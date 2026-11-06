# Orange Pi Zero 3W A733 offline audio install

This guide covers the `TLV320AIC3104` on the [Robot HAT E1](https://code.caric.io/Robotics/elec_RPI_Robot_HAT), the head board of the robot,
on the Orange Pi Zero 3W (A733). It also sets up the servo UART and the I²C buses. The target system
is currently fixed to:

- Board: `orangepizero3w` / `sun60iw2`
- OS: Debian Trixie, server mode
- Kernel: `6.6.98-sun60iw2`
- HAT buses: TWI0 (I²C, `/dev/i2c-0`), I2S0, UART0 (servo bus, `/dev/ttyS0`), TWI2 (ToF, `/dev/i2c-2`)
- Codec address: TWI0 `0x18`
- Codec clock: the HAT's own 12 MHz oscillator; codec reset: an RC on the HAT (no GPIO)
- Amp: PAM8406, always on (no enable GPIO)

The pin table and the hardware notes are in [`docs/hardware/INTERFACE-CN.md`](../../docs/hardware/INTERFACE-CN.md).

`scripts/setup-board.sh` is only for the Radxa Zero 3W/RK3566. Do not run it on the
A733. It uses `/boot/armbianEnv.txt`, `ttyS5` and the `rk35xx` kernel, while the
A733 uses `/boot/orangepiEnv.txt` and the `sun60iw2` kernel. The script detects the A733 and
stops, so it cannot change the wrong files.

## 1. Prepare the source archive on your computer

The board does not need access to GitHub and should not access it directly. Run these
commands in PowerShell on your Windows computer:

```powershell
Set-Location <repo>

git clone --bare --branch kernel-sun60iw2-6.6 --single-branch `
  https://github.com/scallopmuscle/linux-kernel.git `
  tools/reference/linux-kernel-sun60iw2-6.6.git

git --git-dir=tools/reference/linux-kernel-sun60iw2-6.6.git `
  rev-parse e3ee05f508bd6db1026cf1e7012c2eeb128da410

git -c core.protectNTFS=false `
  --git-dir=tools/reference/linux-kernel-sun60iw2-6.6.git `
  archive --format=tar.gz `
  --prefix=linux-sun60iw2-6.6.98/ `
  --output=tools/cache/a733/linux-sun60iw2-6.6.98-e3ee05f.tar.gz `
  e3ee05f508bd6db1026cf1e7012c2eeb128da410

Get-FileHash -Algorithm SHA256 `
  tools/cache/a733/linux-sun60iw2-6.6.98-e3ee05f.tar.gz
```

The archive made from this commit is `342785029` bytes, and its SHA256 is
`AB72B32F6B9A91FC3210EB2B6A53923235C549CE8E6915ACEA01CF6BB7B21D13`.
After the transfer, check it again on the board with `sha256sum`.

Keep `-c core.protectNTFS=false`. The kernel tree has a file named `aux.c`. By default,
Git for Windows treats this name as a reserved Windows device name and refuses to archive it.

The source is a third-party snapshot of the A733 kernel, not the official Orange Pi repository:

- Repository: `scallopmuscle/linux-kernel`
- Branch: `kernel-sun60iw2-6.6`
- Commit: `e3ee05f508bd6db1026cf1e7012c2eeb128da410`
- Commit message: `fix: restore missing arch/arm64/kernel/vmlinux.lds.S`

If a production image uses a different kernel, get the source that matches it exactly and
rebuild the modules. Do not copy the `.ko` files built here to a system with a different `uname -r`.

## 2. Copy from your computer to the board

First, create the directory on the board:

```powershell
ssh orangepi@<robot-ip> \
  "mkdir -p /home/orangepi/microduck-offline/kernel"
```

Then copy the full source archive and this repo's audio directory from your computer. The
commands ask for the board's password:

```powershell
& 'C:\Program Files\PuTTY\pscp.exe' `
  tools/cache/a733/linux-sun60iw2-6.6.98-e3ee05f.tar.gz `
  orangepi@<robot-ip>:/home/orangepi/microduck-offline/kernel/

& 'C:\Program Files\PuTTY\pscp.exe' -r `
  deploy/audio `
  orangepi@<robot-ip>:/home/orangepi/microduck-offline/
```

On the first connection, compare the SSH host fingerprint shown with the board fingerprint you
already confirmed on your computer. Do not accept it without checking.

## 3. Install on the board

If the Debian package sources are reachable, first install the build dependencies. This step
does not access GitHub:

```bash
sudo apt update
sudo apt install -y \
  build-essential bc flex bison libssl-dev libelf-dev dwarves \
  device-tree-compiler i2c-tools alsa-utils
```

Then run the offline installer:

```bash
cd /home/orangepi/microduck-offline
sha256sum kernel/linux-sun60iw2-6.6.98-e3ee05f.tar.gz
sudo sh audio/install-aic3104-a733.sh --hat robothat-e1 \
  kernel/linux-sun60iw2-6.6.98-e3ee05f.tar.gz
sudo reboot
```

The installer does the following:

1. checks the board model and the running kernel version;
2. prepares the kernel tree from the local archive;
3. builds and installs two modules: the AIC3X core and the I2C module;
4. compiles `aic3104-a733-robothat.dts` as the `microduck-aic3104` overlay and adds it to
   `/boot/orangepiEnv.txt`: the codec on TWI0 with no reset GPIO (TWI0 at 400 kHz, which also
   carries the body IMU, a BNO055 on Qwiic J5), the codec told its MCLK is 12 MHz, I2S0 without PB4
   (it goes to the HAT's Qwiic J6), TWI2 for the ToF on Qwiic J8, and UART0 on PB9/PB10;
5. installs and enables `aic3104-a733-robothat.service` as `aic3104-a733.service`: the codec bus is found in
   sysfs, the mics are J2 (left) and J9 (right), and the line output gain is 0 dB (the PAM8406 clips
   at +9 dB with a full-scale signal);
6. sets `console=display` in `/boot/orangepiEnv.txt` and masks `serial-getty@ttyS0.service`, so
   Linux does not write to the servo bus. U-Boot still prints its boot messages on UART0 at
   115200 baud before Linux starts.

The UART stays on its stock 24 MHz clock: 500 kbit/s is 24 MHz / 16 / 3, exact.

After the reboot, install the robot's robotd config. It sets the servo port (`/dev/ttyS0`) and the
BNO055 as the IMU (`imu_source = "bno055"` on `/dev/i2c-0`); finish its `joint_ids`, `joint_offsets`
and `imu_axes` with `tools/bringup`:

```bash
sudo cp deploy/robots/opi-hl2915-robothat-e1.toml /etc/robot/robotd.toml
```

## 4. Checks

```bash
uname -r
modinfo snd-soc-tlv320aic3x-i2c | grep -E 'filename|vermagic'
lsmod | grep snd_soc_tlv320aic3x
ls /sys/bus/i2c/devices/*-0018          # the codec, bound by the driver
journalctl -u aic3104-a733.service -b --no-pager
aplay -l; arecord -l                     # card "aic3104"
i2cdetect -y 0                           # TWI0: codec 0x18 (UU), BNO055 0x28, INA226 0x45, LSM6DSV16X 0x6a
i2cdetect -y 2                           # the ToF on J8 (0x29 for the VL53L5CX)
fuser -v /dev/ttyS0                      # nothing but robotd
python3 tools/robot-tests/ping_all.py 50 /dev/ttyS0   # with robotd stopped
```

Expected:

- the kernel and `vermagic` are both `6.6.98-sun60iw2`;
- both `snd_soc_tlv320aic3x` modules are loaded;
- `0x18` shows as `UU` on bus 0, because the kernel driver uses it;
- the service is `active (exited)`, and its log does not say `not detected`.

Even with no codec found, ASoC may register a logical sound card named `aic3104`. So seeing this
card in `aplay -l` alone does not prove that the codec works. Last, check on the real hardware:

- playback through the speaker, and a mute test;
- a recording from each of the two mic inputs (J2 left, J9 right), to confirm the `LINE1` routing;
- a cold boot test;
- a stability test of the 5 V and 3.3 V supplies while the speaker plays.

## 5. Other robot software on the A733

This guide covers the A733 board interfaces and the AIC3104 bring-up. The robot software has more
platform differences:

- robotd's servo port is `/dev/ttyS0`; the robot config above sets it;
- `mediad` currently uses the Rockchip `mpph264enc`. The A733 has the `/dev/cedar_dev*` kernel
  nodes, but the Allwinner user-space hardware encoding pipeline is not verified yet;
- the `.rknn` detection models are for RK3566/RKNN. On the A733, use CPU ONNX first, or port
  them to the A733 NPU separately.

Do not run `scripts/setup-gstreamer.sh` or `scripts/setup-npu.sh` on the A733. Both are
Rockchip-only for now.
