# bringup: build / repair tool (web page)

A tool to use after you build or repair a DuckBuddy (MicroDuck). The web page has four tabs:

1. **Servos**:
   - **New-servo setup wizard** (on the Feetech USB board): plug the servos in one at a time. For each one it sets the ID, the limits 0/4095, mode 0 and the unload conditions (5 on the HD-1910, 13 on the HL-2915), changes the baud rate to 500k, locks the EEPROM and reads everything back to check it. For the first servo it asks you to power off and on, to check that the EEPROM really kept the values. At the end each servo moves to center (2048) and holds torque; fit the horn, then release it. Two wirings work: a chain (IDs are given in reverse, the same way as `tools/servo/setup_ids.py`) or one servo at a time. Starting again after an interruption does not give two servos the same ID.
   - **Joint mapping** (after assembly, on the robot bus or the USB board): each servo wiggles ±8° in turn, and you click the joint that moved. When all are done, a "left / right check" wiggles them again to confirm. Then pick one of two: change the IDs in bulk to a chosen order (joint order 1–15, same as the HL-2915 robot, the order in the config, or your own); all servos first move to a temporary ID 160 + new ID and then to the new ID, so swaps work too. Or keep the IDs and write `joint_ids` into the robot config (a backup is made first).
   - Single-servo actions: scan the bus, set ID / baud rate, center, read and write the key registers, wiggle test.
   - **Set current position as center**: writes EEPROM 31 (position correction, BIT15 sign bit) so the servo's present position reads 2048. The 0/4095 wrap point and the goal position shift with it. So when a horn was fitted off center, or a joint's zero reading is near the wrap point, you do not have to take the horn off. Bench-tested on 10-31 on the HL-2915 (firmware 3.45): kept over power off, readings stay continuous across the old wrap point, and center and wiggle reach the right places in the new coordinates. The STS method "write 40=128" does nothing on it. Not tested on the HD-1910 yet.
2. **Zero calibration**: finds `[bus] joint_signs` / `joint_offsets` after assembly. It embeds `tools/joint_align` as is (same code, same page).
3. **IMU firmware**: builds `firmware/imu-feetech` on the computer, flashes it with an ST-Link on PDB J2, then reads ID 200 over the robot bus to check it.
4. **Whole-robot test**: servo bus (every ID answers, SYNC_READ error rate), IMU, mic, speaker, ToF, camera. Each item shows pass / fail and the measured values. The results can be exported as a JSON report.

## Start

```bash
python tools/bringup/app.py --host orangepi@duck-1a2b.local              # the system image's host name is duck-XXXX
python tools/bringup/app.py --host orangepi@192.168.1.50 --com COM11      # by IP, and with the Feetech USB board
python tools/bringup/app.py --bench pi@192.168.1.166                       # Raspberry Pi test bench, no robot
```

Open <http://localhost:8780> in the browser (`--port` changes it); the zero calibration uses the next port, 8781. At the top of each tab there is a tutorial with pictures that you can fold away. It lists the steps, the register values for the HD-1910 and the HL-2915, and what to check when a test fails. With `--listen 0.0.0.0`, a phone on the same LAN can open the page too.

Requirements:

- ssh to the robot must work without a password. The robot needs `python3` and `python3-serial`, nothing else.
- The computer needs `pyserial`. The zero calibration tab also needs `mujoco`, `numpy` and `Pillow` (the same as joint_align). The IMU tab also needs `cargo` and `probe-rs` (`cargo install probe-rs-tools --locked`).

Other options:

| Option | Default | Meaning |
|---|---|---|
| `--config` | `~/robot/active.toml` | robotd's config file; the zero calibration writes back to this file |
| `--unit` | `robotd-dev` | the `systemctl --user` unit used to stop / start robotd |
| `--restart-cmd` | `systemctl --user restart robotd-dev` | run after the zero offsets are written, so robotd reloads its config |
| `--init-cmd` | `cd ~/robot && ./robotctl robot init --robot-socket /tmp/robotd.sock` | run after the restart by "Write and go home" on the zero calibration tab |
| `--bench` | none | ssh address of a Raspberry Pi test bench (see below), used in place of the USB board. With `--bench`, `--host` can be left out; the zero calibration and the whole-robot test then do not work |
| `--bench-port` | `/dev/serial0` | the bench's servo UART |

## Raspberry Pi test bench (in place of the Feetech USB board)

A Raspberry Pi with a [Robot HAT E1](https://code.caric.io/Robotics/elec_RPI_Robot_HAT) can do everything the USB board does:
the new-servo wizard, scan, set ID / baud rate, center, wiggle, register reads and writes, and the
joint mapping on a servo chain plugged into the HAT. The Pi's UART runs 1 Mbit/s exactly (its
UART clock is 48 MHz), so it talks to factory servos, which the Orange Pi's UART cannot do.

`agent.py --usb` runs on the Pi over ssh, the same way as on the robot. Nothing is copied to the Pi.

Set up the Pi once:

- Raspberry Pi OS. The servo UART on pins 8/10 is the PL011 (`/dev/serial0` → `ttyAMA0`):
  in `/boot/config.txt` (`/boot/firmware/config.txt` on newer releases) set `enable_uart=1` and
  `dtoverlay=disable-bt`, and leave `console=serial0,...` out of `cmdline.txt`.
- `sudo apt install python3-serial`.
- ssh with a key from the computer (no password).
- Servo power on the HAT: a 3S battery for the HL-2915 (the HAT's D5 must be the SMBJ15A, see
  [Using a 12 V battery](https://code.caric.io/Robotics/elec_RPI_Robot_HAT/src/branch/main/docs/12V_battery_swap.md)); a 2S battery for the HD-1910. Plug the servo into
  a 3-pin servo connector (J13 / J14, pin order 1 GND · 2 battery · 3 DATA).

Then start the app with `--bench user@pi-address` (add `--host` too when the robot is on as well).
"Raspberry Pi test bench" is first in the overview tab's port list and is selected at start-up; the
pages that say "USB board" then use the bench.

### Factory servos in a robot that is already built

Factory servos are all ID 1 at 1 Mbit/s, so they must still be set up one at a time. With the servos
mounted but not cabled yet:

- Take the robot's battery out, if it has one in. The bench HAT powers the servos.
- In the wizard pick wiring "One at a time" and ID order `1-15`. Then plug the bench's servo cable
  into the servos in `joint_ids` order (L-yaw, roll, pitch, knee, ankle, neck, head pitch, yaw, roll,
  mouth, R-yaw, roll, pitch, knee, ankle), one at a time, as the wizard asks. Each servo then has
  the ID of its joint, so `joint_ids` is `[1, 2, ..., 15]`.
- The battery on the bench HAT's XT60 powers the HAT, the Pi and the servos together; there is no
  separate servo switch. Turn the bench off (battery out) before you plug or unplug a servo, and
  wait for the Pi to boot again (about a minute) before you click. Plugging with power on can spark.
- **Clear "Center to fit horn".** The horns are already on: centering would drive the
  joint to 2048, which can be past its stop.
- Then, with the robot's own board: the joint mapping (to check `joint_ids` and the signs), "Set
  current position as center" for any joint whose zero reading is near the 0/4095 wrap point, and
  the zero calibration.

## Layout

```
browser ⇄ app.py (computer) ─ ssh ─ agent.py (robot: /dev/ttyS0 500k, plus audio / ToF / camera)
                            ├─ agent.py --usb (computer: Feetech USB board, COMx)
                            ├─ agent.py --usb on the test bench Pi over ssh (/dev/serial0, 1M), with --bench
                            ├─ tools/joint_align (zero calibration, port +1)
                            └─ cargo / probe-rs (IMU firmware)
```

- On each connection `agent.py` is sent to the robot on ssh's stdin and runs there, so there are no files to deploy on the robot. It takes one JSON request per line and answers with one JSON line. You can also run it on the robot by hand: `python3 agent.py`, then type requests on stdin.
- Factory servos run at 1M. The OPi's UART set to 1M really runs at only 750k, so a new servo's ID and baud rate must be set with the Feetech USB board (CH343, pick its serial port on the overview tab) or the test bench. The FD software holds this serial port while it is open.

## Safety rules (already built into the tool)

- **robotd holds the bus.** While it runs, the servo tab, the bus test and the IMU test on the PDB board (ID 200) all refuse to run. The BNO055 test reads I2C, not the servo bus, so it runs alongside robotd. The overview tab can stop it: if it was started by the `robotd-dev` unit, it is stopped with systemctl; otherwise only the PID shown on the page is stopped. **Stopping robotd does not relax the servos.**
- Every action that moves a servo or turns torque on (wiggle, center, torque on, writes to 40/41/42/44/46) needs a "held" confirmation on the page first.
- Goal writes always cover 42..47 together (goal position + 44 + 46). The reason: the HD-1910 sticks at zero current if 46 is not rewritten.
- Torque on is refused when a servo reads outside 0..4095 (multi-turn count). Only powering the servo off clears the multi-turn count.
- Wiggle test: swings ±amplitude around the present position, comes back, then releases torque. A side that would cross 0/4095 is skipped. The current limit is 400 mA by default; torque goes off at once if the current stays above 1.5 A or the position drifts 15° off.
- Center: moves to the nearest 2048 in the same turn and holds torque, for fitting the horn. Only for servos not yet built into a joint. Torque goes off if it moves further away or the current is too high.
- "Relax all" in the page header: sends `robot.relax` while robotd runs; otherwise it broadcasts "torque switch = 0" on the bus.
- EEPROM writes unlock first (55=0) and lock again after. Before an ID change the tool checks that the new ID is free; the IMU's 200 cannot be used.

## Whole-robot test criteria

| Item | Method | Pass when |
|---|---|---|
| Servo bus | PING each of the config's `joint_ids`, then N rounds of SYNC_READ the way robotd does it (15 bytes from address 56, IMU last; the IMU is left out when `[bus] imu_source = "bno055"`) | all answer; error rate ≤ 0.5%; all status bits 0; no multi-turn readings |
| IMU (PDB board, ID 200) | read ID 200's version, model, the 56..70 block and the diagnostic counters from 90, for 2 seconds | model 0x16D6; flags = 3; fusion output 90–150 Hz; \|q\| ≈ 1; gyro noise < 1 dps and bias < 5 dps while still; no receive errors on the board. Pitch / roll are converted to the trunk frame with `[bus] imu_axes` |
| IMU (BNO055, `[bus] imu_source = "bno055"`) | read the BNO055 over I2C (`[bus] imu_i2c`, default `/dev/i2c-0`; address `imu_i2c_address`, default 0x28) in place of ID 200, for 2 seconds. If the chip is not in IMU fusion mode and robotd is not running, the test sets that mode first | chip ID 0xA0; mode IMU fusion (0x08); samples change at least 20 times a second (the quaternion alone stays the same while the chip is perfectly still, so the check counts changes of the whole sample); \|q\| within 0.98..1.02; gyro noise < 1 dps and bias < 5 dps while still; gyro calibration 3/3 (keep the robot still for a few seconds); read failures ≤ 1%. Pitch / roll are converted with `[bus] imu_axes`. `gravity_sensor` in the result shows which sensor axis carries gravity; use it to find `imu_axes` (robot upright, then on its back) |
| Mic | play silence and record 4 seconds at the same time (play first, then record, or the whole recording is stuck at full scale); clap or talk during the recording | neither channel is all 0; DC offset < 3000; clipping < 2%; peak ≥ 4 × noise floor |
| Speaker | play 1 kHz (−12 dBFS) and record at the same time, compare the 1 kHz energy in the loud and quiet windows; then ask whether a person heard it | ≥ 15 dB higher, and a person heard it |
| ToF | read tofd's `tof.stream`; when tofd is not running, start one for the test (`--bus` taken from tofd-dev.service, default /dev/i2c-2) and stop only that one afterwards | ≥ 10 Hz; ≥ 32/64 valid zones |
| Camera | find the node named `vin_video*`, grab 45 frames with `duckcam --half` (ISP auto exposure) | ≥ 10 fps; brightness not all black or all white; the image has texture. A thumbnail is attached |

- The camera test never calls `v4l2-ctl --list-ctrls`: that command hangs the board. When the vin driver is not loaded, run `sudo modprobe -a vin_io imx219 vin_v4l2` first.
- While visiond runs it holds the camera, and the camera test reports it as in use.
