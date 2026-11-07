# The brain: Orange Pi Zero 3W + Robot HAT E1

The brain is the head board of the DuckBuddy: an Orange Pi Zero 3W (Allwinner A733) on the
Orange Pi 1.0.2 Debian 13 image (kernel `6.6.98-sun60iw2`), wired to the
[Robot HAT E1](https://code.caric.io/Robotics/elec_RPI_Robot_HAT). Pins, power and buses:
[docs/hardware/INTERFACE-CN.md](../../docs/hardware/INTERFACE-CN.md).

## Deploy

From your computer, in the repo (needs `cargo board`, `uv` and `ffmpeg`):

```bash
deploy/brain/deploy.sh <user@host> --install    # first time: board setup + software, then reboot
deploy/brain/deploy.sh <user@host>              # later: build, copy, restart the services
```

`--install` runs `install.sh` on the board with sudo. Run it again when `overlay/` or `rootfs/` change.
After the first `--install`, reboot once (`sudo reboot`): the overlay and the codec driver load at boot.
`BRAIN_SSH_OPTS` passes extra ssh options; `ROBOT_CONFIG` picks the config from
[deploy/robots](../robots) on the first deploy (default `opi-hl2915-robothat-e1.toml`).

## What install.sh sets up (system, needs sudo)

| Part | What | Files |
|---|---|---|
| Overlay | codec TLV320AIC3104 on TWI0 (`/dev/i2c-0`, 0x18), the I2S sound card `aic3104`, TWI2 for the Qwiic J8 (`/dev/i2c-2`), UART0 for the servos (`/dev/ttyS0`, 96 MHz clock: exact 1 Mbaud and 500 kbaud) | `overlay/brain.dts` → `/boot/overlay-user/brain.dtbo` |
| Codec driver | `snd-soc-tlv320aic3x(-i2c)`, built from the matching kernel source (the image has it off) | `/lib/modules/6.6.98-sun60iw2/extra` |
| Audio | mixer levels and routing at boot, alsamixer works (`alsamixer -c aic3104`); shared devices `duck_out` (dmix) and `duck_in` (dsnoop) | `brain-audio-init`, `brain-audio.service`, `/etc/default/brain-audio`, `/etc/asound.conf` |
| Battery guard | INA226 on the HAT: warns, then shuts the board down at 9.9 V (3S) | `/opt/brain/battery_guard.py`, `brain-battery-guard.service` |
| Camera | vin modules at boot; `camgrab` with the IMX219 tuning file | `/etc/modules-load.d/brain-camera.conf`, `/opt/brain/camera` |
| Reboot fix | the SD card's power is cut for 0.5 s on reboot (it stays in 1.8 V mode otherwise and the board does not come back) | `/usr/lib/systemd/system-shutdown/sd-card-power-cycle` |
| Devices, groups | `/dev/duck-servos`, i2c / gpio groups; the user joins dialout, i2c, gpio, audio, video, netdev and robot (the daemons' sockets); lingering on | `/etc/udev/rules.d/99-brain.rules` |
| Wi-Fi from a QR code | NetworkManager allowed for group netdev (polkit) | `/etc/polkit-1/rules.d/50-brain-nm.rules` |
| Packages | Python numpy, OpenCV and pyserial (tools/bringup), venv, build tools for the driver | |

It also removes the earlier opi-robot-hat setup (robot-hat-* services, `/opt/robot-hat`, the Cone
Radio web app, kept as `~/board-demos-backup-*.tgz`).

Audio levels in `/etc/default/brain-audio` (then `sudo systemctl restart brain-audio`):
`BRAIN_PCM_VOLUME` (DAC, default 103 = −12 dB), `BRAIN_LOP_GAIN` (line out, default 0 dB),
`BRAIN_MIC_GAIN` (mic PGA, default 72 = +36 dB). The speaker is on RIGHT_LOP; the onboard mic is on
MIC2R and feeds both capture channels.

## What deploy.sh installs (the login user, no sudo)

| Where | What |
|---|---|
| `~/robot` | `robotd`, `tofd`, `robotctl`, `sounds`, the robot configs, `active.toml` → the chosen config, `robotd.env`, onnxruntime 1.28.3, `recs/` (service logs) |
| `~/lifed` `~/voiced` `~/visiond` `~/duckweb` `~/persona` | the Python services from [tools](../../tools); `~/lifed/voice` the voice clips (rendered on your computer with edge-tts); `~/visiond/duckcam` built on the board |
| `~/voiced/.venv` | sherpa-onnx (system numpy) |
| `~/models/asr-sensevoice` | SenseVoice-Small int8, silero VAD, gtcrn denoiser |
| `/var/lib/robot/sounds` | robotd's sound bank (`sounds ensure-bank`) |
| `~/.config/systemd/user` | the user units: [units](units/README.md) |

The services: robotd (the body), tofd (the ToF in the face, on J8), lifed (the life layer),
voiced (the ears), visiond (the eyes), duckweb (the phone page, `http://<brain>:8088`).

**While the legs are not built**, `~/robot/robotd.env` holds `ROBOTD_ARGS="--fake --no-policy"`:
robotd runs without the servo bus and nothing moves, but the sounds, the voice, the camera, the ToF
and the phone page all work. Empty `ROBOTD_ARGS` once the servo IDs and the zero pose are set with
[tools/bringup](../../tools/bringup/README.md). deploy.sh never overwrites `robotd.env`.

Not started by deploy.sh: padd (the gamepad, it walks the robot) and frpc (the tunnel to the
duckbrain voice server).

## Checks

```bash
aplay -l                                    # card aic3104
speaker-test -D duck_out -c 2 -t sine -f 1000 -l 1
arecord -D duck_in -f S16_LE -r 48000 -c 2 -d 3 /tmp/mic.wav
i2cdetect -y 2                              # 0x29: the ToF on J8
systemctl --user status robotd-dev tofd-dev lifed-dev voiced-dev visiond-dev duckweb-dev
tail -f ~/robot/recs/voiced-service.log     # what it hears
```
