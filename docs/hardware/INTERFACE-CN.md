# Expansion board interfaces (HAT R3E, PDB/IMU R2f)

This document covers only the **interfaces**: pins, power, buses and sizes. With it you can use our boards, or design your own compatible boards.
The boards' schematics, PCB layouts and production files are not in this repo. If you need assembled boards, contact the maintainers.

> An open, compatible PDB/IMU board (R3) is in [`hardware/pcb/pdb-imu`](../../hardware/pcb/pdb-imu/README.md). It has not been fabricated yet. The R3E and R2f design files are still not in this repo.
> This fork's robot uses the Robot HAT E1 and a BNO055 instead of the HAT R3E and the PDB/IMU board: see section 6.

## 1. Overall connections

```
                 ┌───────────── Orange Pi Zero 3W ─────────────┐
                 │  40-pin header (J1)                         │
                 └──────────────┬──────────────────────────────┘
                                │ 5V, I2S, I2C, UART (servo bus)
          ┌─────────────────────┴────────────────────────────┐
          │ HAT                                              │
          │  Power: battery → reverse protection/soft start  │── J5  ToF (I²C, 3.3 V)
          │         → 5 V buck                               │
          │  Audio: TLV320AIC3104 codec + amp                │── J6  speaker
          │  Servo bus: half-duplex transceiver              │── J7/J8 two electret mics (head, left and right)
          └──────────────────┬───────────────────────────────┘
                             │ J2 (XH 3P): GND / battery / bus data
          ┌──────────────────┴───────────────────────────────┐
          │ PDB/IMU                                          │── J1  battery
          │  Power distribution: TVS, branch fuses           │── J4  left leg, 5 servos
          │  IMU: STM32G031 + LSM6DSV16X, bus ID 200         │── J6  right leg, 5 servos
          └──────────────────────────────────────────────────┘
     The HAT is in the head. The 5 head servos and the HAT share the
     PDB J5 branch (power and bus).
```

All servos, the IMU and the HAT share **one** single-wire half-duplex bus. The servos run directly on the battery voltage.

## 2. HAT

**Size**: 65 × 30 mm, 4-layer board. One Ø2.75 mm plated mounting hole in each corner, hole centers at (±29, ±11.5) mm. This is the standard Raspberry Pi Zero hole spacing of 58 × 23 mm.

### 2.1 J1: to the Orange Pi's 40-pin header

The female header body is on the **back** of the HAT and plugs down into the Orange Pi.

| Pin | Signal | Orange Pi side |
|---|---|---|
| 2, 4 | 5V (**the HAT supplies** the Orange Pi) | 5V |
| 3 | Amp shutdown AMP_SD | PB3 |
| 7 | I2S MCLK | PB4 (I2S0) |
| 11 | Codec reset | PB0 |
| 12 | I2S BCLK | PB5 |
| 16 / 18 | Servo bus TX / RX | UART7 (`/dev/ttyS7`) |
| 19 / 23 | I²C SDA / SCL (codec, ToF) | PE2 / PE1 (TWI2) |
| 35 | I2S LRCK | PB6 |
| 38 | I2S data into the SoC (codec output) | PB8 |
| 40 | I2S data out of the SoC (codec input) | PB7 |
| 6, 9, 14, 20, 25, 30, 34, 39 | GND | GND |
| 1, 17 | Not connected | 3.3V |

The device tree config on the Orange Pi (I2S, I²C, UART) is in `deploy/audio/`.

### 2.2 Other connectors

| Ref | Connector | Pins | Notes |
|---|---|---|---|
| J2 | XH 3P (2.5 mm) | 1 GND · 2 battery · 3 bus data | To PDB J5, with a 3P same-direction cable |
| J5 | SH1.0 4P | 1 3V3 · 2 GND · 3 SCL · 4 SDA (pin 1 is the end with the small dot) | 8×8 ToF module. We use the VL53L5CX; the original uses the VL53L8CX |
| J6 | Solder holes | Speaker + / − | Small speaker, mono (the amp takes only the left channel), TPA2005D1 amp |
| J7 / J8 | Solder holes | 1 = + (P) · 2 = − (N, the pin wired to the mic capsule's case) | Two electret mics on the head, left on J7, right on J8 |

### 2.3 Power

- **Input**: the battery voltage comes in through J2, with reverse polarity protection and soft start. F1 fuse, 3 A.
- **5 V**: LMR51450 buck (500 kHz). It powers the Orange Pi and the peripherals on the board. 3.3 V and 1.8 V come from LDOs fed by the 5 V rail.
- **Undervoltage lockout**: below a set voltage, the buck chip does not start. This protects the battery.

| Battery | Start voltage | Board version |
|---|---|---|
| 3S (HL-2915 servos) | About 8.5 V | 3S version |
| 2S (HD-1910 servos) | About 6.3 V | 2S version |

The two board versions look the same. Tell them apart by the "2S" mark on the back. **Do not fit the 2S version to a 3S robot**, or the undervoltage lockout will not work.

## 3. PDB/IMU

**Size**: 55 × 28 mm, 2-layer board.

| Ref | Connector | Pins | Notes |
|---|---|---|---|
| J1 | Solder holes | Battery + / − | Battery leads. 2S and 3S batteries use **different plugs**, so they cannot be swapped by mistake |
| J4 / J6 | PH2.0 3P | 1 GND · 2 V (battery) · 3 DATA | Left leg / right leg, 5 servos each, daisy-chained |
| J5 | XH 3P (2.5 mm) | 1 GND · 2 V · 3 DATA | To HAT J2. The HAT is in the head, and the 5 head servos also use this branch |
| J2 | Pin header | SWD | For flashing the IMU firmware |

- **Protection**: TVS (SMBJ14A). One 4 A fuse on each of the three branches (left leg, right leg, head with the HAT), and a 1 A fuse on the board's 3.3 V (IMU) branch. The servos get the battery voltage directly.
- **IMU**: the STM32G031 reads the attitude fusion output of the LSM6DSV16X and acts as a Feetech protocol device on the bus, **ID 200**. It switches the bus direction with hardware DE. Firmware: `firmware/imu-feetech`.
- **R3 (open version)**: same interface as the table above (J4/J6 as side-entry PH2.0), on a 55 × 31 mm board that lies flat on the hip servos (3 mm taller at the J1 edge, both J5-side corners cut away 6 × 3 mm, held by two M2 screws on standoffs at the J1-side corners instead of the R2f holes), plus a power switch with reverse polarity protection, bulk input capacitors, ESD protection on DATA, one LED per branch, a status LED on PA11, a bus speed jumper (JP1: open = 500 kbit/s, bridged = 1 Mbit/s for STS3215 servos), self-resetting (PPTC) branch fuses, battery voltage and current readings served on the bus (firmware 1.2), a hardware low-battery cutoff (JP2: open = 3S, bridged = 2S), test points, and Tag-Connect SWD pads. See [`hardware/pcb/pdb-imu`](../../hardware/pcb/pdb-imu/README.md).

## 4. Servo bus

| Item | Value |
|---|---|
| Physical layer | Single-wire TTL, half-duplex |
| Protocol | Feetech (HLS memory table, see the Feetech driver in `duck-control`) |
| Baud rate | **500 kbps**. On the A733, UART7 set to 1 Mbps really runs at only about 750 kbps, so 500k is used everywhere |
| Devices | 15 servos (IDs in `deploy/robots/*.toml`) + IMU (ID 200) |

## 5. Battery

| Robot | Battery | Servo rating | robotd config |
|---|---|---|---|
| HL-2915 version | 3S LiPo / LiHV | 9–14 V | `[battery] cells = [3]`, `max_volts = 14.0` |
| HD-1910 version | 2S LiPo (**do not use 2S LiHV**: fully charged it is 8.7 V, above the 8.4 V rating) | 4–8.4 V | `[battery] cells = [2]`, `max_volts = 8.4` |

At startup, robotd detects the battery by itself (cell count, LiPo or LiHV). If the battery does not match the config, it refuses to enable torque and says why.

## 6. Robot HAT E1 build (no HAT R3E, no PDB/IMU board)

This fork's robot uses the Robot HAT E1 (KiCad project `elec_RPI_Robot_HAT`) in the head, on the
Orange Pi Zero 3W, and **no PDB/IMU board**. The HAT takes the battery and feeds the servos itself,
and the body IMU is a BNO055 on a Qwiic cable. The HAT has the same codec (TLV320AIC3104) on the
same I2S pins as the R3E, but other header pins and connectors.

Software:

- Audio, servo UART and I²C: `deploy/audio/install-aic3104-a733.sh --hat robothat-e1`
  (see [`deploy/audio/README-A733-CN.md`](../../deploy/audio/README-A733-CN.md), section 8).
- robotd: [`deploy/robots/opi-hl2915-robothat-e1.toml`](../../deploy/robots/opi-hl2915-robothat-e1.toml)
  (`port = "/dev/ttyS0"`, `imu_source = "bno055"`), finished with `tools/bringup`.

| Pin | Robot HAT E1 | Orange Pi Zero 3W | HAT R3E on this pin |
|---|---|---|---|
| 2, 4 | 5 V (the HAT supplies the Orange Pi) | 5V | same |
| 3 / 5 | I²C SDA / SCL: codec 0x18, INA226 0x45, LSM6DSV16X 0x6A, Qwiic J5 (BNO055 0x28) | PB3 / PB2 (TWI0, `/dev/i2c-0`, 400 kHz) | 3 = AMP_SD |
| 7 | Qwiic J6 SDA | PB4 (not muxed as MCLK) | I2S MCLK |
| 8 / 10 | servo bus TX / RX | PB9 / PB10 (UART0, `/dev/ttyS0`) | not used |
| 11 | not connected | PB0 | codec reset |
| 12, 35, 38, 40 | I2S BCLK, LRCK, codec DOUT, codec DIN | PB5, PB6, PB8, PB7 (I2S0) | same |
| 16 / 18 | not connected | UART7 | servo bus |
| 19 / 23 | Qwiic J8 SDA / SCL (ToF) | PE2 / PE1 (TWI2, `/dev/i2c-2`) | I²C (codec, ToF) |
| 32, 33, 37 | RGB LED red, green, blue (low = on) | PD1, PD3, PD4 | not used |

| Item | Robot HAT E1 build | Notes |
|---|---|---|
| Size | 84 × 30.9 mm (65 × 30 mm Pi Zero part plus 19 mm for the XT60 and fuse) | The R3E is 65 × 30 mm. The open head in [`hardware/cad/open-head`](../../hardware/cad/open-head/README.md) is made for this board |
| Battery | 3S LiPo / LiHV into the XT60 (J15) | XT60 → INA226 shunt (R43) → 10 A fuse (F1) → servo ports and the 5 V buck. The battery leads run from the body to the head |
| TVS | D5 SMBJ10A as built: 2S only | For 3S, replace D5 with an SMBJ15A first (`elec_RPI_Robot_HAT/docs/12V_battery_swap.md`) |
| Servos | J13 / J14 (JST EH 3P, 2.5 mm): 1 GND · 2 battery · 3 DATA, both on the same bus | Three servo chains: left leg, right leg, head. An EH contact is rated 3 A: give each leg its own port, and join the head chain to one of them with a Y-cable (the head servos carry little load) |
| What the PDB did | per-branch 4 A fuses, a hardware low-battery cutoff, the IMU on the bus | Here: one 10 A fuse (F1) for everything; no hardware cutoff, robotd reads the battery from the servos and shuts down when it is empty (`[safety] battery_empty_shutdown`); the IMU is the BNO055 |
| Body IMU | BNO055 breakout (Adafruit 4646, address 0x28) in the body, on a Qwiic cable to **J5** | On the front face of the LiPo plate ([`hardware/cad/lipo-plate`](../../hardware/cad/lipo-plate/README.md)), just under the hip servos, close to the IMU site of the robot model. robotd runs it in IMU fusion mode (no magnetometer) and polls it 200 times a second. Not on J8: a ToF frame holds that bus for 10–30 ms, longer than the IMU delay the walking policies tolerate. Leave slack in the cable through the neck. `[bus] imu_axes` is measured with the bring-up tool's IMU test (robot upright, then on its back) |
| Codec clock | 12 MHz oscillator on the HAT | The SoC MCLK is not used |
| Codec reset | RC on the HAT | No GPIO |
| Speaker | PAM8406 class-D amp, always on; speaker on J1 (screw terminal, the amp's right channel) | No amp-enable GPIO |
| Microphones | J2 (left) and J9 (right): screw terminals for electret mics, biased on the HAT, single-ended into LINE1L / LINE1R; MK1: MEMS mic on the board, on MIC2R | Wire the two head mics to J2 and J9 for the sound direction |
| ToF | Qwiic J8 on TWI2 (`/dev/i2c-2`, as on the R3E) | Qwiic pin order: 1 GND · 2 3V3 · 3 SDA · 4 SCL. This is the reverse of R3E J5, so an R3E ToF cable swaps 3V3 and GND |
| Servo bus | UART0, 500 kbit/s; the bus direction follows TX | UART0 is the board's debug console: the installer moves the console off it. U-Boot still prints its boot messages on the bus at 115200 baud |
| Bench | A Raspberry Pi with the same HAT sets up factory servos (1 Mbit/s) | `tools/bringup/app.py --bench` (see `tools/bringup/README.md`) |
