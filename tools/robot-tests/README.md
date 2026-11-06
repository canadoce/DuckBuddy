# Robot test scripts (run on the OPi)

Deploy: `scp start.sh trial.sh thermal_run.sh settle_hold.py rpc.py orangepi@<ip>:robot/`, and after every boot
`cp ~/robot/rpc.py /tmp/rpc.py` (`/tmp` is cleared at power off). Recordings are stored in `~/robot/recs`.

| Script | What it does |
|---|---|
| `start.sh <cfg.toml> <tag>` | Starts robotd in the background (`/tmp/robotd.sock`), log in `recs/robotd-<tag>.log`; servos are not powered |
| `rpc.py init / enable / disable / relax / health / watch S / record S PATH / move VX S` | robotd IPC |
| `trial.sh <tag> [vx] [seconds]` | One walking trial: temperature limit (CPU 80 °C / servo 65 °C) → wait for the standing policy to take over (at most 4 s), then stand 1 s → steady check (the standing policy must be in control, `QUIET_MAX`, default 1.5°/tick) → by default walk at 0.2 m/s for 4 s. Stop the gamepad service padd-dev first, it keeps sending zero velocity |
| `ping_all.py [N]` | Pings the 15 servos and the IMU board (ID 200) one by one, counts lost packets, and reads each servo's voltage, temperature and status. **Do not run it while robotd is running**, both would fight over the bus. The IMU board is slow to answer single reads, so its wait time is 30 ms |
| `settle_hold.py` | Waits until the robot is steady for 1 s, then stops the policy (does not stop in the middle of getting up) |
| `thermal_run.sh <tag> walk\|stand [seconds] [vx] [vyaw]` | Heat test: walks in a circle of about 0.75 m (or only stands), up to the given time (default 180 s), records `recs/thermal_<tag>.jsonl`; robotd's `[thermal]` stops walking by itself at 65 °C |
| `thermal_stats.py` (run on the computer) | Reads each servo's temperature `temps_c` from a recording: start and end temperature, heating rate (°C/minute), and after how many seconds the hottest servo reaches 55 / 60 / 65 °C |

Changing the policy needs a robotd restart: first hold the robot (torque is released on exit), `kill <exact PID>`, then `start.sh`; lift the head up before `init`
(it is refused when the neck is >100° away from the standing pose). To analyse trials: `training/data/2026-10-09-hl2915-v4test/trial_stats.py`
(a fall is judged by body tilt >30°; do not rely only on robotd's limp-fall label -- it sets the walk command to zero).

Without the head fan the OPi overheats (2026-10-09: too hot to touch, and many bus reads and writes failed); until the fan arrives, point a desk fan at the head.
