# imu-feetech — PDB IMU board firmware

The STM32G031F8P6 + LSM6DSV16X on the PDB R2f. The firmware presents the chip's built-in orientation fusion
(SFLP game rotation vector) as a Feetech device on the servo bus (ID 200, 500 kbit/s). In every cycle robotd
reads it in the same `SYNC_READ` as the 15 servos.

- Protocol and register layout: `hardware/rev-a/electronics/imu_to_dxl-spec-feetech.md`
- Host side: `duck-control/src/feetech.rs` (reads 15 bytes from address 56 every tick)

## The 15 bytes from address 56

| Offset | Content |
|---|---|
| 0..6 | gyroscope x/y/z, i16 LE raw counts, ±500 dps |
| 6..12 | SFLP quaternion x/y/z, binary16 LE, as it comes from the FIFO; all 0 before the first fusion output (the host's "not ready" convention) |
| 12 | sample counter, +1 for each fusion output |
| 13 | flags: bit0 sensor configured, bit1 orientation valid |
| 14 | Battery voltage in 0.1 V (firmware 1.2, R3 only; meaningless on R2f, where PA0 is not connected) |

Also available with `READ`: address 5 = 200 (ID), 6 = 1 (500k), 3..4 = 0x16D6 (model number), 0..1 = firmware version.

## Build and flash

```bash
rustup target add thumbv6m-none-eabi
cargo build --release
cargo install probe-rs-tools --locked     # once
probe-rs run --chip STM32G031F8Px target/thumbv6m-none-eabi/release/imu-feetech
```

ST-Link on the PDB's J2: 1 SWDIO, 2 SWCLK, 3 GND, 4 3V3 (when the board has its own power, the ST-Link's 3V3 can be left unconnected).

On R3 the same signals, plus NRST, are also on J7, pads for a Tag-Connect TC2030-NL cable (TC2030-CTX pinout: 1 3V3, 2 SWDIO, 3 NRST, 4 SWCLK, 5 GND).
J2 on R3 does not fit inside the robot body (and sits where the J6 plug lies), so flash an R3 in the robot through J7.

The protocol logic can be tested on a computer, with no hardware:

```bash
rustc --edition 2021 --test src/proto.rs -o target/proto-test && target/proto-test
```

## What to check on the robot

- Mounting direction: by default the host's `DEFAULT_MOUNT` assumes the chip is mounted rotated +90° about the Y axis (spec §4). On the PDB, U2 is on the back side,
  so check the real direction on the robot by putting it in known poses; if it is wrong, change the mount quaternion on the host side.
- robotd puts ID 200 in the sync read only when its config has `[bus] imu = true`.
- On the open R3 board, U2 is on the top side: set `[bus] imu_axes = "-y,x,z"` and check it on the robot (see [`hardware/pcb/pdb-imu`](../../hardware/pcb/pdb-imu/README.md#imu-direction)).

## Bus speed (firmware 1.1)

PC15 selects the bus speed at start-up, read once with the internal pull-up: open = 500 kbit/s, tied to GND = 1 Mbit/s.
On R3 this is the solder jumper JP1 on the bottom side (bridge it for an STS3215 bus at its factory speed, as on Frankenduck).
PC15 is not connected on R2f, so R2f stays at 500 kbit/s. Register 6 reads back the speed in Feetech's encoding (1 = 500k, 0 = 1M),
and register 1 (firmware minor) is 1 or higher.

## Battery voltage and current (firmware 1.2)

R3 boards measure the battery with the MCU's ADC, 100 times a second (16 conversions averaged per reading,
then smoothed over about 80 ms):

- PA0 (ADC_IN0): battery voltage through a 100 kΩ / 22 kΩ divider (full scale 18.3 V).
- PB7 (ADC_IN11): battery current from the INA180A2 on the 2 mΩ shunt RS1, 0.1 V per A (full scale 33 A).
  It counts everything drawn from the battery: the three branches and the 3.3 V supply.
- The 3.3 V supply itself is measured against the internal reference, so both readings stay right if it drifts.

The readings are served at address 100, 6 bytes, all u16 LE:

| Offset | Content |
|---|---|
| 0..2 | battery voltage, mV |
| 2..4 | battery current, mA |
| 4..6 | 3.3 V supply, mV |

Byte 14 of the block at 56 carries the battery voltage too (0.1 V units, rounded), so the host gets it in every
`SYNC_READ` with no extra read. All values are 0 until the first reading (a few ms after start-up). Register 1
(firmware minor) is 2. PA0 and PB7 are not connected on R2f, so there the values mean nothing.

The board also turns itself off when the battery runs low (a hardware cutoff, no firmware involved): see
[`hardware/pcb/pdb-imu`](../../hardware/pcb/pdb-imu/README.md).

## Status LED

PA11 drives a status LED (LED4 on R3; this pin is not connected on R2f): fast blink = the IMU does not answer, 1 Hz blink = orientation data is flowing.
