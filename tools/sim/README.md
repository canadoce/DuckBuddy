# phoebe-sim: the whole duck on a Mac

One command runs the brain's services on your computer, with a web page standing in for the robot's
body: your browser's microphone is its ears, your browser's camera its eyes, your speakers its voice.

```bash
uv run tools/sim/phoebe_sim.py --open
```

Then on the page (http://127.0.0.1:8090) click **Speaker**, **Mic** and **Camera**. Use headphones:
with speakers the mic also hears the duck. Ctrl-C stops everything.

The first run builds robotd and sounds (`cargo build`), renders robotd's sound bank, downloads the
hearing models, onnxruntime for macOS and renders lifed's voice clips (needs `ffmpeg`, `brew install
ffmpeg`, and the internet). Later runs start in a few seconds; `--no-build` skips cargo.

## What runs

The same programs as on the Orange Pi ([deploy/brain](../../deploy/brain/README.md)), started with
the same flags except the paths:

| Service | On the Mac |
|---|---|
| robotd | `--fake` (no servo bus) with the policies from [policies](../../policies): the robot stands, sits, walks in place; `--fake-tilt` lets the page tip it over |
| lifed, voiced, visiond, duckweb | as on the brain |
| duckbrain, duckjev | as on the brain, on ports 18210 and 18211 |
| tofd | a stand-in inside the simulator: a slider sets the distance |

The hardware programs are stand-ins ([shim.py](shim.py)), first on the services' `PATH`:

| Program | Stand-in |
|---|---|
| `arecord` (voiced) | the browser's mic, 48 kHz; silence while the mic is off |
| `aplay` (robotd's voice, lifed's clips) | plays in the browser, at the real pace: a sound ends when it has been heard |
| `duckcam` (visiond) | the browser's camera, as 1920x1080 grey or NV12 frames: faces, motion, QR codes, Jev's photos |
| `amixer` | the volume lifed sets is applied to the page's sound |
| `nmcli` | a pretend Wi-Fi: the page lists the networks on the air; a Wi-Fi QR code shown to the camera joins one |
| `timedatectl`, `ip` | the clock is set; the address is 127.0.0.1 |

## The page

- **Senses**: speaker, mic (with a level meter) and camera, each on or off.
- **Talk without the mic**: typed words go to lifed exactly as voiced sends what it hears (same
  code), optionally as a named person.
- **Touch and noises**: pet its head, a loud noise from one side, any sound from robotd's bank.
- **ToF in the face**: nothing in front, or a distance.
- **Power**: the gamepad's Start and Stop (`robot.enable`). The simulator presses Start at launch.
- **Tilt the body**: upright, leaning, on its front, back or side, upside down. Laid down for a
  moment, robotd calls it a fall and lifed reacts.
- **Wi-Fi (pretend)**: the networks on the air, and which one is joined.
- **The phone page**: duckweb, as on your phone.
- **Services**: each one's state and a restart button; **Logs**: each one's output.
- **Inside**: robotd's `robot.state` and `robot.health`, lifed's `life.state`.

## Settings

The same files as on the brain:

| File | What |
|---|---|
| `~/.config/duck/persona.json` (or `$DUCK_PERSONA`) | the duck's name and character ([tools/persona](../persona/README.md)) |
| `~/.config/duckbrain/jev.env` | `DUCKBRAIN_SYSTEMONE_URL=http://<host>:<port>` for a local Jev |
| `~/.config/duckbrain/duckbrain.env` | `DUCKBRAIN_LLM=http://<host>:<port>/v1/chat/completions` for the chat LLM; without it the small brain answers |

Flags: `--port` (the page, 8090), `--open`, `--no-build`, `--no-policy` (robotd holds its pose and
lifed stays OFF), `--no-start` (do not press Start), `--seed` (the sound bank's voice),
`--jev-timeout` (lifed's wait for Jev, 2.5 s).

## Its files

| Where | What |
|---|---|
| `~/.local/state/phoebe-sim` | `logs/` (each service's log, lifed's trace, Jev's log), `voices.json` (the voice prints of the people it met), `sounds/` (robotd's bank), `robotd.toml`, `lifed-state.json`, `bin/` (the stand-ins) |
| `/tmp/phoebe-sim` | the sockets |
| `~/.cache/duckbuddy` | `hearing/` (Moonshine, VAD, denoisers, TitaNet), `voice-en-US-JennyNeural/` (lifed's clips, shared with deploy.sh), onnxruntime |

## Limits

- The fake robot has no physics: joints go where the policy sends them, the IMU reads the tilt set
  on the page, nothing walks away. Walking shows as the twist and odometry robotd reports.
- One mic channel, copied to both: sound direction always reads straight ahead.
- The page works on 127.0.0.1 only: browsers allow the mic and the camera on `localhost`, not on a
  LAN address without HTTPS.
- Not simulated: the gamepad (padd) and robotd's petting classifier (off on the brain too); use
  **Pet its head**.
