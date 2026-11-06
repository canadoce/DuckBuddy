# Orange Pi Zero 3W A733 offline audio install

This guide covers the `TLV320AIC3104` on the MicroDuck Orange Pi Zero 3W A733 HAT.
The target system is currently fixed to:

- Board: `orangepizero3w` / `sun60iw2`
- OS: Debian Trixie, server mode
- Kernel: `6.6.98-sun60iw2`
- HAT buses: I2C2, I2S0, UART7
- Codec address: I2C2 `0x18`
- Codec reset: PB0, active low
- Amp enable: PB3, active high

`scripts/setup-board.sh` is only for the Radxa Zero 3W/RK3566. Do not run it on the
A733. It uses `/boot/armbianEnv.txt`, `ttyS5` and the `rk35xx` kernel, while the
A733 uses `/boot/orangepiEnv.txt`, `ttyS7` and the `sun60iw2` kernel. The script now
detects the A733 and stops, so it cannot change the wrong files.

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
sudo sh audio/install-aic3104-a733.sh \
  kernel/linux-sun60iw2-6.6.98-e3ee05f.tar.gz
sudo reboot
```

The installer does the following:

1. checks the board model and the running kernel version;
2. prepares the kernel tree from the local archive;
3. builds and installs two modules: the AIC3X core and the I2C module;
4. builds and installs the `microduck-aic3104` DT overlay;
5. adds the overlay to `/boot/orangepiEnv.txt`;
6. installs and enables `aic3104-a733.service`.

## 4. Checks without the HAT

With no physical HAT connected, this is the correct state:

```bash
uname -r
modinfo snd-soc-tlv320aic3x-i2c | grep -E 'filename|vermagic'
lsmod | grep snd_soc_tlv320aic3x
systemctl status aic3104-a733.service --no-pager
cat /sys/class/leds/microduck-amp-enable/brightness
```

Expected:

- the kernel and `vermagic` are both `6.6.98-sun60iw2`;
- both `snd_soc_tlv320aic3x` modules are loaded;
- the service is `active (exited)`;
- the log says `TLV320AIC3104 not detected on I2C2`;
- the amp enable value (PB3) is `0`.

Even with no physical codec, ASoC may register a logical sound card named `aic3104`. So
seeing this card in `aplay -l` alone does not prove that the HAT is connected.

## 5. Checks with the HAT

Power off, fit the HAT, power on again, then check these in order:

```bash
i2cdetect -y 2
journalctl -u aic3104-a733.service -b --no-pager
cat /sys/class/leds/microduck-amp-enable/brightness
aplay -l
arecord -l
```

Expected: `0x18` shows as `UU`, because the kernel driver uses it. The init log no longer
says `not detected`, and the amp enable becomes `1`. Last, these tests must be done on the
real hardware:

- playback on the left and right channels, and a mute test;
- a recording from each of the two mic inputs, to confirm the `MIC2`/`LINE1` routing;
- MCLK, BCLK and LRCK checked with an oscilloscope;
- a reset test and a cold boot test;
- a stability test of the 5 V, 3.3 V and 1.8 V supplies while the speaker plays.

## 6. Non-audio interfaces already verified

These system nodes are verified on the current prototype:

- UART7: `/dev/ttyS7`
- I2C2: `/dev/i2c-2`
- USB camera: `/dev/video0`, driver `uvcvideo`
- GPU render node: `/dev/dri/renderD128`
- EGL/OpenGL ES: PowerVR B-Series BXM-4-64, OpenGL ES 3.2
- Vulkan: PowerVR proprietary driver, Vulkan 1.3

These results show that the drivers and the pinmux are enabled. They do not replace the
electrical tests of the first HAT built. The only known failed systemd unit at the moment is
`smartmontools.service`. It is not related to the HAT, the GPU, the camera or the sound card.

## 7. Robot software migration not yet included

This guide covers the A733 board interfaces and the AIC3104 bring-up. It does not mean that the
current Radxa software image can be deployed to the Orange Pi as it is. The robot software has
at least three more platform differences:

- the repo default for `robotd` is still `/dev/ttyS5`; the A733 prototype must use `/dev/ttyS7`;
- `mediad` currently uses the Rockchip `mpph264enc`. The A733 has the `/dev/cedar_dev*` kernel
  nodes, but the Allwinner user-space hardware encoding pipeline is not verified yet;
- the `.rknn` detection models are for RK3566/RKNN. On the A733, use CPU ONNX first, or port
  them to the A733 NPU separately.

So after the sound card passes its hardware checks, the A733 app config and the media
performance still need their own work and checks. Do not run `scripts/setup-gstreamer.sh` or
`scripts/setup-npu.sh` on the A733. Both are Rockchip-only for now.

## 8. Robot HAT E1 instead of the HAT R3E

The Robot HAT E1 (`elec_RPI_Robot_HAT`) has the codec on TWI0 with its own 12 MHz oscillator and an RC
reset, an always-on PAM8406 amp, and the servo bus on UART0 (header pins 8/10). The pin table and the
hardware notes are in [`docs/hardware/INTERFACE-CN.md`](../../docs/hardware/INTERFACE-CN.md), section 6.

Install with the same kernel source archive as in sections 1 to 3, and add `--hat robothat-e1`:

```bash
cd /home/orangepi/microduck-offline
sudo sh audio/install-aic3104-a733.sh --hat robothat-e1 \
  kernel/linux-sun60iw2-6.6.98-e3ee05f.tar.gz
sudo reboot
```

Compared with the R3E install, the installer:

1. compiles `aic3104-a733-robothat.dts` as the `microduck-aic3104` overlay: the codec on TWI0 with no
   reset GPIO (TWI0 at 400 kHz, which also carries the body IMU, a BNO055 on Qwiic J5), the codec told its MCLK is 12 MHz, I2S0 without PB4 (it goes to the HAT's Qwiic J6),
   TWI2 for the ToF on Qwiic J8, and UART0 on PB9/PB10;
2. installs `aic3104-a733-robothat.service` as `aic3104-a733.service`: the codec bus is found in
   sysfs, the mics are J2 (left) and J9 (right), and the line output gain is 0 dB (the PAM8406 clips
   at +9 dB with a full-scale signal);
3. sets `console=display` in `/boot/orangepiEnv.txt` and masks `serial-getty@ttyS0.service`, so
   Linux does not write to the servo bus. U-Boot still prints its boot messages on UART0 at
   115200 baud before Linux starts.

The UART stays on its stock 24 MHz clock: 500 kbit/s is 24 MHz / 16 / 3, exact.

After the reboot, install the robot's robotd config. It sets the servo port (`/dev/ttyS0`) and the
BNO055 as the IMU (`imu_source = "bno055"` on `/dev/i2c-0`); finish its `joint_ids`, `joint_offsets`
and `imu_axes` with `tools/bringup`:

```bash
sudo cp deploy/robots/opi-hl2915-robothat-e1.toml /etc/robot/robotd.toml
```

Then check:

```bash
ls /sys/bus/i2c/devices/*-0018          # the codec, bound by the driver
journalctl -u aic3104-a733.service -b --no-pager
aplay -l; arecord -l                     # card "aic3104"
i2cdetect -y 0                           # TWI0: codec 0x18 (UU), BNO055 0x28, INA226 0x45, LSM6DSV16X 0x6a
i2cdetect -y 2                           # the ToF on J8 (0x29 for the VL53L5CX)
fuser -v /dev/ttyS0                      # nothing but robotd
python3 tools/robot-tests/ping_all.py 50 /dev/ttyS0   # with robotd stopped
```

To use the onboard MEMS mic instead of J2/J9, set `Environment=AIC3104_MIC_ROUTE=mic2r-both` in
`/etc/systemd/system/aic3104-a733.service`. The MEMS mic is a single mic, so the sound direction
(`tools/voiced/doa.py`) does not work with it.

Still to test on the hardware: playback and both mic inputs, the boot messages on the servo bus
(the servos should ignore them), the ToF on J8, and the BNO055 on J5 (robotd's journal says
"BNO055 in IMU fusion mode"; the bring-up tool's IMU test checks rate, noise and calibration).
