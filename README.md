<h1 align="center">DuckBuddy</h1>

<p align="center"><b>An open-source embodied AI robot duck — it walks, hears, sees, and has a life of its own.</b></p>

<p align="center">🦆 <b>Make DuckBuddy your real-life buddy duck.</b></p>

<p align="center">
<a href="https://github.com/Animan-AI/DuckBuddy/actions/workflows/ci.yml"><img src="https://github.com/Animan-AI/DuckBuddy/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="Apache-2.0">
<img src="https://img.shields.io/badge/board-Orange%20Pi%20Zero%203W-orange" alt="Orange Pi Zero 3W">
<img src="https://img.shields.io/badge/servos-Feetech%20HL--2915-green" alt="Feetech HL-2915">
</p>

https://github.com/user-attachments/assets/7dd5c290-7b48-4f87-a991-7aab6c25632f

<p align="center"><sub>A string of spoken instructions, done one move after another (recorded on the robot, 2026-10-17; it has sound — unmute the player).</sub></p>

<details>
<summary>📱 No video in the GitHub app? Open the GIF</summary>

<p align="center"><img src="docs/media/demo.gif" width="480" alt="Demo GIF (3× speed)"></p>

<p align="center"><sub>3× speed, no sound. The full video: <a href="https://github.com/Animan-AI/DuckBuddy/raw/main/docs/media/demo.mp4">download demo.mp4</a> (5.7 MB), or open this page in a browser.</sub></p>

</details>

This is not just another robot duck. DuckBuddy brings **motion, perception, voice and a life layer** together
in one open system that you can **build and improve** — and all of it runs on the robot itself, without a
phone or the cloud.

<sub>DuckBuddy is built on [Pollen Robotics' Microduck](https://github.com/pollen-robotics/microduck). It is an independent community project, **not** affiliated with or endorsed by Pollen Robotics; "Microduck" is their name for their robot. See [NOTICE](NOTICE).</sub>

## What makes DuckBuddy special?

- 🦆 **Motion** — Reinforcement-learning policies retrained for our Feetech HL-2915 servos: walking, getting up after a fall, sitting down and standing up, a forward roll (trained in sim). A 50 Hz loop that guards against falls, heat, a flat battery and a lost link
- 👂 **Hearing** — Offline speech recognition (SenseVoice) with denoising and voice detection; two microphones in the head tell which side a voice came from, so it turns to look when you call it
- 👀 **Vision** — Notices faces and things that move and turns to look, naturally (being tested on the robot); joins Wi-Fi from a QR code; "what is this?" answered by a multimodal model when online
- 🧭 **Autonomy** — A mission layer: say a string of moves ("two steps forward, turn around, sit down") and it plans and does them in turn; walking a spoken route is being tested on the robot
- 💗 **A life layer** — Drives and moods; it tires, rests and keeps its servos cool (a hot head moves less); it answers in duck-speak rather than a text-to-speech voice; its name and character live in one persona file — swap it and you have a different duck

## Architecture

One picture of how it fits together: **perception** (hearing, vision, distance) reports events to the
**life layer**, `lifed`, which decides where to look, what to do and what to say, and hands its intents to
**robotd**, the only process that drives the servos. The gamepad outranks `lifed`. Online, `lifed` asks a
**brain server** (a multimodal LLM) through an frp tunnel; offline, its own small brain answers. Every
service runs on its own on the Orange Pi and they talk JSON over local Unix sockets.

<p align="center"><img src="docs/media/arch-software-en.png" width="900" alt="Software architecture"></p>

<details>
<summary>For developers: the editable Mermaid diagram</summary>

```mermaid
flowchart TB
  subgraph ROBOT["On the robot · Orange Pi (Linux)"]
    subgraph SENSE["Senses"]
      VOICED["voiced · Python<br/>denoise · VAD · SenseVoice offline ASR<br/>sound direction from two mics"]
      VISIOND["visiond · Python + duckcam<br/>faces (YuNet) · motion · Wi-Fi QR · photos"]
      TOFD["tofd · Rust<br/>8×8 ranging"]
    end
    LIFED["lifed · Python · the life layer<br/>states · drives and moods · attention<br/>missions · offline small brain · head · voice prompts"]
    PERSONA[("persona JSON<br/>name · character · voice")]
    DUCKWEB["duckweb · Python<br/>phone page :8088"]
    PADD["padd · Rust<br/>Xbox pad"]
    ROBOTD["robotd · Rust · 50 Hz<br/>ONNX policies: walk · stand up · sit · roll<br/>safety: falls · heat · battery · deadman"]
  end
  HW["15 servos · IMU · speaker"]
  BRAIN["duckbrain · GPU server (optional)<br/>multimodal LLM: talk · look · judge"]
  TRAIN["Training · GPU<br/>mjlab · BAM actuator identification"]

  VOICED -- "calls / speech (with direction)" --> LIFED
  VISIOND -- "faces · motion · QR codes" --> LIFED
  TOFD -- "distance ahead" --> LIFED
  TOFD -- "someone close" --> VISIOND
  LIFED -- "watch · scan · snap" --> VISIOND
  PERSONA -.-> VOICED
  PERSONA -.-> LIFED
  DUCKWEB <-- "state · volume · missions" --> LIFED
  LIFED -- "JSON-RPC: move · skills · head · sounds · rest" --> ROBOTD
  ROBOTD -- "pose · temperatures · battery · odometry" --> LIFED
  PADD -- "JSON-RPC: driving" --> ROBOTD
  ROBOTD -- "Feetech bus · 500 kbps" --> HW
  LIFED <-. "frp tunnel: talk · look" .-> BRAIN
  PERSONA -.-> BRAIN
  TRAIN -. "ONNX policies" .-> ROBOTD
```

</details>

## Hardware & Software

### Hardware at a glance

| | Microduck | DuckBuddy |
|---|---|---|
| Main board | Radxa Zero 3W (RK3566, 1 GB) | **Orange Pi Zero 3W** (Allwinner A733: 2×A76 + 6×A55, 4 GB, 3 TOPS NPU) |
| Servos | 15 × Dynamixel XL330 (2S) | 15 × **Feetech HL-2915** (3S); HD-1910 (2S) on the way |
| Carrier board | Pollen's hat | the [**Robot HAT E1**](https://code.caric.io/Robotics/elec_RPI_Robot_HAT) (XT60 battery input, battery monitor, 5 V supply, two servo ports, audio codec, microphones, speaker amp, Qwiic ports) and a **BNO055** body IMU |
| Sensors | IMU | IMU, two microphones, IMX219 camera, 8×8 ToF ranging |
| Policies | Pollen's | **retrained for the HL-2915**, in `training/` |
| Behaviour | a gamepad or the app | a **life layer** on the robot, in `tools/lifed` |

The 3S battery plugs into the XT60 of the [Robot HAT E1](https://code.caric.io/Robotics/elec_RPI_Robot_HAT) in the head. The HAT measures the
battery, fuses it, brings it down to 5 V for the Orange Pi, and feeds the servos the battery voltage
on its two servo ports: one leg on each port, the head chain joined to one of them with a Y-cable. All
15 servos share one bus on the Orange Pi's UART0. The HAT also does the sound (two microphones in, a
speaker out) and has the Qwiic ports for the ToF in the face and the BNO055 IMU in the body.

<details>
<summary>For developers: the editable Mermaid diagram</summary>

```mermaid
flowchart LR
  BAT["Battery 3S<br/>LiPo / LiHV"] -- "XT60" --> PWR
  subgraph HEAD["Head"]
    subgraph HAT["Robot HAT E1"]
      PWR["INA226 battery monitor · 10 A fuse<br/>5 V buck"]
      PORTS["Servo ports A / B"]
      CODEC["Audio codec<br/>TLV320AIC3104"]
      AMP["Amplifier<br/>PAM8406"]
    end
    OPI["Orange Pi Zero 3W<br/>Allwinner A733 · 4 GB · 3 TOPS NPU"]
    HSERVO["Head 5 × HL-2915<br/>neck · head · beak"]
    MIC["Microphones × 2<br/>left / right"]
    SPK["Speaker"]
    TOF["ToF 8×8<br/>VL53L5CX"]
    CAM["Camera<br/>IMX219"]
  end
  subgraph BODY["Body"]
    LLEG["Left leg<br/>5 × HL-2915"]
    RLEG["Right leg<br/>5 × HL-2915"]
    IMU["IMU<br/>BNO055"]
  end
  PWR -- "5 V" --> OPI
  PWR -- "battery" --> PORTS
  OPI -- "UART0 · 500 kbps" --> PORTS
  PORTS -- "port A · power + bus" --> LLEG
  PORTS -- "port B · power + bus" --> RLEG
  PORTS -- "Y-cable" --> HSERVO
  OPI -- "I2S + I²C" --> CODEC
  OPI -- "I²C · Qwiic J8" --> TOF
  OPI -- "I²C · Qwiic J5" --> IMU
  CAM -- "MIPI CSI" --> OPI
  MIC --> CODEC
  CODEC --> AMP --> SPK
  OPI -. "Wi-Fi / Bluetooth" .-> EXT["Phone page · Xbox pad<br/>brain server (optional)"]
```

</details>

### Software stack

| Service | Language | What it does |
|---|---|---|
| `robotd` | Rust | the 50 Hz control loop running ONNX policies; Feetech HLS bus driver, battery identification (2S/3S, LiPo/LiHV), heat and fall guards |
| `lifed` | Python | the life layer: state machine, drives and moods, attention, missions, an offline small brain, head motion |
| `voiced` | Python | denoising, voice detection, offline recognition (SenseVoice), sound direction from two microphones |
| `visiond` | Python | the camera: faces (YuNet), motion, Wi-Fi by QR code, snapshots |
| `tofd` | Rust | 8×8 ToF ranging: distance ahead, someone close |
| `padd` | Rust | Xbox gamepad over Bluetooth; outranks `lifed` |
| `duckweb` | Python | a phone page: state, battery, conversation, volume |
| `duckbrain` | Python | optional, on a GPU server: any OpenAI-compatible multimodal LLM, for conversation and looking |
| `persona` | JSON | who the duck is — name, character, how it talks — apart from the code |

### Verified platforms

| Combination | Status |
|---|---|
| Orange Pi Zero 3W 4 GB + 15 × HL-2915 + 3S battery (LiPo 1500 mAh / LiHV 2800 mAh) | ✅ in daily use |
| Orange Pi Zero 3W + 15 × HD-1910 + 2S battery | 🚧 boards being assembled; servo driver and policies to do |
| Original Microduck (Radxa Zero 3W + Dynamixel XL330) | ⚪ the Dynamixel bus driver is unchanged; not tested by us |

### Progress

| When | Done |
|---|---|
| 2026-08 | Started from Microduck |
| 2026-09 | Designed the PDB/IMU (R2f) board; fabricated and assembled |
| early 2026-10 | Feetech HL-2915 bus driver, IMU firmware; actuator identification (BAM); walk, stand-up and sit/stand retrained |
| 10-13 | Xbox gamepad over Bluetooth |
| 10-14 | The life layer: drives, moods, rest, servo heat budget |
| 10-15 – 16 | Voice: offline recognition, duck-speak replies, online brain |
| 10-17 | Wi-Fi by QR code, voice prompts, volume, "what is this?", missions (a spoken sequence of moves), odometry calibration |
| 10-18 | Sound direction from two microphones, attention with vision (faces, motion), battery identification, persona apart from framework, open source |

| Area | What | Status |
|---|---|---|
| Skills | Forward roll, picking a cloth up from the floor (trained in sim, robot test next) | 🚧 in progress |
| Attention | Vision-guided gaze, on the robot | 🚧 in progress |
| Missions | Walking a spoken route on the robot | 🚧 in progress |
| 2S version | HD-1910 servos on 2S | 🚧 in progress |
| NPU | Object detection for the attention | 📋 planned |
| On-device VLM | MiniCPM-V 4.7 1B, seeing offline | 📋 planned |
| Localisation | AprilTag landmarks → visual odometry → a room map | 📋 planned |
| Voice | Wake word, noisy rooms, two-mic beamforming | 📋 planned |
| Docs | A full build guide | 📋 planned |

## Build Your Own DuckBuddy

| Step | Where | Status |
|---|---|---|
| 1. Get the parts | the parts list below | ✅ list · 🚧 shop links coming |
| 2. Print | [hardware/print](hardware/print/README.md): Bambu Studio project `DuckBuddy.3mf`, 6 plates, PETG + TPU, settings included. Optional open development head for the [Robot HAT E1](https://code.caric.io/Robotics/elec_RPI_Robot_HAT): [hardware/cad/open-head](hardware/cad/open-head/README.md); optional LiPo plate with the BNO055 mount: [hardware/cad/lipo-plate](hardware/cad/lipo-plate/README.md) | ✅ |
| 3. Carrier board | the [Robot HAT E1](https://code.caric.io/Robotics/elec_RPI_Robot_HAT): schematic, PCB and production files in its repo; for a 3S battery replace D5 with an SMBJ15A first ([guide](https://code.caric.io/Robotics/elec_RPI_Robot_HAT/src/branch/main/docs/12V_battery_swap.md)). Pinout, power and bus as used here: [docs/hardware/INTERFACE-CN.md](docs/hardware/INTERFACE-CN.md) | ✅ |
| 4. Body IMU | a BNO055 breakout (Adafruit 4646) on the [LiPo plate](hardware/cad/lipo-plate/README.md), on a Qwiic cable to the HAT's J5. Nothing to flash | ✅ |
| 5. Set up the Orange Pi | audio, servo UART and I²C: [deploy/audio](deploy/audio/README-A733-CN.md); services in [deploy/opi-dev](deploy/opi-dev/README.md); robot config [deploy/robots/opi-hl2915-robothat-e1.toml](deploy/robots/opi-hl2915-robothat-e1.toml) | 🚧 one-step installer coming |
| 6. Servos, zero pose, whole-robot test | [tools/bringup](tools/bringup/README.md): a web workbench on your computer - servo IDs, joint mapping, zero calibration, IMU firmware, self-test, each page with a guide. New servos are set up on a Raspberry Pi test bench with a second Robot HAT E1, in place of the Feetech USB board (`--bench`) | ✅ |
| 7. Policies | trained policies ship in the repo; to train your own see [training](training) | ✅ |
| 8. Give it a character | [tools/persona](tools/persona/README.md): write your own persona JSON after the example duck | ✅ |
| 9. Assembly guide, FAQ | a short FAQ below; an illustrated assembly guide is coming | 🚧 |

### Parts list

| Part | Qty | Notes |
|---|---|---|
| Feetech HL-2915 servo | 15 | the 3S version; 2 × 5 in the legs, 5 in the head (neck, head, beak). Microduck's printed parts fit as is, M2×6 self-tapping screws |
| Orange Pi Zero 3W | 1 | the 4 GB version recommended |
| [Robot HAT E1](https://code.caric.io/Robotics/elec_RPI_Robot_HAT) | 1 | in the head, on the Orange Pi's 40-pin header; it takes the battery and feeds the servos. D5 swapped to an SMBJ15A for 3S |
| BNO055 breakout (Adafruit 4646) | 1 | the body IMU, on the [LiPo plate](hardware/cad/lipo-plate/README.md), with a Qwiic cable (about 30 cm) to the HAT's J5 |
| Servo Y-cable | 1 | joins the head chain to one of the HAT's servo ports |
| IMX219 camera module | 1 | MIPI CSI, in the face |
| 8×8 ToF module (VL53L5CX) | 1 | in the face |
| Small speaker | 1 | on the HAT's amplifier (J1) |
| Electret microphones | 2 | left and right of the head, on the HAT's J2 and J9 |
| 3S battery | 1 | LiPo 1500 mAh or LiHV 2800 mAh; robotd identifies it. XT60 plug |
| PETG and TPU filament | | TPU for the soft parts (soles, beak) |
| Xbox gamepad | 1 | optional, Bluetooth |

### FAQ

- **2S or 3S?** The HL-2915 runs on 3S: replace the HAT's D5 with an SMBJ15A first ([guide](https://code.caric.io/Robotics/elec_RPI_Robot_HAT/src/branch/main/docs/12V_battery_swap.md)).
  The HD-1910 runs on 2S, and the HAT as built takes 2S. robotd identifies the pack at start-up and refuses to power the servos if it does
  not match the configuration.
- **The servos have power but don't move?** Feetech HLS servos stay still while their target current and
  running speed registers are 0. robotd writes them at start-up; set them in your own test scripts.
- **It stops answering the stick after a while?** Most likely the head servos' heat guard. The head has
  little cooling, and the life layer budgets its movement and rest by temperature.
- **Does the original Microduck run this software?** In software terms yes — the Dynamixel bus driver is
  unchanged — but we have not tested it on the original hardware.

## Join the Community

[Issues](https://github.com/Animan-AI/DuckBuddy/issues) and pull requests are welcome; see
[CONTRIBUTING.md](CONTRIBUTING.md) for building and testing. Places we'd love help with:

- the HD-1910 servo driver;
- NPU object detection for the attention;
- AprilTag localisation for the mission layer;
- the build guide.

<details>
<summary>Repository layout</summary>

| Path | What |
|---|---|
| `robotd`, `duck-control`, `kinematics`, `padd`, `robotctl`, … | the Rust workspace (from Microduck, extended) |
| `tools/` | the Python services: `lifed`, `voiced`, `visiond`, `duckweb`, `duckbrain`, `persona`, the bring-up workbench `bringup`, robot test scripts |
| `firmware/imu-feetech` | the IMU board's firmware (STM32G031 + LSM6DSV16X, speaks the Feetech protocol) |
| `training/` | HL-2915 tasks, actuator identification (BAM), evaluation scripts, trained policies |
| `hardware/` | the print project (`hardware/print`), the open PDB/IMU R3 board (`hardware/pcb/pdb-imu`, tscircuit), the open head shell (`hardware/cad/open-head`, an organic frame generated in Python), the LiPo plate (`hardware/cad/lipo-plate`, build123d), the robot model used for training (`hardware/rev-a/mjcf`) |
| `docs/` | the hardware interface (`docs/hardware`), and Microduck's own design notes and guides |

</details>

Come and chat — building, tuning, training, or just showing off your duck. The WeChat group:

<p align="center"><img src="docs/media/wechat-group.png" width="300" alt="DuckBuddy WeChat group QR code"></p>

<p align="center"><sub>WeChat group codes expire after a week and are refreshed here; if this one has lapsed, open an issue.</sub></p>

---

<sub>License: software Apache-2.0 (as Microduck), documentation CC-BY-4.0; some components carry their own licences — see [NOTICE](NOTICE).</sub>
