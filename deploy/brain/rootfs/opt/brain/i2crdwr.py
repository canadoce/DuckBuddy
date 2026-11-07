"""Minimal i2c-dev helper using the I2C_RDWR ioctl (combined transactions)."""
import ctypes
import fcntl
import os

I2C_RDWR = 0x0707
I2C_M_RD = 0x0001


class _msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16),
                ("flags", ctypes.c_uint16),
                ("len", ctypes.c_uint16),
                ("buf", ctypes.POINTER(ctypes.c_uint8))]


class _rdwr(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(_msg)),
                ("nmsgs", ctypes.c_uint32)]


def hat_bus():
    """I2C bus number of the HAT's I2C (header pins 3/5).

    Orange Pi Zero 3W: twi0 @ 0x02510000. Override with ROBOT_HAT_I2C_BUS.
    """
    env = os.environ.get("ROBOT_HAT_I2C_BUS")
    if env:
        return int(env)
    base = "/sys/bus/i2c/devices"
    try:
        for name in sorted(os.listdir(base)):
            if name.startswith("i2c-") and "2510000.twi" in os.path.realpath(os.path.join(base, name)):
                return int(name[4:])
    except OSError:
        pass
    return None


class Codec:
    def __init__(self, bus=None, addr=0x18, wait_secs=20.0):
        # the device node may exist before udev has given it the right group,
        # so wait for it instead of failing (this bit the boot service once)
        import time
        deadline = time.time() + wait_secs
        while True:
            n = bus if bus is not None else hat_bus()
            try:
                if n is None:
                    raise FileNotFoundError("HAT I2C bus (twi0) not present yet")
                self.fd = os.open("/dev/i2c-%d" % n, os.O_RDWR)
                break
            except (FileNotFoundError, PermissionError):
                if time.time() > deadline:
                    raise
                time.sleep(0.2)
        self.bus = n
        self.addr = addr

    def close(self):
        os.close(self.fd)

    def _xfer(self, msgs):
        arr = (_msg * len(msgs))()
        keep = []
        for i, (data, rd) in enumerate(msgs):
            buf = (ctypes.c_uint8 * len(data))(*data)
            keep.append(buf)
            arr[i].addr = self.addr
            arr[i].flags = I2C_M_RD if rd else 0
            arr[i].len = len(data)
            arr[i].buf = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8))
        rw = _rdwr(msgs=arr, nmsgs=len(msgs))
        fcntl.ioctl(self.fd, I2C_RDWR, rw)
        return keep

    def write(self, reg, val):
        self._xfer([([reg, val], False)])

    def read(self, reg):
        # write address, repeated start, read one byte (single transaction)
        keep = self._xfer([([reg], False), ([0], True)])
        return keep[1][0]
