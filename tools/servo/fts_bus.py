# -*- coding: utf-8 -*-
"""Minimal Feetech FT-SCS bus protocol (HLS series).

Memory table: http://doc.feetech.cn/#/f?q=250689e628d7
Note that the HLS table is **not the same** as STS/SMS. The worst trap is address 44:
on HLS, 44 is "goal current" = the motor's maximum running current. At 0 the servo has no torque at all.
"""
import time
import serial

# ---- addresses -----------------------------------------------------------
ID_ADDR     = 5      # 1B, EEPROM main ID
BAUD_ADDR   = 6      # 1B, EEPROM 0..7 = 1M/500k/250k/128k/115200/76800/57600/38400
MIN_ANGLE   = 9      # 2B, EEPROM. For multi-turn absolute position control write 0 here and in MAX_ANGLE
MAX_ANGLE   = 11     # 2B, EEPROM
PROT_CURR   = 28     # 2B, EEPROM protection current, 6.5mA/LSB
MODE        = 33     # 1B, EEPROM 0=position servo 1=constant speed 2=constant current 3=PWM open loop
TORQUE      = 40     # 1B 0=off 1=on 2=damping
ACCEL       = 41     # 1B, 8.7 deg/s^2, 0=maximum acceleration
GOAL_POS    = 42     # 2B, BIT15 is the direction bit
GOAL_CURR   = 44     # 2B, 6.5mA/LSB -- at 0 the motor has no torque
GOAL_SPEED  = 46     # 2B, 0.732RPM/LSB -- 0 means stop
TORQUE_LIM  = 48     # 2B, 0.1%
LOCK        = 55     # 1B 0=unlocked (EEPROM kept after power off) 1=locked (EEPROM not kept after power off)
PRES_POS    = 56     # 2B, read only, BIT15 is the direction bit
PRES_VOLT   = 62     # 1B, read only, 0.1V
PRES_TEMP   = 63     # 1B, read only, °C
STATUS      = 65     # 1B, read only, bit=1 means that fault is present
PRES_CURR   = 69     # 2B, read only, 6.5mA/LSB

BROADCAST = 0xFE
CENTER    = 2048     # midpoint of the single-turn range 0..4095


def smag(v):
    """Sign bit + magnitude -> signed integer. Feetech uses BIT15 as the direction bit, not two's complement."""
    return -(v & 0x7FFF) if v & 0x8000 else v


def enc(v):
    """Signed integer -> sign bit + magnitude."""
    return (0x8000 | abs(int(v))) if v < 0 else int(v)


class Bus:
    def __init__(self, port='COM11', baud=1000000, timeout=0.03):
        self.s = serial.Serial(port, baud, timeout=timeout, write_timeout=0.5)

    def close(self):
        self.s.close()

    def _txrx(self, sid, inst, params=()):
        body = [sid, len(params) + 2, inst] + list(params)
        self.s.reset_input_buffer()
        self.s.write(bytes([0xFF, 0xFF] + body + [(~sum(body)) & 0xFF]))
        self.s.flush()
        time.sleep(0.003)
        hdr = self.s.read(4)
        if len(hdr) < 4 or hdr[0] != 0xFF or hdr[1] != 0xFF or hdr[2] != sid:
            return None, None
        rest = self.s.read(hdr[3])
        if len(rest) < hdr[3]:
            return None, None
        return rest[0], rest[1:-1]

    def ping(self, sid):
        err, _ = self._txrx(sid, 0x01)
        return err

    def read(self, sid, addr, n):
        _, d = self._txrx(sid, 0x02, (addr, n))
        return d

    def write(self, sid, addr, data):
        return self._txrx(sid, 0x03, [addr] + list(data))

    # ---- helpers --------------------------------------------------------
    def r8(self, sid, addr):
        d = self.read(sid, addr, 1)
        return None if d is None else d[0]

    def r16(self, sid, addr):
        d = self.read(sid, addr, 2)
        return None if d is None else (d[0] | (d[1] << 8))

    def w8(self, sid, addr, v):
        return self.write(sid, addr, [v & 0xFF])

    def w16(self, sid, addr, v):
        v = int(v) & 0xFFFF
        return self.write(sid, addr, [v & 0xFF, (v >> 8) & 0xFF])

    def scan(self, lo=0, hi=253, tries=2):
        """Returns the list of IDs that give a valid PING reply."""
        out = []
        for sid in range(lo, hi + 1):
            for _ in range(tries):
                if self.ping(sid) is not None:
                    out.append(sid)
                    break
        return out

    def pos(self, sid):
        v = self.r16(sid, PRES_POS)
        return None if v is None else smag(v)
