//! The seam between the control loop and the physical world.
//!
//! Everything between [`RobotIo::read`] and [`RobotIo::write`] is pure computation over
//! plain data, which is what makes the loop testable without a robot.
//!
//! [`Sensors`] carries joints *and* IMU together because that is what the hardware does:
//! the IMU board sits on the Dynamixel bus and is fetched in the same transaction as the
//! servos. A trait that split them would invent a distinction the bus does not have, and
//! would double the bus traffic to honour it.

use crate::imu::ImuData;
use crate::model::NUM_JOINTS;

/// One atomic sample of the robot.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Sensors {
    /// Joint angles in radians, indexed as [`crate::model::JOINT_NAMES`].
    pub positions: [f64; NUM_JOINTS],
    /// Joint velocities, rad/s.
    pub velocities: [f64; NUM_JOINTS],
    /// Present current magnitude, mA. Sign is dropped — direction is inferable from
    /// velocity, and every consumer so far wants load, not direction.
    pub currents_ma: [f64; NUM_JOINTS],
    pub imu: ImuData,
}

impl Default for Sensors {
    fn default() -> Self {
        Self {
            positions: [0.0; NUM_JOINTS],
            velocities: [0.0; NUM_JOINTS],
            currents_ma: [0.0; NUM_JOINTS],
            imu: ImuData::default(),
        }
    }
}

/// What the loop commands. Position control only — alpha has no velocity-mode joints.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct JointTargets {
    pub positions: [f64; NUM_JOINTS],
}

impl JointTargets {
    pub fn new(positions: [f64; NUM_JOINTS]) -> Self {
        Self { positions }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum IoError {
    #[error("serial port {path}: {source}")]
    Port {
        path: String,
        #[source]
        source: std::io::Error,
    },
    #[error("bus transaction failed: {0}")]
    Bus(String),
    /// A `sync_read` that returns the wrong number of blocks, or a block of the wrong
    /// length, means a device did not answer. Reported rather than papered over: a
    /// silently short read would leave stale values in half the joint array.
    #[error("{what}: expected {expected}, got {got}")]
    ShortRead {
        what: &'static str,
        expected: usize,
        got: usize,
    },
    #[error("simulated failure")]
    Simulated,
    /// The IMU on I²C (see [`crate::bno055`]) could not be opened or set up.
    #[error("IMU on {path}: {source}")]
    Imu {
        path: String,
        #[source]
        source: std::io::Error,
    },
}

pub type Result<T> = std::result::Result<T, IoError>;

/// What the servos report about their own supply and case, rather than their motion.
///
/// Sampled about once a second rather than every tick — see [`RobotIo::slow_sensors`]. A pack
/// does not drain and a motor does not heat up in 20 ms, so the tick would be paying for a
/// second bus transaction to learn nothing new.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SlowSensors {
    /// Mean supply voltage across the servos, in volts — the only battery measurement the
    /// robot has, since there is no fuel gauge anywhere on the hat.
    pub volts: f64,
    /// Per-joint case temperature in °C, indexed as [`crate::model::JOINT_NAMES`].
    ///
    /// Per-joint rather than an average because the interesting case is one joint carrying
    /// the load — a knee holding a squat runs far hotter than the mouth, and a mean over
    /// fifteen servos hides exactly the servo about to latch its overheat shutdown.
    pub temps_c: [f64; NUM_JOINTS],
}

/// IMU reads that came back byte-for-byte identical to their predecessor.
///
/// Two numbers, because they answer two different questions and only one of them is worth
/// waking someone for. The *total* says how often the board has repeated itself over the whole
/// run: sporadic hits are ordinary, since the loop and the board keep their own clocks and a
/// tick landing inside one board refresh legitimately sees the same bytes twice. The *run* says
/// whether orientation is frozen right now — a board that has stopped fusing repeats on every
/// single tick, so its run climbs without bound while a total on its own looks the same as a
/// handful of hiccups.
///
/// Reported together so no backend can offer one without the other; a run with no total to
/// scale it against is how the count came to be read as an alarm in the first place.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct ImuStale {
    /// Stale reads since startup, cumulative and never reset.
    pub total: u64,
    /// Length of the current unbroken run of stale reads. Any fresh block resets it to zero.
    pub run: u64,
}

pub trait RobotIo {
    /// One transaction: joints and IMU together.
    fn read(&mut self) -> Result<Sensors>;
    fn write(&mut self, targets: &JointTargets) -> Result<()>;

    /// Set the position P gain on every joint.
    ///
    /// Here rather than in the bus layer alone because it is what makes "go limp" mean
    /// something. Refusing to command a fallen robot only freezes it in the pose it fell
    /// in; dropping the gain lets it yield. The prototype does the same, at kP 50 against
    /// a running value of 200.
    fn set_gain(&mut self, kp: u16) -> Result<()>;

    /// Torque on or off, every joint.
    ///
    /// On the trait — rather than only on the bus — because bringing the robot up is now something
    /// the control loop does when a human asks, and everything that reaches a motor goes through
    /// [`crate::safety::Safety`], which owns the only handle.
    ///
    /// **Nothing calls this at startup, and that part has not changed.** A `robotd` restarted by an
    /// update must leave a standing robot standing: torque comes on when someone enables the policy,
    /// never because a process began.
    fn set_torque(&mut self, on: bool) -> Result<()>;

    /// Which joints go limp while torque is on: `true` turns that joint's torque off and stops
    /// commanding it, `false` gives it torque back, holding where it now is. For a robot
    /// resting seated with its legs unloaded — a servo that holds anything heats ~13 °C a
    /// minute whatever the load (2026-10-12). Takes effect at once when torque is on, and is
    /// remembered across `set_torque`. A bus that cannot do it says so.
    fn set_limp(&mut self, limp: [bool; NUM_JOINTS]) -> Result<()> {
        let _ = limp;
        Err(IoError::Bus(
            "this bus cannot leave single joints limp".into(),
        ))
    }

    /// Supply voltage and case temperatures, in one extra transaction.
    ///
    /// Not part of [`Sensors`], and not on the tick's critical path: these registers sit at
    /// 144–146, past the end of the contiguous block [`Self::read`] fetches, so reaching them
    /// costs a transaction of its own — about a millisecond. Negligible once a second, 5% of
    /// the budget at 50 Hz.
    fn slow_sensors(&mut self) -> Result<SlowSensors>;

    /// Diagnostics the bus keeps about itself. Default to "nothing to report" so a fake or a
    /// future backend is not obliged to invent them.
    ///
    /// `sync_read` blocks identical to their predecessor: the board answered but did not
    /// refresh, which means the policy would be fed dead orientation. Invisible unless
    /// someone counts it, which is why it is counted.
    fn imu_stale(&self) -> ImuStale {
        ImuStale::default()
    }

    /// Has the orientation filter converged? False for the first moments after startup.
    fn imu_ready(&self) -> bool {
        true
    }
}

/// A robot made of nothing, for tests.
///
/// Always compiled — it is what the test suite runs against, and it is why `cargo test`
/// needs no hardware, no network and no Docker. Positions echo back whatever was last
/// written, so a loop driving it behaves like a servo that tracks perfectly.
pub struct FakeIo {
    sensors: Sensors,
    /// Set to make the next [`RobotIo::read`] fail, then cleared. For exercising the
    /// loop's error path without a flaky bus.
    pub fail_next_read: bool,
    /// Reads still to fail before this one starts answering, decremented per read. Models a
    /// robot whose servos are not powered yet, and then are.
    pub fail_reads: u32,
    pub last_written: Option<JointTargets>,
    pub reads: usize,
    pub writes: usize,
    /// Last gain commanded, so a test can tell "went limp" from "stopped commanding".
    pub last_gain: Option<u16>,
    /// Whether the orientation filter reports converged. False models the first seconds after
    /// startup, when projected gravity is not yet a measurement.
    pub imu_ready: bool,
    /// What [`RobotIo::slow_sensors`] reports. Mid-pack and hand-warm by default so `--fake`
    /// shows a plausible robot; set it to exercise a flat pack or a cooking servo. `None`
    /// fails the read, which is what a robot with no bus does.
    pub slow: Option<SlowSensors>,
    /// When true, `read` reports the last written targets as the present positions.
    track_targets: bool,
    /// Last torque state commanded, or `None` if nothing ever asked. `None` is the assertion that
    /// matters most: it is what "a restart did not move the robot" looks like.
    pub torque: Option<bool>,
    /// How many times torque was written, so a test can tell "brought up once" from "written every
    /// tick" — the latter being a bus transaction per joint per tick.
    pub torque_writes: usize,
    /// The last `set_limp` mask.
    pub limp: [bool; NUM_JOINTS],
    /// A file holding the gravity to report ("x y z" in the trunk frame), re-read a few times a
    /// second: how a simulator tips the fake robot over. `None` keeps the IMU as set.
    tilt_file: Option<std::path::PathBuf>,
}

impl Default for FakeIo {
    fn default() -> Self {
        Self::new()
    }
}

impl FakeIo {
    pub fn new() -> Self {
        Self {
            sensors: Sensors::default(),
            fail_next_read: false,
            fail_reads: 0,
            last_written: None,
            reads: 0,
            writes: 0,
            last_gain: None,
            imu_ready: true,
            slow: Some(SlowSensors {
                volts: 7.4,
                temps_c: [32.0; NUM_JOINTS],
            }),
            track_targets: true,
            torque: None,
            torque_writes: 0,
            limp: [false; NUM_JOINTS],
            tilt_file: None,
        }
    }

    /// Report the gravity written in `path` ("x y z", trunk frame, any length; upright is
    /// `0 0 -1`), re-read every tenth read. A missing or unreadable file leaves the IMU as it was.
    pub fn tilted_by(mut self, path: impl Into<std::path::PathBuf>) -> Self {
        self.tilt_file = Some(path.into());
        self
    }

    fn read_tilt(&mut self) {
        let Some(path) = &self.tilt_file else { return };
        let Ok(text) = std::fs::read_to_string(path) else { return };
        let v: Vec<f64> = text.split_whitespace().filter_map(|w| w.parse().ok()).collect();
        if let [x, y, z] = v[..] {
            if let Some(imu) = ImuData::from_gravity([x, y, z]) {
                self.sensors.imu = imu;
            }
        }
    }

    /// Start from a known pose — typically [`crate::model::DEFAULT_POSITION`].
    pub fn at(positions: [f64; NUM_JOINTS]) -> Self {
        let mut io = Self::new();
        io.sensors.positions = positions;
        io
    }

    /// Freeze reported positions so they ignore what is written. Models a robot whose
    /// servos are limp, or one being pushed around by hand.
    pub fn frozen(mut self) -> Self {
        self.track_targets = false;
        self
    }

    /// Fail the next `n` reads, then behave normally. Models a board that comes up before
    /// its servo power does.
    pub fn failing_reads(mut self, n: u32) -> Self {
        self.fail_reads = n;
        self
    }

    pub fn set_imu(&mut self, imu: ImuData) {
        self.sensors.imu = imu;
    }

    pub fn positions(&self) -> [f64; NUM_JOINTS] {
        self.sensors.positions
    }
}

impl RobotIo for FakeIo {
    fn read(&mut self) -> Result<Sensors> {
        if self.fail_next_read {
            self.fail_next_read = false;
            return Err(IoError::Simulated);
        }
        if self.fail_reads > 0 {
            self.fail_reads -= 1;
            return Err(IoError::Simulated);
        }
        if self.reads % 10 == 0 {
            self.read_tilt();
        }
        self.reads += 1;
        Ok(self.sensors)
    }

    fn write(&mut self, targets: &JointTargets) -> Result<()> {
        self.writes += 1;
        self.last_written = Some(*targets);
        if self.track_targets {
            self.sensors.positions = targets.positions;
        }
        Ok(())
    }

    fn set_gain(&mut self, kp: u16) -> Result<()> {
        self.last_gain = Some(kp);
        Ok(())
    }

    fn set_torque(&mut self, on: bool) -> Result<()> {
        self.torque = Some(on);
        self.torque_writes += 1;
        Ok(())
    }

    fn set_limp(&mut self, limp: [bool; NUM_JOINTS]) -> Result<()> {
        self.limp = limp;
        Ok(())
    }

    fn imu_ready(&self) -> bool {
        self.imu_ready
    }

    fn slow_sensors(&mut self) -> Result<SlowSensors> {
        self.slow.ok_or(IoError::Simulated)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::DEFAULT_POSITION;

    /// The loop's whole contract in slice 1: whatever it writes, it reads back. A FakeIo
    /// that ignored writes would make every hold-pose test pass vacuously.
    #[test]
    fn fake_io_tracks_what_was_written() {
        let mut io = FakeIo::at(DEFAULT_POSITION);
        assert_eq!(io.read().unwrap().positions, DEFAULT_POSITION);

        let mut moved = DEFAULT_POSITION;
        moved[0] = 0.5;
        io.write(&JointTargets::new(moved)).unwrap();
        assert_eq!(io.read().unwrap().positions, moved);
        assert_eq!(io.writes, 1);
    }

    /// A limp or hand-held robot does not follow commands. Slice 2's safety work needs to
    /// be testable against that, so the divergence has to be expressible.
    #[test]
    fn frozen_fake_io_ignores_writes() {
        let mut io = FakeIo::at(DEFAULT_POSITION).frozen();
        let mut moved = DEFAULT_POSITION;
        moved[0] = 0.5;
        io.write(&JointTargets::new(moved)).unwrap();
        assert_eq!(io.read().unwrap().positions, DEFAULT_POSITION);
    }

    /// A read failure must be a one-shot, or a test that injects one can never recover and
    /// the loop's retry path is untestable.
    #[test]
    fn a_tilt_file_tips_the_fake_robot() {
        let path = std::env::temp_dir().join(format!("fake-tilt-{}", std::process::id()));
        std::fs::write(&path, "0 2 0").unwrap();
        let mut io = FakeIo::new().tilted_by(&path);
        let g = io.read().unwrap().imu.gravity;
        assert!((g[1] - 1.0).abs() < 1e-9 && g[0].abs() < 1e-9 && g[2].abs() < 1e-9, "{g:?}");
        std::fs::write(&path, "0 0 -1").unwrap();
        for _ in 0..10 {
            io.read().unwrap();
        }
        assert!((io.read().unwrap().imu.gravity[2] + 1.0).abs() < 1e-9);
        std::fs::remove_file(&path).ok();
    }

    #[test]
    fn simulated_read_failure_clears_itself() {
        let mut io = FakeIo::new();
        io.fail_next_read = true;
        assert!(io.read().is_err());
        assert!(io.read().is_ok());
    }
}
