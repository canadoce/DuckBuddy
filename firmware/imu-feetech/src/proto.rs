//! The Feetech bus, from the slave's side: framing, the register map, and the turn-taking a
//! `SYNC_READ` asks of every device it names.
//!
//! Pure logic, no hardware — so it builds and tests on a laptop:
//! `rustc --edition 2021 --test src/proto.rs -o target/proto-test && target/proto-test`.
//!
//! Frames are Dynamixel protocol 1.0 as Feetech uses it: `FF FF id len field params… chk`,
//! `len` = params + 2, `chk` = !(id + len + field + params). On the host's frames `field` is
//! the instruction; on a device's reply it is the error byte. The parser does not care which.

/// This board's bus ID. The host lists it last in every `SYNC_READ`, after the 15 servos.
pub const MY_ID: u8 = 200;
pub const BROADCAST: u8 = 0xFE;

pub const PING: u8 = 0x01;
pub const READ: u8 = 0x02;
pub const WRITE: u8 = 0x03;
pub const SYNC_READ: u8 = 0x82;

/// The bus speeds this board runs at, picked at start-up by the PC15 solder jumper (see
/// `main.rs`). The value at address 6 follows Feetech's baud register: 0 = 1 Mbit/s,
/// 1 = 500 kbit/s.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Baud {
    /// 500 kbit/s: the DuckBuddy bus (the A733's UART7 cannot do a true 1 Mbit/s).
    K500,
    /// 1 Mbit/s: an STS3215 bus at its factory speed (Frankenduck).
    M1,
}

impl Baud {
    pub const fn bits_per_second(self) -> u32 {
        match self {
            Baud::K500 => 500_000,
            Baud::M1 => 1_000_000,
        }
    }

    /// The code a Feetech servo keeps in register 6 for this speed.
    pub const fn register(self) -> u8 {
        match self {
            Baud::K500 => 1,
            Baud::M1 => 0,
        }
    }
}

/// Where the host's tick reads, and how much: the servos' present-state block, 56..70.
pub const BLOCK_ADDR: u8 = 56;
pub const BLOCK_LEN: usize = 15;

/// Where the bus task's own counters can be read: 8 bytes, see `main.rs` (`DIAG`).
pub const DIAG_ADDR: u8 = 90;
pub const DIAG_LEN: usize = 8;

/// Where the power readings can be read (R3 boards): 6 bytes, all u16 LE.
/// 0..2 battery voltage in mV, 2..4 battery current in mA, 4..6 the MCU's 3.3 V supply in mV.
/// All zero until the first reading.
pub const POWER_ADDR: u8 = 100;
pub const POWER_LEN: usize = 6;

/// Byte 14 of the block at 56: the battery voltage in units of 0.1 V, so the host sees it in
/// every `SYNC_READ` without an extra read.
pub const BLOCK_BATTERY: usize = 14;

/// Largest parameter list accepted. A `SYNC_READ` naming 16 devices carries 18.
pub const MAX_PARAMS: usize = 40;
/// Largest read answered.
pub const MAX_READ: usize = 32;
/// A reply frame: header, id, len, error, data, checksum.
pub const MAX_FRAME: usize = MAX_READ + 6;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Frame {
    pub id: u8,
    /// Instruction on a host frame, error byte on a device's reply.
    pub field: u8,
    pub params: [u8; MAX_PARAMS],
    pub nparams: usize,
}

impl Frame {
    pub fn params(&self) -> &[u8] {
        &self.params[..self.nparams]
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum State {
    Header1,
    Header2,
    Id,
    Len,
    Body,
}

/// Byte-at-a-time frame reassembly. Corrupt or oversized frames are dropped and the parser
/// goes back to hunting for `FF FF`, so a glitch costs one frame, never a desync.
pub struct Parser {
    state: State,
    id: u8,
    len: usize,
    body: [u8; MAX_PARAMS + 2],
    got: usize,
}

impl Default for Parser {
    fn default() -> Self {
        Self::new()
    }
}

impl Parser {
    pub const fn new() -> Self {
        Self {
            state: State::Header1,
            id: 0,
            len: 0,
            body: [0; MAX_PARAMS + 2],
            got: 0,
        }
    }

    pub fn reset(&mut self) {
        self.state = State::Header1;
    }

    pub fn feed(&mut self, b: u8) -> Option<Frame> {
        match self.state {
            State::Header1 => {
                if b == 0xFF {
                    self.state = State::Header2;
                }
            }
            State::Header2 => {
                self.state = if b == 0xFF { State::Id } else { State::Header1 };
            }
            State::Id => {
                // A third FF is still header: some senders pad, and 0xFF is never an ID.
                if b != 0xFF {
                    self.id = b;
                    self.state = State::Len;
                }
            }
            State::Len => {
                let len = b as usize;
                if (2..=MAX_PARAMS + 2).contains(&len) {
                    self.len = len;
                    self.got = 0;
                    self.state = State::Body;
                } else {
                    self.state = State::Header1;
                }
            }
            State::Body => {
                self.body[self.got] = b;
                self.got += 1;
                if self.got == self.len {
                    self.state = State::Header1;
                    // body = field, params…, checksum
                    let sum = self.body[..self.len - 1]
                        .iter()
                        .fold(self.id.wrapping_add(self.len as u8), |a, x| a.wrapping_add(*x));
                    if !sum == self.body[self.len - 1] {
                        let nparams = self.len - 2;
                        let mut params = [0; MAX_PARAMS];
                        params[..nparams].copy_from_slice(&self.body[1..1 + nparams]);
                        return Some(Frame {
                            id: self.id,
                            field: self.body[0],
                            params,
                            nparams,
                        });
                    }
                }
            }
        }
        None
    }
}

/// What to put on the wire in answer to a frame.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    Nothing,
    /// A status frame with no data — PING, and WRITE, which this board accepts and ignores.
    Ack,
    /// A status frame carrying `len` bytes of the register map from `addr`.
    Read { addr: u8, len: u8 },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Pending {
    /// Our position in the `SYNC_READ` list: how many replies must pass before ours.
    index: usize,
    seen: usize,
    addr: u8,
    len: u8,
}

/// The slave's decisions, frame by frame.
///
/// A `SYNC_READ` is one request answered by every listed device in list order. This board
/// counts the replies ahead of it and speaks when the last has finished. The host lists it
/// last: Feetech servos start on their own timing rather than waiting for the device ahead,
/// so a servo listed after this board would talk over the end of its reply.
#[derive(Default)]
pub struct Slave {
    pending: Option<Pending>,
}

impl Slave {
    pub const fn new() -> Self {
        Self { pending: None }
    }

    /// Give up on a `SYNC_READ` turn that never came (a device ahead of us is silent).
    pub fn expire(&mut self) {
        self.pending = None;
    }

    pub fn waiting(&self) -> bool {
        self.pending.is_some()
    }

    pub fn on_frame(&mut self, f: &Frame) -> Action {
        if f.id == MY_ID {
            self.pending = None;
            return match f.field {
                PING | WRITE => Action::Ack,
                READ if f.nparams == 2 => Action::Read {
                    addr: f.params[0],
                    len: f.params[1],
                },
                // Includes our own reply heard back on the wire: its "field" is error 0.
                _ => Action::Nothing,
            };
        }
        if f.id == BROADCAST {
            self.pending = None;
            if f.field == SYNC_READ && f.nparams >= 3 {
                let p = f.params();
                if let Some(index) = p[2..].iter().position(|&id| id == MY_ID) {
                    let (addr, len) = (p[0], p[1]);
                    if index == 0 {
                        return Action::Read { addr, len };
                    }
                    self.pending = Some(Pending {
                        index,
                        seen: 0,
                        addr,
                        len,
                    });
                }
            }
            return Action::Nothing;
        }
        // Another device's reply: if we are queued behind it, count it.
        if let Some(mut p) = self.pending {
            p.seen += 1;
            if p.seen == p.index {
                self.pending = None;
                return Action::Read {
                    addr: p.addr,
                    len: p.len,
                };
            }
            self.pending = Some(p);
        }
        Action::Nothing
    }
}

/// Everything the register map is built from at the moment of a read.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Registers {
    pub block: [u8; BLOCK_LEN],
    pub diag: [u8; DIAG_LEN],
    pub power: [u8; POWER_LEN],
    pub baud: Baud,
}

impl Registers {
    pub const fn new(baud: Baud) -> Self {
        Self {
            block: [0; BLOCK_LEN],
            diag: [0; DIAG_LEN],
            power: [0; POWER_LEN],
            baud,
        }
    }
}

/// The register map a host can read: identity at the bottom, the orientation block at 56.
pub fn read_map(r: &Registers, addr: u8, out: &mut [u8]) {
    let battery_mv = u16::from_le_bytes([r.power[0], r.power[1]]);
    for (k, slot) in out.iter_mut().enumerate() {
        let a = addr as usize + k;
        *slot = match a {
            0 => 1, // firmware major
            1 => 2, // firmware minor (1: the baud jumper, 2: battery voltage and current)
            3 => 0xD6, // "model": 0x16D6, chosen not to collide with any Feetech servo
            4 => 0x16,
            5 => MY_ID,
            6 => r.baud.register(),
            7 => 0, // return delay
            55 => 1, // "locked"
            _ if a == BLOCK_ADDR as usize + BLOCK_BATTERY => battery_decivolts(battery_mv),
            _ if (BLOCK_ADDR as usize..BLOCK_ADDR as usize + BLOCK_LEN).contains(&a) => {
                r.block[a - BLOCK_ADDR as usize]
            }
            _ if (DIAG_ADDR as usize..DIAG_ADDR as usize + DIAG_LEN).contains(&a) => {
                r.diag[a - DIAG_ADDR as usize]
            }
            _ if (POWER_ADDR as usize..POWER_ADDR as usize + POWER_LEN).contains(&a) => {
                r.power[a - POWER_ADDR as usize]
            }
            _ => 0,
        };
    }
}

/// Build a status frame (error 0) around `data`. Returns the frame length.
pub fn status_frame(data: &[u8], out: &mut [u8; MAX_FRAME]) -> usize {
    let n = data.len().min(MAX_READ);
    out[0] = 0xFF;
    out[1] = 0xFF;
    out[2] = MY_ID;
    out[3] = (n + 2) as u8;
    out[4] = 0;
    out[5..5 + n].copy_from_slice(&data[..n]);
    let sum = out[2..5 + n].iter().fold(0u8, |a, x| a.wrapping_add(*x));
    out[5 + n] = !sum;
    n + 6
}

/// Answer an action: fill `out` with the reply frame, or return 0 for silence.
pub fn reply(action: Action, r: &Registers, out: &mut [u8; MAX_FRAME]) -> usize {
    match action {
        Action::Nothing => 0,
        Action::Ack => status_frame(&[], out),
        Action::Read { addr, len } => {
            let len = (len as usize).min(MAX_READ);
            let mut data = [0u8; MAX_READ];
            read_map(r, addr, &mut data[..len]);
            status_frame(&data[..len], out)
        }
    }
}

// ── power readings (R3) ──────────────────────────────────────────────────────

/// Full scale of a 12-bit conversion.
const ADC_FULL: u32 = 4095;
/// The factory VREFINT calibration was taken at 3.0 V.
const VREFINT_CAL_MV: u32 = 3000;
/// Battery divider on PA0: 100 kΩ over 22 kΩ, so the pin sees 22/122 of the battery.
const BATTERY_DIV_TOP: u32 = 100;
const BATTERY_DIV_BOTTOM: u32 = 22;
/// Current sense on PB7: 2 mΩ shunt × INA180A2 gain 50 = 0.1 V per A, so 1 mV = 10 mA.
const CURRENT_MA_PER_MV: u32 = 10;

/// The MCU supply in mV, from a reading of the internal reference and its factory value.
pub fn supply_mv(vrefint_raw: u16, vrefint_cal: u16) -> u16 {
    if vrefint_raw == 0 {
        return 0;
    }
    (VREFINT_CAL_MV * vrefint_cal as u32 / vrefint_raw as u32).min(u16::MAX as u32) as u16
}

fn pin_mv(raw: u16, supply_mv: u16) -> u32 {
    raw as u32 * supply_mv as u32 / ADC_FULL
}

/// The battery voltage in mV from a PA0 reading.
pub fn battery_mv(raw: u16, supply_mv: u16) -> u16 {
    (pin_mv(raw, supply_mv) * (BATTERY_DIV_TOP + BATTERY_DIV_BOTTOM) / BATTERY_DIV_BOTTOM).min(u16::MAX as u32) as u16
}

/// The battery current in mA from a PB7 reading.
pub fn current_ma(raw: u16, supply_mv: u16) -> u16 {
    (pin_mv(raw, supply_mv) * CURRENT_MA_PER_MV).min(u16::MAX as u32) as u16
}

/// mV to the 0.1 V units of block byte 14, rounded, capped at 25.5 V.
pub fn battery_decivolts(mv: u16) -> u8 {
    ((mv as u32 + 50) / 100).min(255) as u8
}

/// The 6 bytes served at `POWER_ADDR`.
pub fn power_bytes(battery_mv: u16, current_ma: u16, supply_mv: u16) -> [u8; POWER_LEN] {
    let mut out = [0u8; POWER_LEN];
    out[0..2].copy_from_slice(&battery_mv.to_le_bytes());
    out[2..4].copy_from_slice(&current_ma.to_le_bytes());
    out[4..6].copy_from_slice(&supply_mv.to_le_bytes());
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(id: u8, field: u8, params: &[u8]) -> ([u8; 64], usize) {
        let mut b = [0u8; 64];
        b[0] = 0xFF;
        b[1] = 0xFF;
        b[2] = id;
        b[3] = (params.len() + 2) as u8;
        b[4] = field;
        b[5..5 + params.len()].copy_from_slice(params);
        let sum = b[2..5 + params.len()].iter().fold(0u8, |a, x| a.wrapping_add(*x));
        b[5 + params.len()] = !sum;
        (b, params.len() + 6)
    }

    fn parse_all(bytes: &[u8]) -> Option<Frame> {
        let mut p = Parser::new();
        let mut last = None;
        for &b in bytes {
            if let Some(f) = p.feed(b) {
                last = Some(f);
            }
        }
        last
    }

    /// The checksum example from the protocol spec, `FF FF FE 06 82 1E 02 0B 0C 42`.
    #[test]
    fn parses_the_spec_example() {
        let f = parse_all(&[0xFF, 0xFF, 0xFE, 0x06, 0x82, 0x1E, 0x02, 0x0B, 0x0C, 0x42]).unwrap();
        assert_eq!((f.id, f.field), (0xFE, 0x82));
        assert_eq!(f.params(), &[0x1E, 0x02, 0x0B, 0x0C]);
    }

    #[test]
    fn a_bad_checksum_is_dropped_and_the_next_frame_still_parses() {
        let (mut a, na) = frame(MY_ID, PING, &[]);
        a[na - 1] ^= 1;
        let (b, nb) = frame(MY_ID, READ, &[56, 15]);
        let mut bytes = [0u8; 128];
        bytes[..na].copy_from_slice(&a[..na]);
        bytes[na..na + nb].copy_from_slice(&b[..nb]);
        let mut p = Parser::new();
        let frames: usize = bytes[..na + nb].iter().filter_map(|&x| p.feed(x)).count();
        assert_eq!(frames, 1);
    }

    #[test]
    fn leading_garbage_and_a_third_ff_are_tolerated() {
        let (f, n) = frame(MY_ID, PING, &[]);
        let mut bytes = [0u8; 32];
        bytes[..4].copy_from_slice(&[0x00, 0x13, 0xFF, 0x7E]);
        bytes[4] = 0xFF;
        bytes[5..5 + n].copy_from_slice(&f[..n]);
        assert_eq!(parse_all(&bytes[..5 + n]).unwrap().field, PING);
    }

    #[test]
    fn first_in_a_sync_read_answers_at_once() {
        let (b, n) = frame(BROADCAST, SYNC_READ, &[56, 15, MY_ID, 8, 11, 6]);
        let f = parse_all(&b[..n]).unwrap();
        let mut s = Slave::new();
        assert_eq!(s.on_frame(&f), Action::Read { addr: 56, len: 15 });
    }

    /// Listed third, it must let two replies pass before speaking.
    #[test]
    fn later_in_a_sync_read_waits_its_turn() {
        let (b, n) = frame(BROADCAST, SYNC_READ, &[56, 15, 8, 11, MY_ID]);
        let mut s = Slave::new();
        assert_eq!(s.on_frame(&parse_all(&b[..n]).unwrap()), Action::Nothing);
        let (r1, n1) = frame(8, 0, &[0; 15]);
        assert_eq!(s.on_frame(&parse_all(&r1[..n1]).unwrap()), Action::Nothing);
        let (r2, n2) = frame(11, 0, &[0; 15]);
        assert_eq!(
            s.on_frame(&parse_all(&r2[..n2]).unwrap()),
            Action::Read { addr: 56, len: 15 }
        );
        assert!(!s.waiting());
    }

    #[test]
    fn a_sync_read_without_us_is_ignored() {
        let (b, n) = frame(BROADCAST, SYNC_READ, &[56, 15, 1, 2, 3]);
        let mut s = Slave::new();
        assert_eq!(s.on_frame(&parse_all(&b[..n]).unwrap()), Action::Nothing);
        assert!(!s.waiting());
    }

    /// Our own reply, heard back on the shared wire, must never trigger another reply.
    #[test]
    fn our_own_echo_is_not_an_instruction() {
        let mut out = [0u8; MAX_FRAME];
        let r = Registers { block: [7u8; BLOCK_LEN], ..Registers::new(Baud::K500) };
        let n = reply(Action::Read { addr: 56, len: 15 }, &r, &mut out);
        let f = parse_all(&out[..n]).unwrap();
        assert_eq!(f.id, MY_ID);
        assert_eq!(Slave::new().on_frame(&f), Action::Nothing);
    }

    #[test]
    fn ping_and_read_are_answered() {
        let mut s = Slave::new();
        let (b, n) = frame(MY_ID, PING, &[]);
        assert_eq!(s.on_frame(&parse_all(&b[..n]).unwrap()), Action::Ack);
        let (b, n) = frame(MY_ID, READ, &[5, 3]);
        assert_eq!(
            s.on_frame(&parse_all(&b[..n]).unwrap()),
            Action::Read { addr: 5, len: 3 }
        );
    }

    #[test]
    fn the_map_serves_identity_and_the_block() {
        let mut r = Registers::new(Baud::K500);
        for (i, b) in r.block.iter_mut().enumerate() {
            *b = 100 + i as u8;
        }
        let mut out = [0u8; 4];
        read_map(&r, 5, &mut out);
        assert_eq!(out, [MY_ID, 1, 0, 0]);
        let mut out = [0u8; BLOCK_LEN];
        read_map(&r, BLOCK_ADDR, &mut out);
        r.diag = [1, 2, 3, 4, 5, 6, 7, 8];
        let mut d = [0u8; DIAG_LEN];
        read_map(&r, DIAG_ADDR, &mut d);
        assert_eq!(d, r.diag);
        // Byte 14 is the battery voltage, not the IMU loop's byte (no reading yet: 0).
        assert_eq!(out[..BLOCK_BATTERY], r.block[..BLOCK_BATTERY]);
        assert_eq!(out[BLOCK_BATTERY], 0);
    }

    /// The reply must be a frame the host's own parser accepts — checked by parsing it back.
    #[test]
    fn replies_round_trip_through_the_parser() {
        let r = Registers {
            block: [0x5Au8; BLOCK_LEN],
            power: power_bytes(11_100, 0, 3300),
            ..Registers::new(Baud::K500)
        };
        let mut out = [0u8; MAX_FRAME];
        let n = reply(Action::Read { addr: BLOCK_ADDR, len: 15 }, &r, &mut out);
        assert_eq!(n, 21);
        let f = parse_all(&out[..n]).unwrap();
        assert_eq!((f.id, f.field), (MY_ID, 0));
        assert_eq!(f.params()[..BLOCK_BATTERY], r.block[..BLOCK_BATTERY]);
        assert_eq!(f.params()[BLOCK_BATTERY], 111);
        assert_eq!(reply(Action::Ack, &r, &mut out), 6);
        assert_eq!(&out[..6], &[0xFF, 0xFF, MY_ID, 2, 0, !(MY_ID + 2)]);
    }

    /// Address 6 reads back the speed the board runs at, in Feetech's encoding, so a host
    /// checking it the way it checks a servo sees the truth.
    #[test]
    fn the_baud_register_follows_the_jumper() {
        let mut out = [0u8; 1];
        read_map(&Registers::new(Baud::K500), 6, &mut out);
        assert_eq!(out, [1]);
        read_map(&Registers::new(Baud::M1), 6, &mut out);
        assert_eq!(out, [0]);
        assert_eq!(Baud::K500.bits_per_second(), 500_000);
        assert_eq!(Baud::M1.bits_per_second(), 1_000_000);
    }

    #[test]
    fn power_readings_convert_to_millivolts_and_milliamps() {
        // VREFINT reads 1500 counts against a factory value of 1655 (taken at 3.0 V): 3.31 V.
        assert_eq!(supply_mv(1500, 1655), 3310);
        assert_eq!(supply_mv(0, 1655), 0);
        // 12.6 V (3S full) puts 2.272 V on PA0: 2819 counts at 3.3 V.
        let mv = battery_mv(2819, 3300);
        assert!((12_580..=12_620).contains(&mv), "{mv}");
        // 5 A through 2 mΩ × 50 = 0.5 V on PB7: 620 counts at 3.3 V.
        let ma = current_ma(620, 3300);
        assert!((4_980..=5_010).contains(&ma), "{ma}");
        assert_eq!(battery_decivolts(7_449), 74);
        assert_eq!(battery_decivolts(7_450), 75);
        assert_eq!(battery_decivolts(60_000), 255);
    }

    #[test]
    fn the_power_registers_and_block_byte_14_serve_the_readings() {
        let r = Registers { power: power_bytes(8_400, 1_250, 3_300), ..Registers::new(Baud::K500) };
        let mut out = [0u8; POWER_LEN];
        read_map(&r, POWER_ADDR, &mut out);
        assert_eq!(out, [0xD0, 0x20, 0xE2, 0x04, 0xE4, 0x0C]);
        let mut b = [0u8; 1];
        read_map(&r, BLOCK_ADDR + BLOCK_BATTERY as u8, &mut b);
        assert_eq!(b, [84]);
    }
}
