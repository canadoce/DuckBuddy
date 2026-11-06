//! The BNO055 on I²C: the body IMU of a robot whose servo bus carries no IMU board.
//!
//! This is the Robot HAT E1 build: no PDB/IMU board in the body, a BNO055 breakout there
//! instead, on a Qwiic cable to the HAT in the head (J5, TWI0 — not J8, whose ToF frames hold
//! the bus for 10–30 ms at a time, longer than the IMU lag the walking policies tolerate).
//!
//! The chip runs in its **IMU fusion mode** (accelerometer + gyroscope, no magnetometer: the
//! servos' magnets and currents would pull a compass). It fuses at 100 Hz and serves a
//! relative-orientation quaternion — sensor→world, scalar-first, world z up, the same
//! convention as the bus board's SFLP game rotation vector, checked on the bench against its
//! accelerometer (0.8° at a 44° tilt; the conjugate was 87° off) — and a gyro with its bias
//! removed. Both go through [`TrunkFrame`], the same arithmetic the bus board's block does.
//!
//! A thread polls the chip every [`POLL`] and keeps the newest sample; the control loop takes
//! that sample each tick without touching I²C, so a slow or failing transfer stalls the thread,
//! never the loop. A sample that stops arriving is reported the way a dead bus board is: the
//! tick's read fails (see [`Bno055::latest`]).

use std::io;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use crate::imu::{ImuData, TrunkFrame};

/// The Adafruit breakout's address (ADR pin low). 0x29 with ADR high.
pub const DEFAULT_ADDRESS: u8 = 0x28;

/// What [`REG_CHIP_ID`] reads on every BNO055.
pub const CHIP_ID: u8 = 0xA0;

const REG_CHIP_ID: u8 = 0x00;
const REG_PAGE_ID: u8 = 0x07;
/// Gyro x/y/z, then Euler, then the quaternion w/x/y/z: one contiguous read.
const REG_GYRO: u8 = 0x14;
const REG_CALIB_STAT: u8 = 0x35;
const REG_SYS_STATUS: u8 = 0x39;
const REG_SYS_ERR: u8 = 0x3A;
const REG_UNIT_SEL: u8 = 0x3B;
const REG_OPR_MODE: u8 = 0x3D;
const REG_PWR_MODE: u8 = 0x3E;

const MODE_CONFIG: u8 = 0x00;
/// Fusion of accelerometer and gyroscope, relative orientation.
const MODE_IMU: u8 = 0x08;

/// Bytes read per sample: gyro (6), Euler (6, unused), quaternion (8).
pub const BLOCK_LEN: usize = 20;
const OFF_QUAT: usize = 12;

/// The default gyro unit, 1 dps = 16 LSB, in rad/s.
const GYRO_RAD_PER_LSB: f64 = std::f64::consts::PI / 180.0 / 16.0;
/// Quaternion unit: 1 = 2^14 LSB.
const QUAT_PER_LSB: f64 = 1.0 / 16384.0;

/// How often the thread reads a sample. Twice the fusion rate, so a sample is at most 5 ms old
/// when the loop takes it.
pub const POLL: Duration = Duration::from_millis(5);
/// How often the thread checks the chip is still in fusion mode (a brown-out resets it to
/// config mode, where it answers every read with a frozen sample) and reads its calibration.
const HEALTH_EVERY: u32 = 200;
/// Failed reads in a row after which the thread sets the chip up again.
const REINIT_AFTER: u32 = 20;
/// A sample older than this fails the tick's read: five ticks at 50 Hz.
pub const MAX_AGE: Duration = Duration::from_millis(100);

/// Register access, so the setup sequence can be tested without a chip.
pub trait Registers {
    fn read(&mut self, reg: u8, buf: &mut [u8]) -> io::Result<()>;
    fn write(&mut self, reg: u8, value: u8) -> io::Result<()>;
}

/// One sample as the chip sent it, decoded into the sensor's frame: rad/s, and the
/// quaternion when the chip has produced one (all zeros until fusion has run, and a value
/// far from unit length is a corrupt transfer).
pub fn decode(raw: &[u8; BLOCK_LEN]) -> ([f64; 3], Option<[f64; 4]>) {
    let i16_at = |at: usize| i16::from_le_bytes([raw[at], raw[at + 1]]) as f64;
    let gyro = [
        i16_at(0) * GYRO_RAD_PER_LSB,
        i16_at(2) * GYRO_RAD_PER_LSB,
        i16_at(4) * GYRO_RAD_PER_LSB,
    ];
    let q = [
        i16_at(OFF_QUAT) * QUAT_PER_LSB,
        i16_at(OFF_QUAT + 2) * QUAT_PER_LSB,
        i16_at(OFF_QUAT + 4) * QUAT_PER_LSB,
        i16_at(OFF_QUAT + 6) * QUAT_PER_LSB,
    ];
    let norm = (q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]).sqrt();
    let quat = (0.95..=1.05).contains(&norm).then_some(q);
    (gyro, quat)
}

/// Gyro calibration status, 0..=3, from the `CALIB_STAT` register. 3 once the chip has seen
/// itself still for a few seconds and measured its gyro offset.
pub fn gyro_calibration(calib_stat: u8) -> u8 {
    (calib_stat >> 4) & 3
}

/// Check the chip is there and put it in IMU fusion mode. Waits out the chip's boot (650 ms
/// from power-up) if it does not answer yet.
pub fn configure<R: Registers, S: FnMut(Duration)>(regs: &mut R, mut sleep: S) -> io::Result<()> {
    let mut id = [0u8];
    let mut tries = 0;
    loop {
        match regs.read(REG_CHIP_ID, &mut id) {
            Ok(()) if id[0] == CHIP_ID => break,
            Ok(()) if tries >= 20 => {
                return Err(io::Error::other(format!(
                    "chip ID 0x{:02x}, not a BNO055 (0x{CHIP_ID:02x})",
                    id[0]
                )));
            }
            Err(e) if tries >= 20 => return Err(e),
            _ => {}
        }
        tries += 1;
        sleep(Duration::from_millis(100));
    }
    // Every setting is written in config mode; leaving another mode takes 19 ms.
    regs.write(REG_OPR_MODE, MODE_CONFIG)?;
    sleep(Duration::from_millis(25));
    regs.write(REG_PAGE_ID, 0)?;
    regs.write(REG_PWR_MODE, 0)?; // normal
    sleep(Duration::from_millis(10));
    regs.write(REG_UNIT_SEL, 0)?; // m/s², dps, degrees
    regs.write(REG_OPR_MODE, MODE_IMU)?;
    sleep(Duration::from_millis(20)); // 7 ms from config mode to any fusion mode
    let mut mode = [0u8];
    regs.read(REG_OPR_MODE, &mut mode)?;
    if mode[0] & 0x0F != MODE_IMU {
        let mut err = [0u8];
        let _ = regs.read(REG_SYS_ERR, &mut err);
        return Err(io::Error::other(format!(
            "operating mode reads 0x{:02x} after setting IMU mode (system error {})",
            mode[0], err[0]
        )));
    }
    Ok(())
}

/// The newest sample the thread has read.
#[derive(Debug, Clone, Copy)]
pub struct Sample {
    pub raw: [u8; BLOCK_LEN],
    /// Samples read since the thread started; 0 = none yet.
    pub seq: u64,
    /// When it was read.
    pub at: Instant,
    /// The last `CALIB_STAT` read (see [`HEALTH_EVERY`]).
    pub calib_stat: u8,
}

#[derive(Debug)]
struct Shared {
    sample: Sample,
    /// The last failure, kept until the next good read, for the error a stale sample raises.
    error: Option<String>,
}

/// The chip and the thread that polls it. Dropping it stops the thread.
pub struct Bno055 {
    shared: Arc<Mutex<Shared>>,
    stop: Arc<AtomicBool>,
    thread: Option<JoinHandle<()>>,
    device: String,
}

impl Bno055 {
    /// Open the I²C device, set the chip up (failing if it is not there) and start polling.
    pub fn open(device: &str, address: u8) -> io::Result<Self> {
        let mut dev = i2c::I2c::open(device, address)?;
        configure(&mut dev, std::thread::sleep).map_err(|e| {
            io::Error::new(
                e.kind(),
                format!("BNO055 at 0x{address:02x} on {device}: {e}"),
            )
        })?;
        let mut status = [0u8];
        let _ = dev.read(REG_SYS_STATUS, &mut status);
        tracing::info!(
            device,
            address = format!("0x{address:02x}"),
            system_status = status[0],
            "BNO055 in IMU fusion mode"
        );

        let shared = Arc::new(Mutex::new(Shared {
            sample: Sample {
                raw: [0; BLOCK_LEN],
                seq: 0,
                at: Instant::now(),
                calib_stat: 0,
            },
            error: None,
        }));
        let stop = Arc::new(AtomicBool::new(false));
        let thread = {
            let (shared, stop) = (Arc::clone(&shared), Arc::clone(&stop));
            std::thread::Builder::new()
                .name("bno055".into())
                .spawn(move || poll(dev, shared, stop))?
        };
        Ok(Self {
            shared,
            stop,
            thread: Some(thread),
            device: device.to_owned(),
        })
    }

    /// The newest sample, or why there has been none for [`MAX_AGE`].
    pub fn latest(&self) -> Result<Sample, String> {
        let shared = self.shared.lock().unwrap_or_else(|e| e.into_inner());
        let age = shared.sample.at.elapsed();
        if shared.sample.seq == 0 || age > MAX_AGE {
            return Err(format!(
                "BNO055 on {}: no sample for {} ms{}",
                self.device,
                age.as_millis(),
                shared
                    .error
                    .as_deref()
                    .map(|e| format!(" ({e})"))
                    .unwrap_or_default()
            ));
        }
        Ok(shared.sample)
    }
}

impl Drop for Bno055 {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
    }
}

fn poll(mut dev: i2c::I2c, shared: Arc<Mutex<Shared>>, stop: Arc<AtomicBool>) {
    let mut next = Instant::now();
    let mut failed: u32 = 0;
    let mut polls: u32 = 0;
    let mut calib_stat = 0u8;
    let mut raw = [0u8; BLOCK_LEN];
    while !stop.load(Ordering::Relaxed) {
        next += POLL;
        let now = Instant::now();
        if next > now {
            std::thread::sleep(next - now);
        } else {
            next = now; // fell behind (a long transfer): do not try to catch up
        }

        polls = polls.wrapping_add(1);
        if polls.is_multiple_of(HEALTH_EVERY) {
            let mut b = [0u8];
            match dev.read(REG_OPR_MODE, &mut b) {
                Ok(()) if b[0] & 0x0F != MODE_IMU => {
                    tracing::warn!(
                        mode = b[0],
                        "BNO055 left IMU fusion mode (reset?); setting it up again"
                    );
                    failed = REINIT_AFTER;
                }
                _ => {}
            }
            if dev.read(REG_CALIB_STAT, &mut b).is_ok() {
                if gyro_calibration(b[0]) != gyro_calibration(calib_stat) {
                    tracing::info!(gyro = gyro_calibration(b[0]), "BNO055 gyro calibration");
                }
                calib_stat = b[0];
            }
        }

        if failed >= REINIT_AFTER {
            match configure(&mut dev, std::thread::sleep) {
                Ok(()) => {
                    tracing::info!("BNO055 set up again");
                    failed = 0;
                }
                Err(e) => {
                    set_error(&shared, format!("setting it up again: {e}"));
                    std::thread::sleep(Duration::from_millis(200));
                    continue;
                }
            }
        }

        match dev.read(REG_GYRO, &mut raw) {
            Ok(()) => {
                if failed > 0 {
                    tracing::info!(failed, "BNO055 reads again");
                }
                failed = 0;
                let mut s = shared.lock().unwrap_or_else(|e| e.into_inner());
                s.sample = Sample {
                    raw,
                    seq: s.sample.seq + 1,
                    at: Instant::now(),
                    calib_stat,
                };
                s.error = None;
            }
            Err(e) => {
                if failed == 0 {
                    tracing::warn!("BNO055 read failed: {e}");
                }
                failed += 1;
                set_error(&shared, e.to_string());
            }
        }
    }
}

fn set_error(shared: &Mutex<Shared>, e: String) {
    shared.lock().unwrap_or_else(|e| e.into_inner()).error = Some(e);
}

/// The chip's samples in the trunk frame, as [`ImuData`].
///
/// Ready once fusion has produced output **and** the gyro has calibrated once (status 3: a few
/// seconds still) — the same "keep the robot still" moment the bus board needs. Latched: the
/// status can dip while the robot walks, and that must not stop a running policy.
pub struct Bno055Decoder {
    frame: TrunkFrame,
    gyro_calibrated: bool,
}

impl Bno055Decoder {
    pub fn new(mount: [f64; 4], median: bool) -> Self {
        Self {
            frame: TrunkFrame::new(mount).with_median(median),
            gyro_calibrated: false,
        }
    }

    pub fn decode(&mut self, sample: &Sample) -> ImuData {
        if gyro_calibration(sample.calib_stat) == 3 {
            self.gyro_calibrated = true;
        }
        let (gyro, quat) = decode(&sample.raw);
        self.frame.update(gyro, quat)
    }

    pub fn ready(&self) -> bool {
        self.gyro_calibrated && self.frame.ready()
    }
}

#[cfg(target_os = "linux")]
mod i2c {
    use std::fs::{File, OpenOptions};
    use std::io::{self, Read, Write};
    use std::os::fd::AsRawFd;

    /// `I2C_SLAVE` from `linux/i2c-dev.h`.
    const I2C_SLAVE: u64 = 0x0703;

    /// An i2c-dev handle bound to one address. Each register read is a write of the register
    /// number and a separate read, which the BNO055 accepts (it needs no repeated start).
    pub struct I2c {
        file: File,
    }

    impl I2c {
        pub fn open(path: &str, address: u8) -> io::Result<Self> {
            let file = OpenOptions::new()
                .read(true)
                .write(true)
                .open(path)
                .map_err(|e| io::Error::new(e.kind(), format!("{path}: {e}")))?;
            // SAFETY: I2C_SLAVE takes the address by value; the fd is open for the call.
            let r =
                unsafe { libc::ioctl(file.as_raw_fd(), I2C_SLAVE as _, address as libc::c_ulong) };
            if r < 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(Self { file })
        }
    }

    impl super::Registers for I2c {
        fn read(&mut self, reg: u8, buf: &mut [u8]) -> io::Result<()> {
            self.file.write_all(&[reg])?;
            self.file.read_exact(buf)
        }

        fn write(&mut self, reg: u8, value: u8) -> io::Result<()> {
            self.file.write_all(&[reg, value])
        }
    }
}

/// No i2c-dev off Linux: the daemon still builds there, and says why it cannot open the chip.
#[cfg(not(target_os = "linux"))]
mod i2c {
    use std::io;

    pub struct I2c;

    impl I2c {
        pub fn open(path: &str, _address: u8) -> io::Result<Self> {
            Err(io::Error::new(
                io::ErrorKind::Unsupported,
                format!("no i2c-dev on this platform, so {path} cannot be opened"),
            ))
        }
    }

    impl super::Registers for I2c {
        fn read(&mut self, _reg: u8, _buf: &mut [u8]) -> io::Result<()> {
            Err(io::ErrorKind::Unsupported.into())
        }

        fn write(&mut self, _reg: u8, _value: u8) -> io::Result<()> {
            Err(io::ErrorKind::Unsupported.into())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A register file that answers like a BNO055, and records the writes.
    struct FakeChip {
        regs: [u8; 128],
        writes: Vec<(u8, u8)>,
        /// Reads of the chip ID that fail before it answers (still booting).
        booting: u32,
        /// Ignore mode writes, as a chip that will not leave config mode.
        stuck: bool,
    }

    impl FakeChip {
        fn new() -> Self {
            let mut regs = [0u8; 128];
            regs[REG_CHIP_ID as usize] = CHIP_ID;
            Self {
                regs,
                writes: Vec::new(),
                booting: 0,
                stuck: false,
            }
        }
    }

    impl Registers for FakeChip {
        fn read(&mut self, reg: u8, buf: &mut [u8]) -> io::Result<()> {
            if reg == REG_CHIP_ID && self.booting > 0 {
                self.booting -= 1;
                return Err(io::Error::other("nack"));
            }
            let at = reg as usize;
            buf.copy_from_slice(&self.regs[at..at + buf.len()]);
            Ok(())
        }

        fn write(&mut self, reg: u8, value: u8) -> io::Result<()> {
            self.writes.push((reg, value));
            if !(self.stuck && reg == REG_OPR_MODE) {
                self.regs[reg as usize] = value;
            }
            Ok(())
        }
    }

    fn block(gyro: [i16; 3], quat: [i16; 4]) -> [u8; BLOCK_LEN] {
        let mut raw = [0u8; BLOCK_LEN];
        for (k, v) in gyro.iter().enumerate() {
            raw[2 * k..2 * k + 2].copy_from_slice(&v.to_le_bytes());
        }
        for (k, v) in quat.iter().enumerate() {
            raw[OFF_QUAT + 2 * k..OFF_QUAT + 2 * k + 2].copy_from_slice(&v.to_le_bytes());
        }
        raw
    }

    fn sample(raw: [u8; BLOCK_LEN], calib_stat: u8) -> Sample {
        Sample {
            raw,
            seq: 1,
            at: Instant::now(),
            calib_stat,
        }
    }

    #[test]
    fn setup_ends_in_imu_fusion_mode() {
        let mut chip = FakeChip::new();
        configure(&mut chip, |_| {}).unwrap();
        assert_eq!(chip.writes.first(), Some(&(REG_OPR_MODE, MODE_CONFIG)));
        assert_eq!(chip.writes.last(), Some(&(REG_OPR_MODE, MODE_IMU)));
        assert!(chip.writes.contains(&(REG_UNIT_SEL, 0)));
    }

    #[test]
    fn setup_waits_for_a_booting_chip() {
        let mut chip = FakeChip::new();
        chip.booting = 5;
        let mut waited = Duration::ZERO;
        configure(&mut chip, |d| waited += d).unwrap();
        assert!(waited >= Duration::from_millis(500));
    }

    #[test]
    fn setup_refuses_another_chip() {
        let mut chip = FakeChip::new();
        chip.regs[REG_CHIP_ID as usize] = 0x6A;
        let e = configure(&mut chip, |_| {}).unwrap_err();
        assert!(e.to_string().contains("not a BNO055"), "{e}");
    }

    #[test]
    fn setup_fails_when_the_mode_does_not_take() {
        let mut chip = FakeChip::new();
        chip.stuck = true;
        assert!(configure(&mut chip, |_| {}).is_err());
    }

    #[test]
    fn units_decode_as_documented() {
        // 16 LSB = 1 dps; 16384 = 1.0. A 90° turn about z: w = x... = cos/sin 45°.
        let (gyro, quat) = decode(&block([160, -16, 0], [11585, 0, 0, 11585]));
        assert!((gyro[0] - 10f64.to_radians()).abs() < 1e-9);
        assert!((gyro[1] + 1f64.to_radians()).abs() < 1e-9);
        let q = quat.unwrap();
        assert!((q[0] - std::f64::consts::FRAC_1_SQRT_2).abs() < 1e-4);
        assert!((q[3] - std::f64::consts::FRAC_1_SQRT_2).abs() < 1e-4);
    }

    #[test]
    fn no_quaternion_until_fusion_has_run() {
        let (_, quat) = decode(&block([0, 0, 0], [0, 0, 0, 0]));
        assert_eq!(quat, None);
        let (_, quat) = decode(&block([0, 0, 0], [8000, 0, 0, 0]));
        assert_eq!(quat, None, "far from unit length");
    }

    #[test]
    fn upright_sensor_reports_gravity_down() {
        let mut d = Bno055Decoder::new([1.0, 0.0, 0.0, 0.0], false);
        let imu = d.decode(&sample(block([0, 0, 0], [16384, 0, 0, 0]), 0));
        assert!((imu.gravity[2] + 1.0).abs() < 1e-9);
    }

    /// The bench result this module's docs cite: the chip's quaternion is sensor→world, so a
    /// sensor pitched nose-down by θ about its y axis sees gravity along +x by sin θ.
    #[test]
    fn a_tilt_moves_gravity_the_way_the_accelerometer_does() {
        let theta = 30f64.to_radians();
        let (w, y) = ((theta / 2.0).cos(), (theta / 2.0).sin());
        let q = [(w * 16384.0) as i16, 0, (y * 16384.0) as i16, 0];
        let mut d = Bno055Decoder::new([1.0, 0.0, 0.0, 0.0], false);
        let imu = d.decode(&sample(block([0, 0, 0], q), 0));
        // Rotating the sensor +θ about y turns world-down (0,0,-1) into sensor (+sin θ, 0, −cos θ).
        assert!(
            (imu.gravity[0] - theta.sin()).abs() < 1e-3,
            "{:?}",
            imu.gravity
        );
        assert!(
            (imu.gravity[2] + theta.cos()).abs() < 1e-3,
            "{:?}",
            imu.gravity
        );
    }

    #[test]
    fn ready_needs_fusion_and_a_calibrated_gyro_once() {
        let mut d = Bno055Decoder::new([1.0, 0.0, 0.0, 0.0], false);
        let still = block([0, 0, 0], [16384, 0, 0, 0]);
        for _ in 0..30 {
            d.decode(&sample(still, 0x00));
        }
        assert!(!d.ready(), "gyro not calibrated yet");
        d.decode(&sample(still, 0x30));
        assert!(d.ready());
        d.decode(&sample(still, 0x10));
        assert!(d.ready(), "latched through a dip while walking");
    }

    #[test]
    fn opening_a_missing_device_says_which() {
        let e = Bno055::open("/dev/definitely-not-an-i2c-bus", DEFAULT_ADDRESS)
            .err()
            .unwrap();
        assert!(
            e.to_string().contains("/dev/definitely-not-an-i2c-bus"),
            "{e}"
        );
    }
}
