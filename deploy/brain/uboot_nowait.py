#!/usr/bin/env python3
"""Make the brain's boot program (U-Boot) start Linux without waiting for a key on the servo bus.

The Orange Pi 1.0.2 image's U-Boot (2018.07, in the "sunxi-package" on the boot card) keeps its
console on UART0, which on the brain is the servo bus. Before it starts Linux it waits one second
for "any key" there (bootdelay=1). A servo that holds the data line low reads as a key press, so
U-Boot stops at its prompt and the board never boots: the fan spins and nothing else happens.

U-Boot reads no saved settings on this image (its env file lookup has no device), so the only
copy of bootdelay is the default settings built into U-Boot. This script changes "bootdelay=1"
there to "bootdelay=-2": start Linux at once, without checking for a key. The one extra byte comes
from "cpu=armv7", which becomes "cpu=armv" (nothing on this board reads it; it is wrong for this
arm64 board anyway). Then it fixes U-Boot's own checksum and the package checksum.

It reads the package from the card the system booted from, changes it only if it holds exactly
the settings above, saves the card's boot area first, writes, and reads it back. Run as root,
on the board:

    python3 uboot_nowait.py                 # change it (install.sh runs this)
    python3 uboot_nowait.py --check         # only say whether it is changed

Standard library only. To undo, write the saved boot area back (README.md, "Boot program").
"""
import argparse
import os
import struct
import subprocess
import sys
import time

BLOCK = 8192
PACKAGE_BLOCK = 2050                 # boot_package.fex at 8 KiB x 2050 (/usr/lib/u-boot/platform_install.sh)
STAMP = 0x5F0A6C39                   # the sum is taken with this in place of the stored sum
ITEMS_AT, ITEM_SIZE = 0x40, 368      # the package's item table: name[64], offset, length, ...
OLD = b"bootdelay=1\0baudrate=115200\0arch=arm\0cpu=armv7\0"
NEW = b"bootdelay=-2\0baudrate=115200\0arch=arm\0cpu=armv\0"


def boot_disk():
    """The disk holding the root file system: the card the board booted from."""
    source = subprocess.run(["findmnt", "-n", "-o", "SOURCE", "/"], capture_output=True, text=True,
                            check=True).stdout.strip()
    parent = subprocess.run(["lsblk", "-n", "-o", "PKNAME", source], capture_output=True, text=True,
                            check=True).stdout.strip()
    if not parent.startswith("mmcblk"):
        sys.exit(f"the root file system is on {parent or source}, not an SD card or eMMC: not changed")
    return "/dev/" + parent


def read_at(disk, offset, size):
    with open(disk, "rb") as f:
        f.seek(offset)
        return f.read(size)


def checksum(buf, at_sum, start, length):
    stored = struct.unpack_from("<I", buf, at_sum)[0]
    total = sum(struct.unpack_from(f"<{length // 4}I", buf, start))
    return (total - stored + STAMP) & 0xFFFFFFFF


def set_checksum(buf, at_sum, start, length):
    struct.pack_into("<I", buf, at_sum, checksum(buf, at_sum, start, length))


def parse(pkg):
    """The package's valid length and its U-Boot item (offset, length), both checksums checked."""
    if pkg[:13] != b"sunxi-package":
        sys.exit("no sunxi-package where the boot program should be: not changed")
    stored, items, valid_len = struct.unpack_from("<I", pkg, 20)[0], *struct.unpack_from("<2I", pkg, 32)
    if valid_len > len(pkg) or checksum(pkg, 20, 0, valid_len) != stored:
        sys.exit("the package checksum does not match: not changed")
    uboot = None
    for i in range(items):
        at = ITEMS_AT + i * ITEM_SIZE
        name = pkg[at:at + 64].split(b"\0")[0]
        offset, length = struct.unpack_from("<2I", pkg, at + 64)
        if name == b"u-boot":
            uboot = (offset, length)
    if uboot is None:
        sys.exit("no u-boot item in the package: not changed")
    offset, _ = uboot
    if pkg[offset + 4:offset + 9] != b"uboot":
        sys.exit("the u-boot item has no U-Boot header: not changed")
    length = struct.unpack_from("<I", pkg, offset + 20)[0]
    if checksum(pkg, offset + 12, offset, length) != struct.unpack_from("<I", pkg, offset + 12)[0]:
        sys.exit("U-Boot's own checksum does not match: not changed")
    return valid_len, offset, length


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only say whether the boot program is changed")
    ap.add_argument("--disk", help="the boot card (default: the disk holding /)")
    ap.add_argument("--backup-dir", default="/var/backups/brain-uboot",
                    help="where the card's boot area is saved before writing")
    a = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("run as root")
    disk = a.disk or boot_disk()
    start = PACKAGE_BLOCK * BLOCK
    head = read_at(disk, start, 64)
    if head[:13] != b"sunxi-package":
        sys.exit(f"no sunxi-package at {start} on {disk}: not changed")
    pkg = bytearray(read_at(disk, start, struct.unpack_from("<I", head, 36)[0]))
    valid_len, offset, length = parse(pkg)
    uboot = pkg[offset:offset + length]
    if uboot.count(NEW) == 1 and uboot.count(OLD) == 0:
        print(f"boot program on {disk}: already starts Linux without waiting for a key")
        return
    if uboot.count(OLD) != 1:
        sys.exit("this U-Boot does not hold the expected default settings: not changed")
    if a.check:
        print(f"boot program on {disk}: waits 1 s for a key on the servo bus (not changed yet)")
        sys.exit(1)

    at = offset + uboot.find(OLD)
    pkg[at:at + len(OLD)] = NEW
    set_checksum(pkg, offset + 12, offset, length)
    set_checksum(pkg, 20, 0, valid_len)
    parse(pkg)

    os.makedirs(a.backup_dir, exist_ok=True)
    backup = os.path.join(a.backup_dir, f"boot-area-{os.path.basename(disk)}-{time.strftime('%Y%m%d-%H%M%S')}.img")
    with open(backup, "wb") as f:
        f.write(read_at(disk, 0, start + valid_len))
    new = os.path.join(a.backup_dir, "boot_package.nowait.fex")
    with open(new, "wb") as f:
        f.write(pkg)
    subprocess.run(["dd", f"if={new}", f"of={disk}", f"bs={BLOCK}", f"seek={PACKAGE_BLOCK}",
                    "conv=fsync,notrunc", "status=none"], check=True)
    with open("/proc/sys/vm/drop_caches", "w") as f:
        f.write("3\n")
    back = subprocess.run(["dd", f"if={disk}", f"bs={BLOCK}", f"skip={PACKAGE_BLOCK}",
                           f"count={-(-valid_len // BLOCK)}", "iflag=direct", "status=none"],
                          capture_output=True, check=True).stdout[:valid_len]
    if back != bytes(pkg):
        sys.exit(f"read-back differs from what was written: write the saved boot area {backup} back")
    print(f"boot program on {disk}: now starts Linux without waiting for a key (boot area saved as {backup})")


if __name__ == "__main__":
    main()
