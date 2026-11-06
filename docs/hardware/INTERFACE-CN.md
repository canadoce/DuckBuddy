# Hardware interfaces (Robot HAT E1, BNO055)

This document covers the **interfaces**: pins, power, buses and sizes of the robot's electronics.

The head board is the [Robot HAT E1](https://code.caric.io/Robotics/elec_RPI_Robot_HAT). Its
schematic, PCB and production files are in that repository. The body IMU is a BNO055 breakout. An
open PDB/IMU board (R3), not used by this build, is in [`hardware/pcb/pdb-imu`](../../hardware/pcb/pdb-imu/README.md).

## 1. Overall connections

```
                 ┌───────────── Orange Pi Zero 3W ─────────────┐
                 │  40-pin header                              │
                 └──────────────┬──────────────────────────────┘
                                │ 5V, I2S, I²C, UART0 (servo bus)
          ┌─────────────────────┴────────────────────────────┐
 battery ─┤ J15 XT60                     Robot HAT E1        │── J8  Qwiic: ToF (TWI2)
          │  INA226 shunt → 10 A fuse → +BATT                │── J5  Qwiic: BNO055 body IMU (TWI0)
          │  5 V buck for the Orange Pi                      │── J1  speaker (PAM8406)
          │  Audio: TLV320AIC3104 codec + amp                │── J2 / J9  electret mics, left / right
          └───────────────┬──────────────────┬───────────────┘
                  J13 port A                 J14 port B
             (GND · battery · DATA)     (GND · battery · DATA)
                     │                        │
              left leg, 5 servos       right leg, 5 servos
                                       + head, 5 servos (Y-cable)
```

All 15 servos share **one** single-wire half-duplex bus. The servos run directly on the battery voltage.

## 2. Robot HAT E1

Software:

- Audio, servo UART and I²C: `deploy/audio/install-aic3104-a733.sh --hat robothat-e1`
  (see [`deploy/audio/README-A733-CN.md`](../../deploy/audio/README-A733-CN.md)).
- robotd: [`deploy/robots/opi-hl2915-robothat-e1.toml`](../../deploy/robots/opi-hl2915-robothat-e1.toml)
  (`port = "/dev/ttyS0"`, `imu_source = "bno055"`), finished with `tools/bringup`.

### 2.1 Header pins

| Pin | Robot HAT E1 | Orange Pi Zero 3W |
|---|---|---|
| 2, 4 | 5 V (the HAT supplies the Orange Pi) | 5V |
| 3 / 5 | I²C SDA / SCL: codec 0x18, INA226 0x45, LSM6DSV16X 0x6A, Qwiic J5 (BNO055 0x28) | PB3 / PB2 (TWI0, `/dev/i2c-0`, 400 kHz) |
| 7 | Qwiic J6 SDA | PB4 (not muxed as MCLK) |
| 8 / 10 | servo bus TX / RX | PB9 / PB10 (UART0, `/dev/ttyS0`) |
| 11 | not connected | PB0 |
| 12, 35, 38, 40 | I2S BCLK, LRCK, codec DOUT, codec DIN | PB5, PB6, PB8, PB7 (I2S0) |
| 16 / 18 | not connected | UART7 |
| 19 / 23 | Qwiic J8 SDA / SCL (ToF) | PE2 / PE1 (TWI2, `/dev/i2c-2`) |
| 32, 33, 37 | RGB LED red, green, blue (low = on) | PD1, PD3, PD4 |

### 2.2 Board and connectors

| Item | Robot HAT E1 | Notes |
|---|---|---|
| Size | 84 × 30.9 mm (65 × 30 mm Pi Zero part plus 19 mm for the XT60 and fuse) | The open head in [`hardware/cad/open-head`](../../hardware/cad/open-head/README.md) is made for this board |
| Battery | 3S LiPo / LiHV into the XT60 (J15) | XT60 → INA226 shunt (R43) → 10 A fuse (F1) → servo ports and the 5 V buck. The battery leads run from the body to the head |
| TVS | D5 SMBJ10A as built: 2S only | For 3S, replace D5 with an SMBJ15A first ([Using a 12 V battery](https://code.caric.io/Robotics/elec_RPI_Robot_HAT/src/branch/main/docs/12V_battery_swap.md)) |
| Servos | J13 / J14 (JST EH 3P, 2.5 mm): 1 GND · 2 battery · 3 DATA, both on the same bus | Three servo chains: left leg, right leg, head. An EH contact is rated 3 A: give each leg its own port, and join the head chain to one of them with a Y-cable (the head servos carry little load) |
| Protection | one 10 A fuse (F1) for everything; no hardware low-battery cutoff | robotd reads the battery from the servos and shuts down when it is empty (`[safety] battery_empty_shutdown`) |
| Body IMU | BNO055 breakout (Adafruit 4646, address 0x28) in the body, on a Qwiic cable to **J5** | On the front face of the LiPo plate ([`hardware/cad/lipo-plate`](../../hardware/cad/lipo-plate/README.md)), just under the hip servos, close to the IMU site of the robot model. robotd runs it in IMU fusion mode (no magnetometer) and polls it 200 times a second. Not on J8: a ToF frame holds that bus for 10–30 ms, longer than the IMU delay the walking policies tolerate. Leave slack in the cable through the neck. `[bus] imu_axes` is measured with the bring-up tool's IMU test (robot upright, then on its back) |
| Codec clock | 12 MHz oscillator on the HAT | The SoC MCLK is not used |
| Codec reset | RC on the HAT | No GPIO |
| Speaker | PAM8406 class-D amp, always on; speaker on J1 (screw terminal, the amp's right channel) | No amp-enable GPIO |
| Microphones | J2 (left) and J9 (right): screw terminals for electret mics, biased on the HAT, single-ended into LINE1L / LINE1R; MK1: MEMS mic on the board, on MIC2R | Wire the two head mics to J2 and J9 for the sound direction |
| ToF | Qwiic J8 on TWI2 (`/dev/i2c-2`) | Qwiic pin order: 1 GND · 2 3V3 · 3 SDA · 4 SCL |
| Bench | A Raspberry Pi with a second Robot HAT E1 sets up factory servos (1 Mbit/s) | `tools/bringup/app.py --bench` (see `tools/bringup/README.md`) |

## 3. Servo bus

| Item | Value |
|---|---|
| Physical layer | Single-wire TTL, half-duplex; the HAT switches the bus direction from TX |
| Protocol | Feetech (HLS memory table, see the Feetech driver in `duck-control`) |
| Baud rate | **500 kbps** on UART0: 24 MHz / 16 / 3, exact. Factory servos run at 1 Mbps; set them up on the Raspberry Pi test bench first |
| Devices | 15 servos (IDs in `deploy/robots/*.toml`) |
| Console | UART0 is the board's debug console: the installer moves the console off it. U-Boot still prints its boot messages on the bus at 115200 baud |

## 4. Battery

| Robot | Battery | Servo rating | robotd config |
|---|---|---|---|
| HL-2915 version | 3S LiPo / LiHV (the HAT's D5 swapped to an SMBJ15A) | 9–14 V | `[battery] cells = [3]`, `max_volts = 14.0` |
| HD-1910 version | 2S LiPo (**do not use 2S LiHV**: fully charged it is 8.7 V, above the 8.4 V rating) | 4–8.4 V | `[battery] cells = [2]`, `max_volts = 8.4` |

At startup, robotd detects the battery by itself (cell count, LiPo or LiHV). If the battery does not match the config, it refuses to enable torque and says why.
