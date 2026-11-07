"""Robot HAT low-battery guard (3S LiPo, the DuckBuddy battery).

Reads the INA226 (0x45) on the HAT I2C bus every few seconds.
- Below WARN_V: blinks the red light and logs a warning.
- Below SHUTDOWN_V for SHUTDOWN_COUNT readings in a row: logs it and powers off.
- No battery seen (bus voltage < NO_BATTERY_V, e.g. on USB-C only): does nothing.

Events go to the journal and to LOG_FILE. Thresholds can be set in
/etc/default/brain-battery-guard (ROBOT_HAT_WARN_V, ROBOT_HAT_SHUTDOWN_V, ...).
"""
import os
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from i2crdwr import Codec  # noqa: E402  (generic I2C_RDWR device helper)

INA_ADDR = 0x45
SHUNT_OHMS = 0.002
BUS_SCALE = 1.25e-3 * 1.006          # V per bit, with this board's measured trim
SHUNT_LSB = 2.5e-6                   # V per bit


def env_f(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


WARN_V = env_f("ROBOT_HAT_WARN_V", 10.5)           # 3.5 V/cell
WARN_CLEAR_V = env_f("ROBOT_HAT_WARN_CLEAR_V", 10.7)
SHUTDOWN_V = env_f("ROBOT_HAT_SHUTDOWN_V", 9.9)     # 3.3 V/cell
SHUTDOWN_COUNT = int(env_f("ROBOT_HAT_SHUTDOWN_COUNT", 3))
NO_BATTERY_V = env_f("ROBOT_HAT_NO_BATTERY_V", 3.0)
PERIOD_S = env_f("ROBOT_HAT_GUARD_PERIOD_S", 10)
LOG_FILE = os.environ.get("ROBOT_HAT_GUARD_LOG", "/var/log/brain-battery.log")
DRY_RUN = os.environ.get("ROBOT_HAT_GUARD_DRY_RUN") == "1"   # log only, never power off
RED_CHIP ="/dev/gpiochip0"
RED_LINE = 97                        # PD1, header pin 32, low = on


def log(msg):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(msg, flush=True)           # journal
    try:
        with open(LOG_FILE, "a") as f:
            f.write("%s %s\n" % (stamp, msg))
            f.flush()
            os.fsync(f.fileno())
    except OSError as e:
        print("cannot write %s: %s" % (LOG_FILE, e), flush=True)


class INA226(Codec):
    def __init__(self):
        super().__init__(addr=INA_ADDR)

    def reg16(self, reg):
        keep = self._xfer([([reg], False), ([0, 0], True)])
        return (keep[1][0] << 8) | keep[1][1]

    def sample(self, n=5, gap=0.1):
        vs, amps = [], []
        for i in range(n):
            vs.append(self.reg16(0x02) * BUS_SCALE)
            raw = struct.unpack(">h", struct.pack(">H", self.reg16(0x01)))[0]
            amps.append(raw * SHUNT_LSB / SHUNT_OHMS)
            if i + 1 < n:
                time.sleep(gap)
        return sum(vs) / n, sum(amps) / n


def blink_red(seconds=0.5):
    """Flash red once. Takes the line only for the flash, so demos can still use it."""
    try:
        import gpiod
        from gpiod.line import Direction, Value
        settings = gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE)
        req = gpiod.request_lines(RED_CHIP, consumer="robot-hat-battery-guard",
                                  config={RED_LINE: settings})
    except Exception:
        return False                 # light busy (a demo holds it) or no gpiod
    try:
        time.sleep(seconds)
        req.set_values({RED_LINE: Value.ACTIVE})   # high = off
    finally:
        req.release()
    return True


def main():
    ina = INA226()
    log("guard started: warn < %.2f V, power off after %d readings < %.2f V"
        % (WARN_V, SHUTDOWN_COUNT, SHUTDOWN_V))
    warning = False
    low_count = 0
    no_battery = None
    errors = 0
    while True:
        start = time.monotonic()
        try:
            volts, amps = ina.sample()
            errors = 0
        except OSError as e:
            errors += 1
            if errors in (1, 30):
                log("INA226 read failed (%s); will keep trying" % e)
            time.sleep(PERIOD_S)
            continue

        if volts < NO_BATTERY_V:
            if no_battery is not True:
                log("no battery seen (%.2f V); guard idle" % volts)
            no_battery, warning, low_count = True, False, 0
            time.sleep(PERIOD_S)
            continue
        if no_battery is not False:
            log("battery %.2f V, %.2f A" % (volts, amps))
            no_battery = False

        if volts < SHUTDOWN_V:
            low_count += 1
            log("battery %.2f V, %.2f A below %.2f V (%d/%d)"
                % (volts, amps, SHUTDOWN_V, low_count, SHUTDOWN_COUNT))
            if low_count >= SHUTDOWN_COUNT:
                log("LOW BATTERY: %.2f V, powering off to protect the battery. "
                    "Unplug it and charge it." % volts)
                if DRY_RUN:
                    log("dry run: not powering off")
                    return
                subprocess.run(["wall", "Robot HAT: battery %.2f V, powering off now" % volts],
                               timeout=5, check=False)
                os.sync()
                subprocess.run(["systemctl", "poweroff"], timeout=30, check=False)
                return
        else:
            if low_count:
                log("battery back to %.2f V; shutdown count reset" % volts)
            low_count = 0

        if not warning and volts < WARN_V:
            warning = True
            log("battery low: %.2f V, %.2f A (warn below %.2f V); blinking red"
                % (volts, amps, WARN_V))
        elif warning and volts >= WARN_CLEAR_V:
            warning = False
            log("battery recovered: %.2f V" % volts)

        if warning or low_count:
            blink_red()
        delay = PERIOD_S - (time.monotonic() - start)
        if delay > 0:
            time.sleep(delay)


if __name__ == "__main__":
    main()
