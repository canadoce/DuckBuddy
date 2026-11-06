//! Read a BNO055 through the same code robotd uses, and check it.
//!
//!     bno055_probe [DEVICE] [ADDRESS] [SECONDS] [IMU_AXES]
//!     bno055_probe /dev/i2c-0 0x28 20 "x,y,z"
//!
//! Prints the trunk-frame gravity and gyro twice a second (with `IMU_AXES` as in
//! `[bus] imu_axes`), then a summary: sample rate, stale samples, readiness, and how well the
//! gyro agrees with the turn rate the quaternion shows. Turn the sensor by hand while it runs
//! for that last check; a sign or frame mix-up between the two shows as a negative ratio.

use std::time::{Duration, Instant};

use duck_control::bno055::{self, Bno055, Bno055Decoder};
use duck_control::imu::mount_from_axes;

fn mul(a: [f64; 4], b: [f64; 4]) -> [f64; 4] {
    let ([aw, ax, ay, az], [bw, bx, by, bz]) = (a, b);
    [
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ]
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let device = args.get(1).map(String::as_str).unwrap_or("/dev/i2c-0");
    let address = args
        .get(2)
        .map(|a| u8::from_str_radix(a.trim_start_matches("0x"), 16).expect("address in hex"))
        .unwrap_or(bno055::DEFAULT_ADDRESS);
    let seconds: f64 = args
        .get(3)
        .map(|s| s.parse().expect("seconds"))
        .unwrap_or(20.0);
    let axes = args.get(4).map(String::as_str).unwrap_or("x,y,z");
    let mount = mount_from_axes(axes).expect("IMU_AXES");

    let chip = match Bno055::open(device, address) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("open failed: {e}");
            std::process::exit(1);
        }
    };
    let mut decoder = Bno055Decoder::new(mount, false);
    let t0 = Instant::now();
    let mut next_print = t0;
    let (mut ticks, mut errors, mut stale, mut first_seq, mut last_seq) =
        (0u64, 0u64, 0u64, None, 0u64);
    let mut ready_at = None;
    let mut last_raw = None;
    let mut prev: Option<([f64; 4], Instant)> = None;
    let (mut dot, mut gyro_sq, mut quat_sq) = (0.0f64, 0.0f64, 0.0f64);
    while t0.elapsed().as_secs_f64() < seconds {
        std::thread::sleep(Duration::from_millis(20)); // robotd's 50 Hz tick
        ticks += 1;
        let sample = match chip.latest() {
            Ok(s) => s,
            Err(e) => {
                errors += 1;
                eprintln!("tick {ticks}: {e}");
                continue;
            }
        };
        first_seq.get_or_insert(sample.seq);
        last_seq = sample.seq;
        if last_raw == Some(sample.raw) {
            stale += 1;
        }
        last_raw = Some(sample.raw);
        let imu = decoder.decode(&sample);
        if decoder.ready() && ready_at.is_none() {
            ready_at = Some(t0.elapsed());
        }

        // Gyro against the quaternion's own rate of turn, both in the sensor frame.
        let (gyro, quat) = bno055::decode(&sample.raw);
        if let Some(q) = quat {
            if let Some((qp, tp)) = prev {
                let dt = sample.at.duration_since(tp).as_secs_f64();
                if dt > 0.005 {
                    let mut d = mul([qp[0], -qp[1], -qp[2], -qp[3]], q);
                    if d[0] < 0.0 {
                        d = [-d[0], -d[1], -d[2], -d[3]];
                    }
                    let w = [2.0 * d[1] / dt, 2.0 * d[2] / dt, 2.0 * d[3] / dt];
                    let wn: f64 = w.iter().map(|v| v * v).sum::<f64>().sqrt();
                    if wn > 0.5 {
                        dot += (0..3).map(|i| w[i] * gyro[i]).sum::<f64>();
                        gyro_sq += gyro.iter().map(|v| v * v).sum::<f64>();
                        quat_sq += wn * wn;
                    }
                }
            }
            prev = Some((q, sample.at));
        }

        if Instant::now() >= next_print {
            next_print += Duration::from_millis(500);
            println!(
                "gravity {:+.2} {:+.2} {:+.2} | gyro {:+6.1} {:+6.1} {:+6.1} dps | gyro calibration {} | ready {}",
                imu.gravity[0],
                imu.gravity[1],
                imu.gravity[2],
                imu.gyro[0].to_degrees(),
                imu.gyro[1].to_degrees(),
                imu.gyro[2].to_degrees(),
                bno055::gyro_calibration(sample.calib_stat),
                decoder.ready()
            );
        }
    }
    let elapsed = t0.elapsed().as_secs_f64();
    println!(
        "ticks {ticks}, failed {errors}, stale {stale}; polls {:.0} Hz; ready after {}",
        (last_seq - first_seq.unwrap_or(last_seq)) as f64 / elapsed,
        ready_at
            .map(|d| format!("{:.1} s", d.as_secs_f64()))
            .unwrap_or_else(|| "never".into())
    );
    if quat_sq > 0.0 {
        println!(
            "gyro vs quaternion turn rate while moving: cosine {:+.2}, magnitude ratio {:.2} (1.00 = same)",
            dot / (gyro_sq.sqrt() * quat_sq.sqrt()),
            gyro_sq.sqrt() / quat_sq.sqrt()
        );
    } else {
        println!("not turned enough to compare gyro and quaternion");
    }
}
