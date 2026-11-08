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
| Reboot fix | the SD card's power is cut for 1 s on reboot, and switched back on until the PMIC reads it on (the card stays in 1.8 V mode otherwise and the board does not come back; the fan, on the same switch, pauses). A board that still stays off after a reboot needs a power cycle | `/usr/lib/systemd/system-shutdown/sd-card-power-cycle` |
| Boot program | U-Boot starts Linux without waiting for a key on the servo bus (`bootdelay=-2` in its built-in settings), so a servo that holds the data line low no longer stops the boot. The card's boot area is saved first. See [Boot program](#boot-program) | `uboot_nowait.py` → the card's boot package (8 KiB × 2050), backup in `/var/backups/brain-uboot` |
| Devices, groups | `/dev/duck-servos`, i2c / gpio groups; the user joins dialout, i2c, gpio, audio, video, netdev and robot (the daemons' sockets); lingering on | `/etc/udev/rules.d/99-brain.rules` |
| Wi-Fi from a QR code | NetworkManager allowed for group netdev (polkit) | `/etc/polkit-1/rules.d/50-brain-nm.rules` |
| Packages | Python numpy, OpenCV and pyserial (tools/bringup), FastAPI, uvicorn and soundfile (duckbrain), venv, build tools for the driver | |

It also removes the earlier opi-robot-hat setup (robot-hat-* services, `/opt/robot-hat`, the Cone
Radio web app, kept as `~/board-demos-backup-*.tgz`).

Audio levels in `/etc/default/brain-audio` (then `sudo systemctl restart brain-audio`):
`BRAIN_PCM_VOLUME` (DAC, default 103 = −12 dB), `BRAIN_LOP_GAIN` (line out, default 0 dB),
`BRAIN_MIC_GAIN` (mic PGA, default 72 = +36 dB). The speaker is on RIGHT_LOP; the onboard mic is on
MIC2R and feeds both capture channels.

## Boot program

The image's U-Boot keeps its console on UART0, which is the servo bus, and waits one second for
"any key" there before it starts Linux. A servo that holds the data line low (a faulty one does)
reads as a key press: U-Boot stops at its prompt, the fan spins and the board never boots.
U-Boot reads no saved settings on this image, so `uboot_nowait.py` changes its built-in
`bootdelay=1` to `bootdelay=-2` (start at once, do not check for a key) and fixes U-Boot's own
checksum and the package checksum. It changes only a U-Boot that holds exactly the expected settings, and
does nothing when it is already changed.

```bash
sudo python3 deploy/brain/uboot_nowait.py --check   # on the board: is it changed?
```

To undo it, write the saved boot package back (on the board, or on the Mac with the card in a
reader and `/dev/rdiskN` in place of `/dev/mmcblk1`):

```bash
sudo dd if=/var/backups/brain-uboot/boot-area-mmcblk1-<time>.img of=/dev/mmcblk1 bs=8k \
    skip=2050 seek=2050 count=170 conv=fsync
```

Re-installing the bootloader from Orange Pi's tools (`orangepi-config`) also puts the original
back; run `install.sh` again afterwards.

## What deploy.sh installs (the login user, no sudo)

| Where | What |
|---|---|
| `~/robot` | `robotd`, `tofd`, `robotctl`, `sounds`, the robot configs, `active.toml` → the chosen config, `robotd.env`, onnxruntime 1.28.3, `recs/` (service logs) |
| `~/lifed` `~/voiced` `~/visiond` `~/duckweb` `~/duckbrain` `~/persona` | the Python services from [tools](../../tools); `~/lifed/voice` the voice clips (rendered on your computer with edge-tts); `~/visiond/duckcam` built on the board |
| `~/voiced/.venv` | sherpa-onnx (system numpy) |
| `~/models/hearing` | Moonshine v2 base English (speech to text), silero VAD, DPDFNet and GTCRN denoisers, NVIDIA TitaNet-small (voice prints) |
| `/var/lib/robot/sounds` | robotd's sound bank (`sounds ensure-bank`) |
| `~/.config/systemd/user` | the user units: [units](units/README.md) |

The services: robotd (the body), tofd (the ToF in the face, on J8), lifed (the life layer),
voiced (the ears), visiond (the eyes), duckweb (the phone page, `http://<brain>:8088`), duckbrain
(the online brain, `127.0.0.1:8210`) and duckjev (Jev's judgments for duckbrain, `127.0.0.1:8211`).

**Who is speaking**: voiced knows people by their voice once they introduce themselves to the duck:
"Phoebe, my name is Rafael" (or "call me Rafael"). Later phrases that match the voice well teach it
more. The voice prints live in `~/.config/duck/voices.json` (`$DUCK_VOICES` names another file); manage them with
`~/voiced/.venv/bin/python ~/voiced/voices.py list | forget NAME | add NAME a.wav ... | who a.wav`
(16 kHz mono wavs). voiced's log shows the name and score of each phrase (`heard: ... - Rafael (0.81)`);
`THRESHOLD` in `tools/voiced/voices.py` is the score a phrase needs.

**duckbrain and Jev** read their settings from `~/.config/duckbrain`, files you write (deploy.sh
never does), one `NAME=value` per line, then `systemctl --user restart duckjev-dev duckbrain-dev`:

| File | Setting | What |
|---|---|---|
| `jev.env` | `DUCKBRAIN_SYSTEMONE_URL=http://<host>:<port>` | a System One server of your own (no key, trusted network only); Box questions are left out unless `DUCKBRAIN_JEV_BOX=1` |
| `jev.env` | `TYPESAFE_API_KEY=...` | TypeSafe's hosted Jev instead (needs `typesafe-sdk`, not installed here) |
| `duckbrain.env` | `DUCKBRAIN_LLM=http://<host>:<port>/v1/chat/completions` | the OpenAI-style chat LLM (text and images) for the duck's replies; `DUCKBRAIN_LLM_MODEL` pins the model |

Without them each part falls back: no Jev, lifed keeps to its rules; no LLM, the offline small brain
answers. A local Jev slower than TypeSafe's (about 0.4 s) needs lifed to wait longer: put
`LIFED_ARGS="--jev-timeout 2.5"` in `~/robot/lifed.env` (deploy.sh writes it empty once and never
overwrites it), then restart lifed-dev.

**While the legs are not built**, `~/robot/robotd.env` holds `ROBOTD_ARGS="--fake --no-policy"`:
robotd runs without the servo bus and nothing moves, but the sounds, the voice, the camera, the ToF
and the phone page all work. Empty `ROBOTD_ARGS` once the servo IDs and the zero pose are set with
[tools/bringup](../../tools/bringup/README.md). deploy.sh never overwrites `robotd.env`.

Not started by deploy.sh: padd (the gamepad, it walks the robot) and frpc (the tunnel to a
duckbrain on another machine; not needed with duckbrain on the brain).

## Checks

```bash
aplay -l                                    # card aic3104
speaker-test -D duck_out -c 2 -t sine -f 1000 -l 1
arecord -D duck_in -f S16_LE -r 48000 -c 2 -d 3 /tmp/mic.wav
i2cdetect -y 2                              # 0x29: the ToF on J8
systemctl --user status robotd-dev tofd-dev lifed-dev voiced-dev visiond-dev duckweb-dev duckjev-dev duckbrain-dev
curl -s 127.0.0.1:8210/health                # duckbrain: llm and jev
tail -f ~/robot/recs/voiced-service.log     # what it hears
```
