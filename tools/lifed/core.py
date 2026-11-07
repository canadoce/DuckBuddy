# -*- coding: utf-8 -*-
"""The duck's life layer, the part that decides: body homeostasis, drives, affect and the life
state machine (docs/project/duck-life-design-20261013-CN.md, L1).

Pure: no sockets, no clocks. `Life.step(dt, body, events)` takes what the robot reports and what
happened, and returns `Action`s for the IO side (lifed.py) to carry out. Everything here can be run
and tested on a PC.

The order of who decides, from the design: safety reflexes (robotd, not here) > body needs (heat,
battery, falls) > the user's explicit asks > what the duck does on its own.

Who has the controls (the user, 2026-10-14): with the gamepad there, the gamepad leads and voice
follows — a voice ask is carried out while the pad is idle, and the pad interrupts it; with no pad,
voice leads. So while the pad is in use (`Body.pad_active`) this layer moves nothing: no head
animation, no voice commands, and a body need that would sit the duck down is only voiced
(robotd's own guards still stop a hot walk). A rest or sleep this layer started, the pad ends.
"""
from __future__ import annotations

import math
import os
import random
import re
import sys
from dataclasses import dataclass, field

import mission
from attention import Attention
import prompts
import words

# duck-speak from English text (tools/persona/duckspeak.py, ~/persona on the robot)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "persona"))
import duckspeak  # noqa: E402

# ── Body ────────────────────────────────────────────────────────────────────────────────────────

# HL-2915 heat budget (2026-10-12): a servo that holds anything warms ~13 C a minute whatever the
# load; one that holds nothing cools ~4 C a minute. robotd refuses to walk at 70 C.
WALK_MAX_C = 70.0
HEAT_C_PER_S = 13.0 / 60.0
FULL_ACTIVITY_S = 150.0
BATTERY_TIRED_PCT = 15.0
LEG_JOINTS = (0, 1, 2, 3, 4, 10, 11, 12, 13, 14)
# The head pays for every move it makes: on the robot (2026-10-14) ten minutes of lifed's idle life
# — a breath that never stopped, glances, attention — took head_yaw to 66 C and the neck to 62 while
# the legs, rested, were at 45. Head activity fades from HEAD_CALM_C and stops at HEAD_STILL_C —
# under robotd's 70 C walking guard (the seller: the sixties are fine for the HL-2915); first set at
# 52 / 60, which stilled the head and sent the duck to rest well before it needed to.
HEAD_CALM_C = 60.0
HEAD_STILL_C = 68.0

POSTURES = ("off", "standing", "walking", "sitting", "lying", "resting", "rising", "fallen")


@dataclass
class Body:
    """What the robot reports, reduced to what the life layer needs."""
    t: float = 0.0
    policy: str = ""                # robot.state policy label
    fallen: bool = False
    gravity: tuple = (0.0, 0.0, -1.0)
    temps_c: list = field(default_factory=list)
    twist: tuple = (0.0, 0.0, 0.0)
    head_cmd: tuple = (0.0, 0.0, 0.0, 0.0)
    rest: dict | None = None        # robot.state rest block while resting
    battery_pct: float | None = None
    odom: tuple | None = None       # robotd's contact odometry: (x, y, yaw), metres / radians
    pad_present: bool = False       # a gamepad is connected (padd's tap)
    pad_active: bool = False        # ... and was used in the last few seconds

    @property
    def posture(self) -> str:
        p = self.policy
        if p in ("", "held", "limp"):
            # no policy driving: a limp robot on its side is switched off, not fallen
            return "off"
        # robotd's limp_pose also re-poses a robot let go on purpose (a deep rest abandoned): fallen only
        # when robotd says so, while it lands (limp_fall), or tipped past 60 deg (2026-10-18: a call
        # woke a deep-sitting duck, its re-pose read as a fall, and it stayed "fallen" sitting upright)
        if self.fallen or p == "limp_fall" or (p == "limp_pose" and self.gravity[2] > -0.5):
            return "fallen"
        if p == "limp_pose":
            return "rising"
        if self.rest and self.rest.get("phase") in ("resting", "bracing"):
            return "resting"
        if p in ("rise", "lie_rise"):
            return "rising"
        if p == "lie":
            return "lying"
        if p == "sit":
            return "sitting"
        if p in ("walk", "settle"):
            return "walking" if any(abs(v) > 0.02 for v in self.twist) else "standing"
        if p == "stand":
            return "standing"
        return "off"   # held, limp, empty: no policy driving, the life layer stays out of it

    @property
    def max_c(self) -> float | None:
        return max(self.temps_c) if self.temps_c else None

    @property
    def head_max_c(self) -> float | None:
        return max(self.temps_c[5:9]) if len(self.temps_c) >= 9 else None

    @property
    def leg_max_c(self) -> float | None:
        return max(self.temps_c[j] for j in LEG_JOINTS) if len(self.temps_c) >= 15 else self.max_c

    @property
    def head_activity(self) -> float:
        """1 with a cool head, fading to 0 (keep still) as it heats."""
        c = self.head_max_c
        if c is None:
            return 1.0
        return max(0.0, min(1.0, (HEAD_STILL_C - c) / (HEAD_STILL_C - HEAD_CALM_C)))

    def energy(self, max_c=None) -> float | None:
        """0-1: the activity left before the walking guard, over what a cool duck has."""
        c = self.max_c if max_c is None else max_c
        if c is None:
            return None
        return max(0.0, min(1.0, (WALK_MAX_C - c) / HEAT_C_PER_S / FULL_ACTIVITY_S))

    @property
    def head_free(self) -> bool:
        """The head may be animated: a policy holds the body up, or it rests seated with the head
        alive. Not lying (the head is part of the pose, and goes limp), not falling, not off."""
        post = self.posture
        if post == "resting":
            return not (self.rest or {}).get("deep", False) and (self.rest or {}).get("phase") == "resting"
        return post in ("standing", "sitting", "walking")


# ── Inner state ─────────────────────────────────────────────────────────────────────────────────

def _toward(x, target, dt, tau):
    return target + (x - target) * math.exp(-dt / tau) if tau > 0 else target


@dataclass
class Inner:
    """Drives (seconds-minutes), affect (seconds), mood (minutes). Events push affect; time pulls
    affect toward mood and mood toward the baseline."""
    social: float = 0.2       # wants company; grows alone, drops with any interaction
    curiosity: float = 0.3    # wants something new; grows, drops when it looks around
    arousal: float = 0.3      # 0 calm .. 1 excited
    valence: float = 0.2      # -1 unhappy .. 1 happy
    mood_arousal: float = 0.3
    mood_valence: float = 0.2

    SOCIAL_FILL_S = 600.0
    CURIOSITY_FILL_S = 90.0
    AFFECT_TAU_S = 25.0
    MOOD_TAU_S = 600.0
    BASE_AROUSAL, BASE_VALENCE = 0.3, 0.2

    IMPULSES = {
        # event: (arousal, valence, social reset?)
        "touch": (0.10, 0.30, True),
        "call": (0.30, 0.10, True),
        "person": (0.20, 0.20, True),
        "sound": (0.35, 0.00, False),
        "say": (0.15, 0.10, True),
        "fall": (0.50, -0.40, False),
        "hot": (0.00, -0.10, False),
        "rested": (0.05, 0.15, False),
        "woke": (0.20, 0.10, False),
        # the feeling it answered with (the brain's emotion tag) colours how it carries on
        "happy": (0.15, 0.25, False),
        "curious": (0.20, 0.05, False),
        "coy": (0.05, 0.20, False),
        "shy": (0.00, 0.10, False),
        "sleepy": (-0.20, 0.00, False),
        "sad": (-0.10, -0.25, False),
        "surprised": (0.35, 0.05, False),
    }

    def tick(self, dt: float, energy: float | None):
        self.social = min(1.0, self.social + dt / self.SOCIAL_FILL_S)
        self.curiosity = min(1.0, self.curiosity + dt / self.CURIOSITY_FILL_S)
        # tired pulls arousal down: an overheated duck is a calm duck
        base_a = self.BASE_AROUSAL * (1.0 if energy is None else 0.5 + 0.5 * energy)
        self.arousal = _toward(self.arousal, max(self.mood_arousal, base_a) if energy is None else base_a, dt, self.AFFECT_TAU_S)
        self.valence = _toward(self.valence, self.mood_valence, dt, self.AFFECT_TAU_S)
        self.mood_arousal = _toward(self.mood_arousal, self.arousal, dt, self.MOOD_TAU_S)
        self.mood_valence = _toward(self.mood_valence, self.valence, dt, self.MOOD_TAU_S)
        self.mood_valence = _toward(self.mood_valence, self.BASE_VALENCE, dt, 4 * self.MOOD_TAU_S)

    def impulse(self, kind: str):
        a, v, social = self.IMPULSES.get(kind, (0.0, 0.0, False))
        self.arousal = max(0.0, min(1.0, self.arousal + a))
        self.valence = max(-1.0, min(1.0, self.valence + v))
        if social:
            self.social = max(0.0, self.social - 0.6)

    def style(self, energy: float | None) -> tuple[float, float]:
        """(amplitude, speed) multipliers for every gesture: excited and happy is big and quick,
        tired is small and slow — the same nod, coloured by how the duck feels."""
        e = 1.0 if energy is None else energy
        amp = (0.6 + 0.5 * self.arousal + 0.2 * max(0.0, self.valence)) * (0.5 + 0.5 * e)
        speed = (0.7 + 0.6 * self.arousal) * (0.6 + 0.4 * e)
        return max(0.3, min(1.3, amp)), max(0.4, min(1.3, speed))


# ── Actions (what the IO side carries out) ──────────────────────────────────────────────────────

@dataclass
class Action:
    kind: str          # "gesture" | "gaze" | "sound" | "rest" | "wake" | "ask" | "speak" | "skill"
    args: dict = field(default_factory=dict)


# ── The life state machine ──────────────────────────────────────────────────────────────────────

STATES = ("OFF", "WAKING", "IDLE", "ATTENDING", "PLAYING", "RESTING", "SLEEPING", "FALLEN", "TIRED")

# words a local intent matcher maps to commands, until voiced brings real ones. Phrases match as
# whole words (words.py: "hi" is not in "this"), and not right after a negation ("don't sit down").
INTENTS = {
    "sleep": ("good night", "goodnight", "night night", "go to sleep", "go sleep", "go to bed", "time to sleep",
              "time for bed", "bedtime", "sleep now", "sleep time"),
    "wake": ("wake up", "get up", "stand up", "good morning", "rise and shine", "wakey wakey"),
    # resting is the deep rest too (the user, 2026-10-16: "rest" should let it all go, like sleep)
    "rest": ("take a rest", "have a rest", "get some rest", "go rest", "rest now", "rest a bit", "rest for a bit",
             "rest for a while", "time to rest", "take a break", "have a break"),
    "sit": ("sit down", "take a seat", "have a seat"),
    "greet": ("hello", "hi", "hiya", "howdy", "hey there", "good afternoon", "good evening"),
    # the speaker's loudness (lifed: the codec's own volume, kept across restarts)
    "vol_max": ("maximum volume", "max volume", "full volume", "volume to max", "volume to maximum",
                "volume all the way up", "turn it all the way up", "as loud as you can", "loudest"),
    "vol_half": ("half volume", "volume to half", "volume at half", "volume to fifty", "half the volume"),
    # louder / quieter: volume_of() below (patterns, not words)
    # ends the conversation (not plain "go play": "let's go play outside" is no goodbye)
    "bye": ("bye", "goodbye", "good bye", "bye bye", "byebye", "see you later", "see you soon", "see ya",
            "talk later", "talk to you later", "catch you later", "thats all", "that is all", "nothing else",
            "you can go play", "off you go"),
    # look: a colour photo to the brain (27B, multimodal), which answers about it (2026-10-17)
    "look": ("what is this", "whats this", "what is that", "whats that", "look at this", "look at that",
             "look at me", "what do you see", "what can you see", "what are you looking at", "look around",
             "can you see this", "take a look", "have a look"),
    # its phone page's address, read out (before "net": "your web address" is no scan)
    "addr": ("your address", "web address", "page address", "ip address", "your ip", "your website", "your url",
             "your web page", "your webpage", "where is your page"),
    # QR Wi-Fi provisioning (visiond): it looks for the phone's share-hotspot code. Not "go online":
    # "can you go online" is a question, not a request.
    "net": ("connect to wifi", "connect to the wifi", "join wifi", "join the wifi", "connect to the internet",
            "connect to the network", "join the network", "join a network", "set up wifi", "wifi setup",
            "scan the code", "scan the qr code", "scan this code", "scan qr", "scan a qr code"),
    # only while it is looking for a Wi-Fi code (otherwise "never mind" is just talk)
    "cancel": ("cancel", "never mind", "nevermind", "forget it", "stop scanning", "stop looking", "dont connect",
               "do not connect", "no need"),
}
# A greeting only when that is about all that was said: "hey, what's the weather like" is a question
# for the brain, not a hello.
INTENT_MAX_WORDS = {"greet": 4}
# One-word commands that count only as the whole of what was said, give or take a "please" or a
# "now": "sleep" or "sit please" is a command, "did you sleep well" is not.
WHOLE = {"sleep": "sleep", "rest": "rest", "sit": "sit", "goodnight": "sleep"}
WHOLE_FILLERS = {"please", "now", "ok", "okay", "hey", "go", "you", "can", "just", "and", "then", "so", "alright"}


# Just after a conversation, the commands that only power things down work without the name, said
# short: "bye... go to sleep" (the user, 2026-10-16, was ignored for want of the name). Otherwise a
# "good night" said to someone else stays theirs. Anything that gets it up always needs the name.
DOWN_INTENTS = ("sleep", "rest", "sit", "bye")
DOWN_MAX_WORDS = 5
AFTER_CONVO_S = 60.0


# "turn your voice down a bit" missed the word list and went to the brain, which said it would turn
# it down and could not (2026-10-17). A complaint says which way first ("you're too quiet, louder
# please"); a request says what to change: "is your voice loud?" is a question.
VOL_DOWN_COMPLAINT = re.compile(r"\b(too loud|so loud|too noisy|hurts my ears)\b")
VOL_UP_COMPLAINT = re.compile(r"\b(too quiet|too soft|(cant|cannot|can not) hear( you)?|hard to hear|barely hear)\b")
VOL_UP = re.compile(r"\b(louder|speak up|volume up|turn (it |the volume |yourself |your voice )?up|"
                    r"(raise|increase) (the |your )?volume|more volume)\b")
VOL_DOWN = re.compile(r"\b(quieter|softer|volume down|turn (it |the volume |yourself |your voice )?down|"
                      r"(lower|decrease|reduce) (the |your )?volume|less volume|keep it down|not so loud)\b")


# a mission's control words, only while there is one to control (otherwise "start" / "continue" /
# "stop" are talk). "stop" must never be missed: the stopping words match anywhere, even negated.
MISSION_WORDS = (
    ("cancel", ("proposed", "running", "paused"), ("cancel", "never mind", "nevermind", "forget it", "dont go",
                                                   "do not go", "dont start", "abort", "call it off")),
    ("halt", ("running",), ("stop", "halt", "freeze", "wait", "hold on", "hold it", "dont move", "do not move",
                            "stay", "stand still", "whoa", "woah")),
    ("go", ("proposed",), ("start", "go", "lets go", "go ahead", "begin", "set off")),
    ("resume", ("paused",), ("continue", "keep going", "go on", "carry on", "resume", "go again")),
)
# The words that set it moving ("go", "continue") count only when they are all that was said, give
# or take these: "okay, go" and "you can start now" start it, "go to sleep" does not.
MOVE_FILLERS = {"please", "now", "ok", "okay", "alright", "then", "so", "you", "can", "yes", "yeah", "sure",
                "well", "and", "right", "hey", "again", "walking", "moving"}


def _only(ws: list[str], phrases) -> bool:
    """Whether `ws`, without MOVE_FILLERS, is made of nothing but `phrases` (one or more of them)."""
    rest = [w for w in ws if w not in MOVE_FILLERS]
    ps = sorted((words.words(p) for p in phrases), key=len, reverse=True)
    i = 0
    while i < len(rest):
        p = next((p for p in ps if rest[i:i + len(p)] == p), None)
        if p is None:
            return False
        i += len(p)
    return bool(rest)


def _without_name(text: str, name: str) -> list[str]:
    """The words of `text`, its own name left out (voiced takes it out already; typed text may have it)."""
    ws, n = words.words(text), words.words(name)
    if n:
        for i in range(len(ws) - len(n), -1, -1):
            if ws[i:i + len(n)] == n:
                del ws[i:i + len(n)]
    return ws


def mission_word(text: str, state: str | None, name: str = "") -> str | None:
    if state is None:
        return None
    ws = _without_name(text, name)
    for kind, states, phrases in MISSION_WORDS:
        if state not in states:
            continue
        if kind in ("go", "resume") and _only(ws, phrases):
            return kind
        if kind in ("cancel", "halt") and words.any_of(ws, phrases, negatable=False):
            return kind
    return None


def volume_of(t: str) -> str | None:
    t = " ".join(words.words(t))
    if VOL_DOWN_COMPLAINT.search(t):
        return "quieter"
    if VOL_UP_COMPLAINT.search(t):
        return "louder"
    if VOL_UP.search(t):
        return "louder"
    if VOL_DOWN.search(t):
        return "quieter"
    return None


def intent_of(text: str, name: str = "") -> str | None:
    ws = _without_name(text, name)
    for name, phrases in INTENTS.items():
        if len(ws) <= INTENT_MAX_WORDS.get(name, len(ws)) and words.any_of(ws, phrases):
            return name
    core = [w for w in ws if w not in WHOLE_FILLERS]
    if len(core) == 1 and core[0] in WHOLE:
        return WHOLE[core[0]]
    if not core and "hey" in ws:
        return "greet"                   # "hey!" alone; "hey, stop it" is no hello
    return volume_of(text)


@dataclass
class Config:
    # Who it is: its persona's name and knobs (tools/persona; lifed passes them in — the defaults
    # here are a lively, talkative duck). `lively` livens the idle life (more moves, a higher resting
    # arousal); `talkative` makes it call out more and sooner.
    name: str = "Biscuit"
    lively: float = 0.8
    talkative: float = 0.8
    rest_energy: float = 0.2          # ask robotd to rest below this energy, standing still
    rest_head_c: float = 66.0         # rest deep (the head limp too) if the head is this hot
    attend_s: float = 20.0            # attention lapses after this long without anything
    idle_min_s: float = 3.0           # gap between idle gestures, scaled by arousal / curiosity
    idle_max_s: float = 12.0
    sound_gap_s: float = 2.5
    lonely_social: float = 0.85       # past this, the duck calls for company
    fall_window_s: float = 300.0
    falls_to_rest: int = 3
    quiet: bool = False               # no unprompted sounds
    # A deep rest (the head limp too) for sleep and a hot head. robotd gets down for it by lying
    # (the lie policy) or, with `[thermal] deep_sit`, by sitting — seated on a flat floor the whole
    # robot let go stays put (2026-10-14), the stand-in while LieDown still lands hard. Off, both
    # rest seated with only the legs limp.
    deep_ok: bool = True
    # Talk to the online brain (tools/duckbrain, through the frp tunnel) about what is said to it.
    # Off, it only nods and takes the command words.
    brain: bool = True
    think_s: float = 1.2              # still no answer after this: tilt and hum "mm~" while it thinks
    ask_timeout_s: float = 8.0
    # A conversation (the user, 2026-10-16, after xiaozhi's wake flow): its name opens one, and while
    # it lasts what is said is for the duck without saying the name again. It closes once this long
    # passes with nobody talking after the duck's last answer, or on a goodbye.
    convo_s: float = 30.0
    # How long each person's-voice clip lasts (prompts.py), from the recorded files; missing ones are
    # estimated from the text
    voice_s: dict = field(default_factory=dict)
    # Missions (mission.py): "off"; "dry" — run on a stand-in robot, nothing moves; "real" — lifed
    # walks the robot (calibrated odometry, the ToF stop, the pad and "stop" over it)
    missions: str = "off"


# The eyes (attention.py, docs/project/attention-gaze-design-20261018-CN.md): while it is awake and its
# head free, visiond watches (faces, what moves) - slowly when nothing is going on, fast with someone
# there; lifed renews the watch before it ends. A target's gaze is held this long and renewed while it
# stays the focus; it is re-aimed only when the target has moved this far (a warm head: twice as far).
WATCH_S = 6.0
WATCH_RENEW_S = 4.0
WATCH_HZ_CALM, WATCH_HZ_ENGAGED = 2.0, 5.0
GAZE_HOLD_S = 2.0
GAZE_REAIM = 0.06
FACE_SIGMA, MOTION_SIGMA, NEAR_SIGMA = math.radians(3), math.radians(6), math.radians(12)
CALL_EL = 0.25                 # looking toward a voice, a little up: a standing person's face is high
HEAD_STILL_S = 0.9             # motion counts only from a head this still (its own turn moves the picture)
FACE_HEAD_FAST_S = 0.3         # a face seen while the head swung is placed wrong: dropped


class Life:
    def __init__(self, config: Config | None = None, rng: random.Random | None = None):
        self.cfg = config or Config()
        self.rng = rng or random.Random()
        self.inner = Inner()
        # the persona tunes the knobs: talkative calls sooner and leaves less quiet between sounds,
        # lively moves more and rests at a higher arousal
        c = self.cfg
        c.lonely_social = min(c.lonely_social, 0.95 - 0.3 * c.talkative)
        c.sound_gap_s = max(1.0, c.sound_gap_s * (1.3 - 0.6 * c.talkative))
        c.idle_min_s *= 1.3 - 0.6 * c.lively
        c.idle_max_s *= 1.3 - 0.6 * c.lively
        self.inner.BASE_AROUSAL = 0.25 + 0.15 * c.lively
        self.inner.arousal = self.inner.mood_arousal = self.inner.BASE_AROUSAL
        self.state = "OFF"
        self.since = 0.0               # time in the current state
        self.t = 0.0
        self.next_idle = 2.0
        self.last_sound = -1e9
        self.falls: list[float] = []
        self.attend_yaw = 0.0
        self.last_interaction = 0.0
        self.pending_wake = False
        self.own_rest = False          # a rest / sleep this layer asked for (not a hot one)
        self.pad = False               # the pad has the controls this tick
        self.warned_hot = -1e9
        self.rest_backoff_until = -1e9   # after a rest (or one robotd did not take), no new one yet
        self.asking_since: float | None = None   # waiting on the brain since
        self.thinking_cued = False
        self.last_reply: dict | None = None
        # its own voice comes back through its microphone; what is heard while it speaks (and just
        # after) is itself, not someone talking to it
        self.deaf_until = -1e9
        self.convo_until = -1e9        # in a conversation until then
        self.convo_id = 0
        self.convo_live = False
        self.convo_ended = -1e9
        self.scanning_since: float | None = None   # looking for a Wi-Fi QR code since
        self.voice_text, self.voice_until = "", -1e9  # the last person's-voice clip, and when it ends
        self.saying_name = False       # its duck-speak line has its own name in it
        self.last_spoke = -1e9           # when it last said something (an expression, a clip)
        self.mission_state: str | None = None   # proposed | running | paused (lifed runs it)
        # where the eyes go: targets heard and seen, the focus, the gaze it keeps up
        self.att = Attention()
        self.gaze_tid, self.gaze_aim, self.gaze_hold_until, self.gaze_at = None, (0.0, 0.0), -1e9, -1e9
        self.gaze_away = False
        self.watch_renew_at, self.watch_hz = -1e9, 0.0
        self.head_last: tuple | None = None
        self.head_moved_at = self.head_fast_at = -1e9
        self.people_seen: set = set()
        # what was said both ways, for the phone page: {"t", "who": "you" | "duck", "text", ...}
        self.dialog: list[dict] = []
        self.quiet_close = False       # it said its own goodbye: no closing coo after it
        self.log: list[str] = []
        self._fresh: list[str] = []

    # helpers ---------------------------------------------------------------------------------

    def _note(self, line: str):
        self.log.append(line)
        self.log = self.log[-50:]
        self._fresh.append(line)

    def drain_log(self) -> list[str]:
        """Lines noted since the last call (lifed prints them)."""
        out, self._fresh = self._fresh, []
        return out

    def _go(self, state: str, why: str):
        if state != self.state:
            self._note(f"{self.t:8.1f}s {self.state} -> {state}: {why}")
            self.state, self.since = state, 0.0

    def _sound(self, out, tag, prompted=False):
        if (self.cfg.quiet and not prompted) or self.t - self.last_sound < self.cfg.sound_gap_s:
            return
        self.last_sound = self.t
        out.append(Action("sound", {"tag": tag}))

    def _gesture(self, out, name, body, **kw):
        if body.head_free and not self.pad and body.head_activity > 0.0:
            amp, speed = self.inner.style(body.energy())
            amp *= 0.5 + 0.5 * body.head_activity
            out.append(Action("gesture", {"name": name, "amp": amp, "speed": speed, **kw}))

    def _dialog(self, who: str, text: str, **kw):
        self.dialog.append({"t": round(self.t, 2), "who": who, "text": text, **kw})
        self.dialog = self.dialog[-40:]

    QR_SAYS = {
        # result: (emotion, say, pre, gesture, body, meaning); the duck-speak is made from `say`
        "joined": ("happy", "Connected!", "chirp", "nod", "bounce", "I'm on {ssid} now!"),
        "read": ("happy", "Got it!", "chirp", "nod", "none", "I can see the QR code for {ssid}."),
        "already": ("happy", "Already on!", "chirp", "nod", "none", "I'm already on {ssid}."),
        "joining": ("curious", "Let's see~", "chirp", "nod", "none", "I can see the QR code for {ssid}. Connecting..."),
        "not_found": ("sad", "Can't find it~", "coo", "shake", "none", "I can't find {ssid}... is the hotspot on?"),
        "timeout": ("sad", "Didn't see it~", "coo", "shake", "none", "I didn't see a QR code... let's try again."),
        "not_wifi": ("curious", "Not Wi-Fi~", "inquire", "tilt", "none", "This QR code is not for joining a network."),
        "failed": ("sad", "Can't connect~", "coo", "droop", "shrink", "I can't connect to {ssid}... is the password right?"),
    }

    def _qr_expression(self, ev: dict) -> dict:
        r = ev.get("result", "failed")
        emotion, say, pre, gesture, body, meaning = self.QR_SAYS.get(r, self.QR_SAYS["failed"])
        return {"emotion": emotion, "say": say, "pinyin": duckspeak.syllables(say), "pre": pre, "gesture": gesture,
                "body": body, "action": "none", "meaning": meaning.format(ssid=ev.get("ssid") or "that network"),
                "via": "vision",
                "voice": r if r in prompts.PROMPTS else None,
                # on a phone's hotspot its page has an address you cannot know: it reads it out
                "then": "address" if r == "joined" else None}

    def in_convo(self) -> bool:
        return self.t < self.convo_until

    def _open_convo(self, why: str, until: float | None = None):
        """Open a conversation, or keep the open one going until `until` (default: convo_s from now)."""
        if not self.in_convo():
            self.convo_id += 1
            self._note(f"{self.t:8.1f}s conversation {self.convo_id} open: {why}")
        self.convo_until = max(self.convo_until, self.t + self.cfg.convo_s if until is None else until)

    def _addressed(self, ev: dict) -> bool:
        """Whether something said is for the duck: with its name (voiced's `named`), or inside a
        conversation. Typed events without `named` keep their `addressed` (default yes)."""
        if "named" in ev:
            return bool(ev["named"]) or self.in_convo()
        return bool(ev.get("addressed", True)) or self.in_convo()

    def _gaze(self, out, body, yaw, pitch, hold_s):
        """Look somewhere — unless the head is too hot to move: then the eyes stay where they are."""
        if body.head_activity > 0.0:
            k = 0.5 + 0.5 * body.head_activity
            out.append(Action("gaze", {"yaw": yaw * k, "pitch": pitch * k, "hold_s": hold_s}))

    # the step ----------------------------------------------------------------------------------

    def step(self, dt: float, body: Body, events: list[dict]) -> list[Action]:
        out: list[Action] = []
        self.t += dt
        self.since += dt
        energy = body.energy()
        self.inner.tick(dt, energy)
        post = body.posture
        self._head_motion(dt, body)
        self.att.decay(self.t, dt)

        # the pad takes the controls: end what this layer started, then stand back
        took = body.pad_active and not self.pad
        self.pad = body.pad_active
        if took:
            self._note(f"{self.t:8.1f}s pad has the controls")
            if self.own_rest and self.state in ("RESTING", "SLEEPING", "TIRED"):
                out.append(Action("wake"))
                self.own_rest = False
                self._go("WAKING", "the pad took over")
            out.append(Action("gaze_stop"))

        # events first: they are what makes the duck feel present (band 2, < 300 ms)
        for ev in events:
            kind = ev.get("type", "")
            if kind in ("say", "call") and self._own_clip(ev.get("text", "")) and not self._answer_to_clip(
                    ev.get("text", "")):
                self._note(f"{self.t:8.1f}s heard its own clip? ignored {ev.get('text')!r}")
                continue
            if kind == "call" and self.t < self.voice_until:
                continue                     # a clip says what to do: not cut short by a call
            if kind == "call" and self.t < self.deaf_until and self.saying_name:
                self._note(f"{self.t:8.1f}s heard its name while saying it: not a call")
                continue
            self._attend_event(ev, body)
            if kind == "say":
                # words count only when meant for the duck: said with its name, or in a conversation
                ev = {**ev, "addressed": self._addressed(ev)}
                text = ev.get("text", "")
                intent = intent_of(text, self.cfg.name)
                if intent == "cancel" and self.scanning_since is None:
                    intent = None
                clip_playing = self.t < self.voice_until + 0.8 and not ev.get("named")
                if clip_playing:
                    # while a person's-voice clip plays (they have command words in them, duck-speak has
                    # none), what it hears without its name is the clip (2026-10-17: reading its address,
                    # it heard "my page address is" and started over, three times)
                    intent = None
                after = self.t - self.convo_ended < AFTER_CONVO_S
                if not ev["addressed"] and not (after and intent in DOWN_INTENTS
                                                and len(words.words(text)) <= DOWN_MAX_WORDS):
                    intent = None
                # a mission: its control words while one is on ("stop" without the name too, and even
                # while a clip plays: no clip says it), a route
                if self.cfg.missions != "off":
                    ctl = mission_word(text, self.mission_state, self.cfg.name)
                    if clip_playing and ctl != "halt":
                        ctl = None
                    if ctl and (ev["addressed"] or ctl == "halt"):
                        self._mission_control(ctl, text, body, out)
                        continue
                    route = mission.parse_route(text) if ev["addressed"] and not clip_playing else None
                    if route is not None:
                        self._mission_route(route, text, body, out)
                        continue
                if intent:
                    ev = {"type": "command", "name": intent, "text": text}
                    kind = "command"
            self.inner.impulse(kind if kind != "command" else "say")
            if kind in ("touch", "call", "person", "say", "command"):
                self.last_interaction = self.t
            if kind == "reply":
                self._perform(ev, body, out)
                continue
            if kind == "judged":
                # Jev's view of something said (lifed IO): next to it on the phone page
                for d in reversed(self.dialog):
                    if d["who"] == "you" and d["text"] == ev.get("text"):
                        d["jev"] = ev.get("summary") or {}
                        break
                continue
            if kind == "ignored":
                # Jev took it as not for the duck, or as needing no answer: stop waiting, say nothing
                self.asking_since = None
                self._note(f"{self.t:8.1f}s not answered {ev.get('text')!r}: {ev.get('why', '')}")
                continue
            if kind == "mission":
                self._mission_event(ev, body, out)
                continue
            if kind == "volume":
                # the phone page's slider
                self._volume(out, {"set": int(ev.get("set", 100))}, f"Volume set to {int(ev.get('set', 100))}.")
                continue
            if kind == "qr":
                # visiond's answer to "connect to Wi-Fi": said by the duck, not the brain ("joining": still at it)
                if ev.get("result") != "joining":
                    self.scanning_since = None
                if ev.get("result") in ("cancelled", "busy"):
                    continue                 # said already ("Okay, I won't connect") / still at the first one
                self._perform(self._qr_expression(ev), body, out)
                continue
            if self.pad and kind in ("command", "say"):
                self._note(f"{self.t:8.1f}s ignored {ev}: the pad has the controls")
                continue
            self._on_event(ev, body, out)

        # waiting on the brain: a thinking tilt and hum once it takes a while, and give up eventually
        if self.asking_since is not None:
            waited = self.t - self.asking_since
            if waited > self.cfg.think_s and not self.thinking_cued:
                self.thinking_cued = True
                if not self.pad:
                    self._gesture(out, "tilt", body, side=self.rng.choice((-1, 1)))
                out.append(Action("speak", {"pinyin": "n1 ~", "mood": "curious"}))
                self.deaf_until = max(self.deaf_until, self.t + 1.5)
            if waited > self.cfg.ask_timeout_s:
                self.asking_since = None

        if self.scanning_since is not None and self.t - self.scanning_since > 150.0:   # 30 s look + joining
            self.scanning_since = None
            self._note(f"{self.t:8.1f}s no answer from the eyes")

        live = self.in_convo()
        if self.convo_live and not live:
            self.convo_ended = self.t
            self._note(f"{self.t:8.1f}s conversation {self.convo_id} over"
                       + (": the brain heard a farewell" if self.quiet_close else ""))
            if not self.pad and self.state in ("IDLE", "ATTENDING") and not self.quiet_close:
                self._sound(out, "coo")      # a soft "mm" as it lets you go
            self.quiet_close = False
        self.convo_live = live

        # body needs come before everything the duck does on its own
        if post == "off":
            if self.state not in ("OFF", "SLEEPING"):
                self._go("OFF", "no policy driving")
            return self._mind_own_voice(out)
        if post == "fallen":
            if self.state != "FALLEN":
                self.falls = [f for f in self.falls if self.t - f < self.cfg.fall_window_s] + [self.t]
                self.inner.impulse("fall")
                self._sound(out, "alarm", prompted=True)
                self._go("FALLEN", f"fell ({len(self.falls)} in {self.cfg.fall_window_s:.0f} s)")
            return self._mind_own_voice(out)

        self._eyes(body, out)
        handler = getattr(self, f"_in_{self.state.lower()}")
        handler(dt, body, out)
        return self._mind_own_voice(out)

    # a bank call is 0.1-0.7 s; the VAD holds on for its tail; then it is someone else again
    OWN_SOUND_DEAF_S = 1.3

    def _mind_own_voice(self, out):
        """Whatever it makes a sound, it does not take the next moment's hearing for someone
        talking to it (2026-10-15: its own answering quack came back as "ah", inside the
        addressed window, and went to the brain as a question)."""
        if any(a.kind == "sound" for a in out):
            self.deaf_until = max(self.deaf_until, self.t + self.OWN_SOUND_DEAF_S)
        return out

    # events --------------------------------------------------------------------------------------

    def _on_event(self, ev, body, out):
        kind = ev.get("type")
        if kind == "command":
            name = ev.get("name")
            if ev.get("text"):
                self._dialog("you", ev["text"], command=name)
            if name == "bye":
                # a goodbye ends the conversation: a coo and a nod, then back to listening for its name
                self._sound(out, "coo", prompted=True)
                self._gesture(out, "nod", body, times=1)
                if self.in_convo():
                    self.convo_until = self.convo_ended = self.t
                    self._note(f"{self.t:8.1f}s conversation {self.convo_id} over: goodbye")
                    self.convo_live = False
                return
            if name not in ("quiet",) + DOWN_INTENTS:
                self._open_convo(f"told {name}")
            if name == "sleep" and self.state not in ("SLEEPING", "OFF"):
                self._sound(out, "coo", prompted=True)
                out.append(Action("rest", {"on": True, "deep": self.cfg.deep_ok}))
                self.own_rest = True
                self._go("SLEEPING", "told to sleep")
            elif name == "wake" and self.state in ("SLEEPING", "RESTING"):
                out.append(Action("wake"))
                self.own_rest = False
                self.pending_wake = True
                self._go("WAKING", "told to wake")
            elif name == "wake" and self.state in ("IDLE", "ATTENDING") and body.posture == "sitting":
                out.append(Action("skill", {"skill": "sit_toggle"}))      # "stand up", from a powered sit
            elif name == "rest" and self.state in ("IDLE", "ATTENDING", "RESTING"):
                self._sound(out, "coo", prompted=True)
                out.append(Action("rest", {"on": True, "deep": self.cfg.deep_ok}))
                self.own_rest = True
                self._go("RESTING", "told to rest")
            elif name == "sit" and self.state in ("IDLE", "ATTENDING") and body.posture == "standing":
                out.append(Action("skill", {"skill": "sit_toggle"}))
            elif name == "greet":
                self._greet(body, out)
            elif name == "cancel" and self.scanning_since is not None:
                out.append(Action("vision", {"cmd": "stop"}))
                self.scanning_since = None
                self._perform({"emotion": "curious", "say": "Okay~", "pinyin": duckspeak.syllables("Okay~"), "pre": "none",
                               "gesture": "nod", "body": "none", "action": "none", "voice": "cancelled",
                               "meaning": "Okay, I won't connect.", "via": "vision"}, body, out)
            elif name in self.VOLUME_SAYS:
                args, meaning = self.VOLUME_SAYS[name]
                self._volume(out, args, meaning)
            elif name == "look":
                if body.posture == "walking":
                    self._note(f"{self.t:8.1f}s asked to look while walking: not now (a blurred photo)")
                else:
                    # look up at what is held out (where the head points: at whoever holds it), a
                    # curious sound, and the brain answers about the photo; the thing stays the focus a
                    # few seconds, then the eyes go back to the person
                    hy, _ = self._head_pose(body)
                    self.att.observe(self.t, "object", hy, self._heading(body), el=0.2, salience=1.6)
                    self._gaze(out, body, hy, 0.2, 8.0)
                    self._sound(out, "inquire", prompted=True)
                    out.append(Action("look", {"text": ev.get("text") or "What do you see?",
                                               "session": f"c{self.convo_id}"}))
                    self.asking_since, self.thinking_cued = self.t, False
                    self._dialog("duck", "Let me see~", meaning="Let me have a look.", via="vision")
            elif name == "addr":
                out.append(Action("voice", {"clip": "address", "pinyin": "", "mood": "happy"}))
                self._voice_heard("address", 0.0)
                self._dialog("duck", "(reads out its address)", meaning="Here is my page address.", via="vision")
            elif name == "net" and body.posture != "walking" and self.scanning_since is None:
                # look up at the phone and say so; visiond scans and answers with a `qr` event
                out.append(Action("vision", {"cmd": "scan_qr", "timeout_s": 30.0}))
                # what to do is said in a person's words (prompts.py); duck-speak without the clip
                out.append(Action("voice", {"clip": "scan_start", "pinyin": duckspeak.syllables("Let me see~"),
                                            "mood": "curious"}))
                self._voice_heard("scan_start", 0.0)
                if body.head_free and not self.pad:
                    self._gaze(out, body, 0.0, 0.35, 30.0)
                self.scanning_since = self.t
                self._dialog("duck", "Let me see~", meaning="Let me see your QR code.", via="vision")
            elif name == "quiet":
                self.cfg.quiet = True
            elif name == "unquiet":
                self.cfg.quiet = False
            return
        if kind == "call" and self.t < self.deaf_until:
            # called while it talks: stop and listen (an empty speak silences robotd)
            out.append(Action("speak", {"pinyin": "", "mood": ""}))
            self.deaf_until = self.t
            self._note(f"{self.t:8.1f}s interrupted: listening")
        if kind == "call":
            self._open_convo("called")
        if self.state == "SLEEPING":
            # asleep: a touch or a call is a stir, not a waking; spoken to, it answers sleepily
            # (the brain hears that it is asleep) without getting up
            if kind in ("touch", "call"):
                self._sound(out, "coo", prompted=True)
            if not (kind == "say" and ev.get("addressed", True)):
                return
        if self.pad:
            # the pad is driving: answer with a sound, leave the head to the pad
            if kind in ("touch", "call"):
                self._sound(out, "coo" if kind == "touch" else "inquire", prompted=True)
            return
        if kind == "touch":
            self._sound(out, "coo", prompted=True)
            self._gesture(out, "tilt", body, side=self.rng.choice((-1, 1)))
        elif kind == "call":
            self._sound(out, "inquire", prompted=True)
            self.attend_yaw = self._heard_yaw(ev, body)
            self._gaze(out, body, self.attend_yaw, 0.15, 3.0)
            if self.state in ("IDLE",):
                self._go("ATTENDING", "called")
        elif kind == "person" and self.state not in ("IDLE", "ATTENDING"):
            # someone came close (the head ToF) while it is off, resting, walking or getting up:
            # noticed, not greeted
            self._note(f"{self.t:8.1f}s someone close ({ev.get('dist', '?')} m) while {self.state}")
        elif kind == "near":
            # the ToF saw something come close: a glance while the eyes (camera + Jev) find out what
            if not self.pad:
                self._gaze(out, body, 0.0, 0.25, 2.0)
        elif kind == "person" and ev.get("via") == "jev" and not ev.get("present", True):
            self._note(f"{self.t:8.1f}s something close, but nobody there (Jev)")
        elif kind == "person":
            activity = ev.get("activity")
            self.attend_yaw = float(ev.get("yaw", 0.0))
            self._gaze(out, body, self.attend_yaw, 0.2, 4.0)
            if activity in ("passing", "busy"):
                self._note(f"{self.t:8.1f}s someone {activity}: a look, no hello")
                return
            first = self.t - self.last_interaction > 60.0 or self.state == "IDLE"
            if activity == "thumbs_up":
                self._sound(out, "chirp", prompted=True)
                self._gesture(out, "nod", body, times=2)
            elif activity == "reaching":
                self._sound(out, "coo", prompted=True)
                self._gesture(out, "lean_in", body)
            elif first or activity == "waving":
                self._greet(body, out)
            if self.state == "IDLE":
                self._go("ATTENDING", "someone is here")
        elif kind == "sound":
            self._gaze(out, body, float(ev.get("yaw", 0.0)), 0.0, 1.5)
        elif kind == "say" and self.t < self.deaf_until:
            self._note(f"{self.t:8.1f}s heard itself? ignored {ev.get('text')!r}")
        elif kind == "say":
            if not ev.get("addressed", True):
                return                                         # not for the duck
            self._open_convo("spoken to")
            self._dialog("you", ev.get("text", ""), **({"speaker": ev["speaker"]} if ev.get("speaker") else {}))
            self._gesture(out, "nod", body, times=1)        # heard you
            if self.cfg.brain and ev.get("text"):
                out.append(Action("ask", {"text": ev["text"], "session": f"c{self.convo_id}",
                                          "named": bool(ev.get("named", True)), "speaker": ev.get("speaker")}))
                self.asking_since, self.thinking_cued = self.t, False
            if self.state == "IDLE":
                self._go("ATTENDING", "spoken to")
        elif kind == "hearing":
            # someone starts talking (voiced: speech onset): in a conversation, look at them - unless the
            # eyes are on someone already
            focus = self.att.focus
            if self.in_convo() and self.t >= self.deaf_until and not (focus and focus.tid is not None):
                self._gaze(out, body, self.attend_yaw, 0.15, 3.0)

    # the brain's answer, performed ---------------------------------------------------------------

    GESTURE_OF = {"nod": "nod", "shake": "shake", "tilt": "tilt", "look_up": "look_up", "droop": "droop",
                  "nuzzle": "nuzzle"}
    # the walking policy was never trained to track a body pose (its tracking weight is 0), so a
    # body move is said with the neck instead
    BODY_OF = {"bounce": "bob", "lean_in": "lean_in", "shrink": "shrink"}

    def _perform(self, e: dict, body, out):
        """An expression from the brain: a call, a few words of duck-speak, a head gesture (the
        body's move as the neck's), and — only if it fits what the duck is doing — an action."""
        self.asking_since = None
        self.last_reply = e
        self.last_spoke = self.t
        mood = e.get("emotion") or "happy"
        self.inner.impulse(mood)
        self.last_interaction = self.t
        delay = 0.0
        pre = e.get("pre")
        if pre and pre != "none":
            self.last_sound = self.t
            out.append(Action("sound", {"tag": pre}))
            delay = 0.45
        syllables = sum(1 for w in (e.get("pinyin") or "").split() if w[-1:].isdigit())
        self.saying_name = words.has(words.words(e.get("say") or ""), self.cfg.name, negatable=False)
        if e.get("voice"):
            # a moment that needs instructions: a person's words (prompts.py), duck-speak without the clip
            out.append(Action("voice", {"clip": e["voice"], "pinyin": e.get("pinyin", ""), "mood": mood,
                                        "delay_s": delay, "then": e.get("then")}))
            self._voice_heard(e["voice"], delay)
            if e.get("then"):
                self.voice_until += prompts.seconds(e["then"])
                self.deaf_until = max(self.deaf_until, self.voice_until + 0.8)
        elif e.get("pinyin"):
            out.append(Action("speak", {"pinyin": e["pinyin"], "mood": mood, "delay_s": delay}))
        self.deaf_until = max(self.deaf_until, self.t + delay + 0.25 * syllables + 1.2)
        if self.in_convo() and e.get("end") is True:
            # the brain heard a farewell ("I'm off to work then"): the conversation ends once it has said bye
            self.convo_until = self.deaf_until
            self.quiet_close = True
        elif self.in_convo():
            # the conversation waits for you from when it has finished, not from when you spoke
            self._open_convo("answered", until=self.deaf_until + self.cfg.convo_s)
        g = self.GESTURE_OF.get(e.get("gesture") or "")
        b = self.BODY_OF.get(e.get("body") or "")
        if g == "nod":
            self._gesture(out, "nod", body, times=2 if mood in ("happy", "surprised") else 1)
        elif g == "shake":
            self._gesture(out, "shake", body, times=2)
        elif g == "tilt":
            self._gesture(out, "tilt", body, side=self.rng.choice((-1, 1)))
        elif g:
            self._gesture(out, g, body)
        elif b:
            self._gesture(out, b, body)
        act = e.get("action") or "none"
        if act != "none" and not self.pad:
            # only what makes sense from here: no waking a duck that is not asleep, no sitting a
            # duck that is walking; and never powering one up (nothing here does)
            awake = self.state in ("IDLE", "ATTENDING")
            if act == "sit" and awake and body.posture == "standing":
                out.append(Action("skill", {"skill": "sit_toggle"}))
            elif act == "stand" and awake and body.posture == "sitting":
                out.append(Action("skill", {"skill": "sit_toggle"}))
            elif act in ("stand", "wake") and self.state in ("SLEEPING", "RESTING"):
                # Getting up powers the legs: only the command words do that (wake up / get up / stand up
                # ...), never the brain's own reading of a sentence. 2026-10-16: "what's wrong?" to the sleeping
                # duck came back as wake, and it stood up — on a leg half rebuilt — and fell 3 times.
                self._note(f"{self.t:8.1f}s brain asked {act!r} from {self.state}: only the wake words get it up")
            elif {"rest": awake, "sleep": self.state not in ("SLEEPING", "OFF")}.get(act, False):
                self._on_event({"type": "command", "name": act}, body, out)
            else:
                self._note(f"{self.t:8.1f}s brain asked {act!r}, not from {self.state} / {body.posture}")
        self._note(f"{self.t:8.1f}s {self.cfg.name}[{mood}] {e.get('say', '')}  ({e.get('meaning', '')})")
        self._dialog("duck", e.get("say", ""), emotion=mood, meaning=e.get("meaning", ""), via=e.get("via", "brain"),
                     **({"photo": e["photo"]} if e.get("photo") else {}))

    VOLUME_SAYS = {
        "louder": ({"step": 15}, "Okay, a bit louder."),
        "quieter": ({"step": -15}, "Okay, a bit quieter."),
        "vol_max": ({"set": 100}, "All the way up."),
        "vol_half": ({"set": 50}, "Half volume."),
    }

    def _volume(self, out, args: dict, meaning: str):
        """Change the loudness (lifed sets it and keeps it) and chirp at the new one, so it is heard."""
        out.append(Action("volume", args))
        self.last_sound = self.t
        out.append(Action("sound", {"tag": "chirp"}))
        self.deaf_until = max(self.deaf_until, self.t + self.OWN_SOUND_DEAF_S)
        self._dialog("duck", "Chirp~", emotion="happy", meaning=meaning, via="vision")

    # missions: the words and the reports (lifed runs it: mission.py) ------------------------------

    def _clip(self, out, body, key: str, meaning: str, emotion: str = "happy", gesture: str = "none"):
        self._perform({"emotion": emotion, "say": "", "pinyin": "", "pre": "none", "gesture": gesture,
                       "body": "none", "action": "none", "voice": key, "meaning": meaning, "via": "mission"}, body, out)

    def _mission_route(self, route, text: str, body, out):
        self._dialog("you", text, command="route")
        self._open_convo("a route")
        if route.problem:
            # unclear or out of bounds: ask, or say why not, in a person's words
            key = {"turn_or_side": "ask_turn_or_side", "how_far": "ask_how_far"}.get(route.problem, route.problem)
            self._clip(out, body, key, prompts.PROMPTS.get(key, ""), emotion="curious", gesture="tilt")
            return
        moves = any(s.skill in ("walk", "turn") for s in route.steps)
        if self.cfg.missions == "real" and moves and body.posture not in ("standing", "walking"):
            # walking needs it up first, and only the name and the wake words get it up
            self._clip(out, body, "mission_need_stand", prompts.PROMPTS["mission_need_stand"], emotion="curious")
            return
        if self.mission_state in ("running", "paused"):
            out.append(Action("mission", {"cmd": "cancel"}))
        out.append(Action("mission", {"cmd": "propose", "text": text, "steps": route.steps}))
        self.mission_state = "proposed"
        said = " → ".join(s.words() for s in route.steps)
        dry = self.cfg.missions == "dry"
        self._clip(out, body, "mission_ready_dry" if dry else "mission_ready",
                   f"I will: {said}.{' (A dry run: I will not really move.)' if dry else ''} Say \"start\" and I will set off.",
                   gesture="nod")

    def _mission_control(self, ctl: str, text: str, body, out):
        self._dialog("you", text, command=ctl)
        self._open_convo(f"mission {ctl}")
        if ctl == "go":
            out.append(Action("mission", {"cmd": "start"}))
            self.mission_state = "running"
            self._perform({"emotion": "happy", "say": "Let's go!", "pinyin": duckspeak.syllables("Let's go!"),
                           "pre": "chirp", "gesture": "nod", "body": "none", "action": "none", "meaning": "Off I go!",
                           "via": "mission"}, body, out)
        elif ctl == "halt":
            out.append(Action("mission", {"cmd": "pause", "why": "told"}))
            self.mission_state = "paused"
            self._clip(out, body, "mission_paused", prompts.PROMPTS["mission_paused"])
        elif ctl == "resume":
            out.append(Action("mission", {"cmd": "resume"}))
            self.mission_state = "running"
            self._perform({"emotion": "happy", "say": "Okay!", "pinyin": duckspeak.syllables("Okay!"), "pre": "chirp",
                           "gesture": "nod", "body": "none", "action": "none", "meaning": "Carrying on.",
                           "via": "mission"}, body, out)
        elif ctl == "cancel":
            out.append(Action("mission", {"cmd": "cancel"}))
            self.mission_state = None
            self._clip(out, body, "mission_cancelled", prompts.PROMPTS["mission_cancelled"])

    def _mission_event(self, ev: dict, body, out):
        what = ev.get("what")
        if what == "step_done":
            self._dialog("duck", "", emotion="happy", meaning=f"✓ {ev.get('words', '')}"
                         + (f" ({ev['note']})" if ev.get("note") else ""), via="mission")
        elif what == "done":
            self.mission_state = None
            self._clip(out, body, "mission_done", f"All done: {ev.get('words', '')}", gesture="nod")
        elif what == "failed":
            self.mission_state = None
            self._clip(out, body, "mission_failed",
                       f"I could not do \"{ev.get('words', '')}\" ({ev.get('why', '')}), so I stopped.",
                       emotion="sad", gesture="shake")
        elif what == "paused":
            self.mission_state = "paused"
            if ev.get("why") == "obstacle":
                self._clip(out, body, "mission_obstacle", prompts.PROMPTS["mission_obstacle"], emotion="surprised")
            else:
                self._clip(out, body, "mission_paused", f"I stopped ({ev.get('why', '')}). Say continue and I will keep going.")

    def _voice_heard(self, key: str, delay: float):
        """A clip starts in `delay` s: deaf to itself while it plays, and its words known (_own_clip)."""
        s = self.cfg.voice_s.get(key) or prompts.seconds(key)
        self.voice_text = (prompts.PROMPTS["addr_intro"] + " " + prompts.PROMPTS["addr_port"] if key == "address"
                           else prompts.PROMPTS.get(key, ""))
        self.voice_until = self.t + delay + s + 0.6      # + the hush round trip and aplay's start
        self.deaf_until = max(self.deaf_until, self.voice_until + 0.8)

    def _answer_to_clip(self, text: str) -> bool:
        """A word the clip asked for, said back on its own a moment after the clip: the person, not the
        echo. An echo comes in under a second after the clip ends (the recogniser's lag) and is a phrase
        of it ("... say start and I will set off"); someone answering takes longer and says just the
        word ("start": dropped as the echo 1.0 s after "say start", 2026-10-17)."""
        ws = [w for w in words.words(text) if not w.isdigit()]
        if len(ws) > 3 or self.t < self.voice_until + 0.4:
            return False
        if mission_word(text, self.mission_state, self.cfg.name) is not None:
            return True
        return self.scanning_since is not None and intent_of(text, self.cfg.name) == "cancel"

    def _own_clip(self, text: str) -> bool:
        """Heard soon after a clip, and mostly its words (word pairs in the clip's order): the clip
        coming back through the mic. (2026-10-17: "I don't want to connect, cancel it", said after
        the clip, shares only single words with it.)"""
        if not self.voice_text or self.t > self.voice_until + 4.0:
            return False
        # numbers as the recogniser writes them ("<robot-ip>", "8088") are not in a clip's words: left
        # out (the address came back as "...<robot-ip>, colon 8088..." and closed the conversation)
        ws = [w for w in words.words(text) if not w.isdigit()]
        clip = words.words(self.voice_text)
        if not ws:
            return False
        if len(ws) < 2:
            return ws[0] in clip and self.t < self.voice_until + 1.5
        pairs = set(zip(clip, clip[1:]))
        covered = [False] * len(ws)
        for i in range(len(ws) - 1):
            if (ws[i], ws[i + 1]) in pairs:
                covered[i] = covered[i + 1] = True
        return sum(covered) >= 0.6 * len(ws)

    @staticmethod
    def _heard_yaw(ev: dict, body) -> float:
        """Where a call came from, in the body frame. voiced hears with the two mics on the head, so its
        direction is the head's: add the head's yaw (2026-10-18). An unsure one (dir_ok false) is
        straight ahead, as before there was a direction."""
        yaw = float(ev.get("yaw", 0.0))
        if ev.get("dir_ok") is False:
            return 0.0
        head = body.head_cmd[2] if len(body.head_cmd) > 2 else 0.0
        return max(-1.0, min(1.0, head + yaw))

    # the eyes ------------------------------------------------------------------------------------

    @staticmethod
    def _heading(body) -> float:
        """Which way the body faces in the world (robotd's odometry), 0 without it."""
        return float(body.odom[2]) if body.odom and len(body.odom) > 2 else 0.0

    @staticmethod
    def _head_pose(body) -> tuple[float, float]:
        """(yaw, pitch up) the head is at, body frame (robot.state's head command)."""
        hc = body.head_cmd
        return (float(hc[2]) if len(hc) > 2 else 0.0, -float(hc[1]) if len(hc) > 1 else 0.0)

    def _head_motion(self, dt: float, body):
        pose = self._head_pose(body)
        if self.head_last is not None and dt > 0:
            d = abs(pose[0] - self.head_last[0]) + abs(pose[1] - self.head_last[1])
            if d > 0.01:
                self.head_moved_at = self.t
            if d / dt > 0.4:
                self.head_fast_at = self.t
        self.head_last = pose

    def _attend_event(self, ev: dict, body):
        """What is heard and seen, into the attention's targets (world frame: the body's heading added).
        Directions from the head (the mics, the camera) get the head's pose added."""
        kind, t = ev.get("type"), self.t
        heading = self._heading(body)
        hy, hp = self._head_pose(body)
        if kind in ("call", "say"):
            if kind == "say" and (t < self.deaf_until or t < self.voice_until):
                return                                   # its own voice
            if ev.get("dir_ok") is None and "yaw" not in ev:
                return                                   # typed (the phone page): from nowhere
            if ev.get("dir_ok") is False:
                if kind == "say":
                    return
                yaw, mirror, sigma = 0.0, None, math.radians(40)   # called from somewhere: ahead, unsure
            else:
                yaw = hy + float(ev.get("yaw", 0.0))
                mirror = hy + float(ev["yaw_back"]) if ev.get("yaw_back") is not None else None
                sigma = max(float(ev.get("dir_sigma") or 0.0), math.radians(10))
            if kind == "call":
                self.att.observe(t, "call", yaw, heading, el=CALL_EL, sigma=sigma, mirror_body=mirror)
            else:
                self.att.observe(t, "voice", yaw, heading, el=CALL_EL, sigma=sigma, mirror_body=mirror,
                                 talking=True, salience=1.0 if self._addressed(ev) else 0.5)
        elif kind == "face":
            if t - self.head_fast_at < FACE_HEAD_FAST_S:
                return
            size = float(ev.get("size", 0.0))
            tid = self.att.observe(t, "person", hy + float(ev.get("yaw_cam", 0.0)), heading,
                                   el=hp + float(ev.get("pitch_cam", 0.0)), sigma=FACE_SIGMA, facing=True)
            if tid not in self.people_seen:
                self.people_seen.add(tid)
                self.inner.impulse("person")
                self._note(f"{self.t:8.1f}s a face, {size:.2f} of the view wide")
            if size >= 0.06:
                # someone near enough, looking at it: company (the attention follows them)
                self.last_interaction = t
                if self.state == "IDLE":
                    self._go("ATTENDING", "someone looking at me")
        elif kind == "motion":
            if t - self.head_moved_at < HEAD_STILL_S:
                return
            self.att.observe(t, "motion", hy + float(ev.get("yaw_cam", 0.0)), heading,
                             el=hp + float(ev.get("pitch_cam", 0.0)), sigma=MOTION_SIGMA,
                             salience=min(1.0, 0.5 + 10.0 * float(ev.get("size", 0.0))))
        elif kind == "near":
            dist = ev.get("dist")
            self.att.observe(t, "near", hy, heading, el=hp, dist=float(dist) if dist is not None else None,
                             sigma=NEAR_SIGMA)
        elif kind == "sound" and "yaw" in ev:
            self.att.observe(t, "sound", hy + float(ev["yaw"]), heading, sigma=math.radians(20))
        elif kind == "watch_end" and not ev.get("faces"):
            f = self.att.focus
            if f is not None and f.tid is not None and f.kind in ("call", "voice"):
                self.att.not_found(t, f.tid)             # looked there and saw no one

    def _eyes(self, body, out):
        """Keep visiond watching while the eyes are open: awake (idle, attending), the head free, not
        walking, not looking for a QR code. Fast with someone there, slow otherwise."""
        if not (self.state in ("IDLE", "ATTENDING") and body.head_free and not self.pad
                and body.posture != "walking" and self.scanning_since is None and body.head_activity > 0.0):
            return
        f = self.att.focus
        engaged = self.in_convo() or (f is not None and f.tid is not None)
        hz = WATCH_HZ_ENGAGED if engaged else WATCH_HZ_CALM
        if self.t >= self.watch_renew_at or hz > self.watch_hz:
            out.append(Action("vision", {"cmd": "watch", "seconds": WATCH_S, "hz": hz}))
            self.watch_renew_at, self.watch_hz = self.t + WATCH_RENEW_S, hz

    def _attend(self, body, out):
        """The focus (attention.py), and the eyes kept on it while it is a target: aimed at once at a
        new one, re-aimed when it moves, the hold renewed while it lasts. A focus without a target
        (wandering) is left to the idle life's own pace."""
        f = self.att.select(self.t, self.state, self._heading(body), self._head_pose(body)[0], self.rng,
                            conversing=self.in_convo(), thinking=self.asking_since is not None,
                            walking=body.posture == "walking", heat_ok=body.head_activity >= 1.0)
        if f.tid is None:
            self.gaze_tid = None
            return f
        tg = self.att.targets.get(f.tid)
        if tg is not None and f.kind == "person" and tg.facing and self.t - tg.seen > 3.0 \
                and self.t - self.att.focus_since > 3.0:
            tg.facing = False                            # looked at, and no face there any more
            self.att.not_found(self.t, f.tid)
        if f.kind in ("person", "call", "voice"):
            self.attend_yaw = f.yaw
        reaim = GAZE_REAIM * (1.0 if body.head_activity >= 1.0 else 2.0)
        away = f.mode == "look_away"
        new = f.tid != self.gaze_tid or away != self.gaze_away
        moved = (abs(f.yaw - self.gaze_aim[0]) > reaim or abs(f.el - self.gaze_aim[1]) > reaim) \
            and self.t - self.gaze_at > 0.3
        if new or moved or self.t > self.gaze_hold_until - 0.5:
            self._gaze(out, body, f.yaw, f.el, GAZE_HOLD_S)
            self.gaze_tid, self.gaze_aim, self.gaze_away = f.tid, (f.yaw, f.el), away
            self.gaze_hold_until, self.gaze_at = self.t + GAZE_HOLD_S, self.t
        return f

    def _greet(self, body, out):
        self._sound(out, "greet", prompted=True)
        self._gesture(out, "nod", body, times=2)

    # states --------------------------------------------------------------------------------------

    def _in_off(self, dt, body, out):
        if body.posture == "resting":
            # lifed (re)started on a resting duck: it is asleep or resting, not waking up
            deep = bool((body.rest or {}).get("deep"))
            self._go("SLEEPING" if deep else "RESTING", "found resting")
            return
        # a person started the policy: wake up into the day
        self._go("WAKING", f"policy driving ({body.posture})")

    def _in_waking(self, dt, body, out):
        post = body.posture
        if post in ("lying", "resting", "rising"):
            return   # still getting up; robotd does that
        if self.pad and self.since < 8.0:
            return   # started from the pad: wake up once the hands are off it
        if self.since >= 0.3 and not getattr(self, "_woke_done", False):
            self._woke_done, self._woke_at = True, self.since
            self.inner.impulse("woke")
            if not self.pad:
                out.append(Action("gesture", {"name": "wake_up", "amp": 1.0, "speed": 1.0}))
            self._sound(out, "greet", prompted=True)
        if getattr(self, "_woke_done", False) and self.since > getattr(self, "_woke_at", 0.0) + 4.0:
            self._woke_done = False
            self.pending_wake = False
            self._go("IDLE", "awake")

    def _needs(self, body, out) -> bool:
        """Body needs, checked from the active states. True if one took over."""
        energy = body.energy(body.leg_max_c)
        still = body.posture in ("standing", "sitting")
        if body.battery_pct is not None and body.battery_pct < BATTERY_TIRED_PCT and not self.pad:
            out.append(Action("rest", {"on": True, "deep": False}))
            self._sound(out, "inquire", prompted=True)
            self._go("TIRED", f"battery {body.battery_pct:.0f}%")
            return True
        if self.t < self.rest_backoff_until:
            return False
        hot_head = (self.cfg.deep_ok and body.head_max_c is not None
                    and body.head_max_c >= self.cfg.rest_head_c)
        recent_falls = [f for f in self.falls if self.t - f < self.cfg.fall_window_s]
        if still and (hot_head or (energy is not None and energy < self.cfg.rest_energy)
                      or len(recent_falls) >= self.cfg.falls_to_rest):
            why = ("head hot" if hot_head else "tired" if energy is not None and energy < self.cfg.rest_energy
                   else "fell too often")
            if self.pad:
                # not under the user's hands: say so, and rest once they let go
                if self.t - self.warned_hot > 30.0:
                    self.warned_hot = self.t
                    self._sound(out, "coo", prompted=True)
                    self._note(f"{self.t:8.1f}s wants to rest ({why}); the pad has the controls")
                return False
            self.inner.impulse("hot")
            self._sound(out, "coo", prompted=True)
            out.append(Action("rest", {"on": True, "deep": hot_head}))
            self.own_rest = False     # a body need: the pad does not cancel it
            self.falls = []
            self._go("RESTING", why)
            return True
        return False

    def _in_idle(self, dt, body, out):
        if body.posture == "walking":
            self._go("PLAYING", "walking")
            return
        if self._needs(body, out):
            return
        if body.posture == "resting":
            self._go("RESTING", "resting (robotd)")
            return
        if self.pad:
            return
        f = self._attend(body, out)
        # alone too long: call for company, once in a while
        if self.inner.social > self.cfg.lonely_social:
            self._sound(out, "inquire")
            if f.tid is None:
                self._gaze(out, body, 0.0, 0.2, 2.0)
            self.inner.social -= 0.35
        self.next_idle -= dt
        if self.next_idle <= 0:
            self._idle_gesture(body, out, f)
            a = self.inner.arousal * 0.6 + self.inner.curiosity * 0.4
            span = self.cfg.idle_max_s - (self.cfg.idle_max_s - self.cfg.idle_min_s) * a
            e = body.energy()
            if e is not None:
                span *= 1.0 + (1.0 - e)        # tired: fewer moves
            span /= 0.15 + 0.85 * body.head_activity   # a warm head: fewer still
            self.next_idle = self.rng.uniform(0.6, 1.4) * span

    def _idle_gesture(self, body, out, focus=None):
        r = self.rng.random()
        if r < 0.55 + 0.25 * self.inner.curiosity:
            if focus is not None and focus.tid is not None:
                return                           # the eyes are on something: no look about
            if focus is not None and focus.mode == "wander":
                # where it has not looked lately, or where someone was (attention.py)
                yaw, pitch = focus.yaw * (0.5 + 0.5 * self.inner.curiosity), focus.el
            else:
                yaw = self.rng.uniform(-0.7, 0.7) * (0.5 + 0.5 * self.inner.curiosity)
                pitch = self.rng.uniform(-0.15, 0.25)
            self._gaze(out, body, yaw, pitch, self.rng.uniform(1.0, 3.5))
            self.inner.curiosity = max(0.0, self.inner.curiosity - 0.25)
        elif r < 0.85:
            self._gesture(out, "tilt", body, side=self.rng.choice((-1, 1)))
            self.inner.curiosity = max(0.0, self.inner.curiosity - 0.15)
        else:
            self._gesture(out, "nod", body, times=1)

    def _in_attending(self, dt, body, out):
        if body.posture == "walking":
            self._go("PLAYING", "walking")
            return
        if self._needs(body, out):
            return
        if not self.in_convo() and self.t - self.last_interaction > self.cfg.attend_s:
            self._go("IDLE", "attention lapsed")
            return
        if self.pad:
            return
        f = self._attend(body, out)
        # keep looking at them (where they were, if the eyes have no one), with a small nod now and then
        self.next_idle -= dt
        if self.next_idle <= 0:
            if f.tid is None:
                self._gaze(out, body, self.attend_yaw + self.rng.uniform(-0.1, 0.1), 0.2, 3.0)
            if self.rng.random() < 0.4:
                self._gesture(out, "nod", body, times=1)
            self.next_idle = self.rng.uniform(2.5, 5.0)

    def _in_playing(self, dt, body, out):
        if body.posture != "walking" and self.since > 1.0:
            self._go("IDLE", "stopped walking")
            self.next_idle = 1.5

    def _in_resting(self, dt, body, out):
        post = body.posture
        if self.since > 6.0 and post in ("standing",) and not body.rest:
            # rested — or robotd never took the rest: either way, not again for a minute
            self.rest_backoff_until = self.t + 60.0
            self.inner.impulse("rested")
            self.own_rest = False
            self._sound(out, "greet", prompted=True)
            self._go("IDLE", "rested")
            return
        # resting seated with the head alive: it can still look about, slowly
        if body.head_free and not self.pad:
            self.next_idle -= dt
            if self.next_idle <= 0:
                self._gaze(out, body, self.rng.uniform(-0.4, 0.4), -0.05, self.rng.uniform(2.0, 5.0))
                self.next_idle = self.rng.uniform(6.0, 14.0)

    def _in_sleeping(self, dt, body, out):
        if body.posture == "standing" and self.since > 10.0 and not body.rest:
            # robotd got it up (a hot rest ends by itself): it's awake after all
            self._go("WAKING", "got up")

    def _in_tired(self, dt, body, out):
        if body.battery_pct is not None and body.battery_pct > BATTERY_TIRED_PCT + 5:
            self._go("IDLE", "battery back")
            return
        if self.since > 120.0:
            self._sound(out, "inquire")
            self.since = 0.0

    def _in_fallen(self, dt, body, out):
        # up again - on its feet, or sitting (a fall that ended seated, or a re-pose that was none)
        if body.posture in ("standing", "sitting") and self.since > 2.0:
            self._go("IDLE", "back up" if body.posture == "standing" else "upright again, sitting")
            self.next_idle = 2.0

    def snapshot(self, body: Body) -> dict:
        i = self.inner
        return {
            "state": self.state, "since_s": round(self.since, 1), "posture": body.posture,
            "energy": None if body.energy() is None else round(body.energy(), 2),
            "head_energy": None if body.head_max_c is None else round(body.energy(body.head_max_c), 2),
            "head_activity": round(body.head_activity, 2),
            "battery_pct": body.battery_pct, "max_c": body.max_c, "head_max_c": body.head_max_c,
            "social": round(i.social, 2), "curiosity": round(i.curiosity, 2),
            "arousal": round(i.arousal, 2), "valence": round(i.valence, 2),
            "mood": [round(i.mood_arousal, 2), round(i.mood_valence, 2)],
            "pad": "active" if body.pad_active else "present" if body.pad_present else "absent",
            "own_rest": self.own_rest,
            "asking": self.asking_since is not None,
            "convo_s_left": round(max(0.0, self.convo_until - self.t), 1),
            "scanning": self.scanning_since is not None,
            "t": round(self.t, 2),
            "dialog": self.dialog[-20:],
            "last_reply": self.last_reply,
            "quiet": self.cfg.quiet, "falls_recent": len([f for f in self.falls if self.t - f < self.cfg.fall_window_s]),
            "log": self.log[-8:],
            "attention": self.att.snapshot(self.t, self._heading(body)),
        }
