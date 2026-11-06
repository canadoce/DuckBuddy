# -*- coding: utf-8 -*-
"""The duck's small brain: a whole answer without the network (step 3 of the 2026-10-16 plan).

When the online brain (tools/duckbrain, through frp) cannot be reached — outdoors with no hotspot,
the V100 box down — the duck still answers what is said to it, in the same expression format the
online brain returns (emotion, a few words of duck-speak with their syllables, a call before them,
a head gesture, a body move, an action, and a meaning line for the human). Duck-speak carries no
words anyone understands, so what matters is the expression: an intent matched from keywords
(whole words, words.py), and one of a few answers for it, coloured by how the duck is (asleep,
tired, hot, hungry, happy).

Pure: no clocks, no IO. `respond(text, mind, rng)`; the duck-speak syllables of each line are made
from its English words by duckspeak.py (tools/persona), with no extra package on the robot.
"""
from __future__ import annotations

import os
import random
import re
import sys
from dataclasses import dataclass

import words

# duck-speak from English text (tools/persona/duckspeak.py, ~/persona on the robot)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "persona"))
import duckspeak  # noqa: E402


@dataclass
class Mind:
    """What the small brain knows of the duck right now (lifed fills it in)."""
    asleep: bool = False
    posture: str = "standing"
    energy: float | None = None        # 0 tired .. 1 fresh (legs)
    head_hot: bool = False
    battery_pct: float | None = None
    valence: float = 0.2               # -1 unhappy .. 1 happy
    arousal: float = 0.3
    hour: int | None = None            # local hour, None if the clock is not set (no RTC, no NTP yet)
    minute: int = 0


def E(emotion, say, pre, gesture, body, meaning, action="none"):
    return {"emotion": emotion, "say": say, "pre": pre, "gesture": gesture, "body": body,
            "action": action, "meaning": meaning}


# intent: (keywords, answers). Earlier intents win, so the specific ones go first.
INTENTS = [
    ("sorry", ("sorry", "i apologize", "my bad", "forgive me"), [
        E("coy", "It's okay~", "coo", "nuzzle", "lean_in", "It's okay, I'm not upset."),
        E("happy", "Mm-hm!", "coo", "nod", "none", "All right, all right, I forgive you."),
    ]),
    ("thanks", ("thank you", "thanks", "thank", "many thanks"), [
        E("shy", "Hehe~", "coo", "tilt", "shrink", "You're welcome. I'm happy I could help."),
        E("happy", "You're welcome!", "chirp", "nod", "bounce", "No need to thank me!"),
    ]),
    ("love", ("love you", "i like you", "like you", "miss you", "my favorite", "youre my favorite"), [
        E("shy", "Hehe~", "coo", "nuzzle", "shrink", "You're my favorite too. I'm all shy now."),
        E("coy", "Me too!", "coo", "nuzzle", "lean_in", "I like you too. Stay with me always, okay?"),
    ]),
    ("praise", ("good boy", "good girl", "good duck", "well done", "good job", "great job", "clever", "smart", "cute",
                "adorable", "so pretty", "beautiful", "amazing", "awesome", "youre great", "you are great",
                "the best", "brilliant"), [
        E("happy", "Quack quack!", "chirp", "nod", "bounce", "You said something nice about me, I'm so happy!"),
        E("shy", "Hehe~", "coo", "tilt", "shrink", "Oh, all that praise makes me a little shy."),
        E("happy", "Hahaha!", "chirp", "look_up", "bounce", "Haha, I think I'm pretty great too!"),
    ]),
    ("scold", ("stupid", "dumb", "bad duck", "bad boy", "bad girl", "naughty", "hate you", "annoying", "shut up",
               "be quiet", "idiot", "go away"), [
        E("sad", "Aww...", "coo", "droop", "shrink", "Aww, you're telling me off. That makes me a little sad."),
        E("sad", "Quack...", "peck", "shake", "shrink", "Hmph, I'm not stupid..."),
        E("coy", "Don't~", "peck", "shake", "none", "Please don't talk to me like that."),
    ]),
    ("hug", ("hug", "hugs", "cuddle", "pet you", "kiss", "snuggle"), [
        E("coy", "Hug~", "coo", "nuzzle", "lean_in", "A hug! I love being close to you."),
        E("happy", "Quack~", "coo", "nuzzle", "none", "That feels so nice. Pet me some more."),
    ]),
    ("comfort", ("im sad", "i am sad", "so sad", "feel sad", "feeling sad", "upset", "im tired", "i am tired",
                 "so tired", "crying", "cry", "bad day", "feel bad", "feel down", "stressed"), [
        E("sad", "Hug~", "coo", "nuzzle", "lean_in", "Don't be sad. I'm here with you. Here's a hug."),
        E("coy", "There, there~", "coo", "nuzzle", "lean_in", "There, there. I'm right here."),
    ]),
    ("joke", ("joke", "make me laugh", "funny", "haha", "hahaha", "hahahaha", "lol", "laugh"), [
        E("happy", "Hahaha!", "chirp", "look_up", "bounce", "Hahaha, you make me laugh!"),
        E("happy", "Quack quack quack!", "chirp", "nod", "bounce", "Quack quack, that's so funny!"),
    ]),
    ("sing", ("sing", "song", "sing a song", "sing for me"), [
        E("happy", "La la la~", "chirp", "nod", "bounce", "La la la, here's a duck song for you!"),
        E("shy", "Quack quack quack~", "coo", "tilt", "bounce", "I can only sing quack, so don't laugh at me."),
    ]),
    ("dance", ("dance", "play with me", "lets play", "play a game", "wiggle"), [
        E("happy", "Yay, yay!", "chirp", "nod", "bounce", "Yay, let's play together!"),
        E("happy", "Quack quack!", "chirp", "look_up", "bounce", "Great, playing is my favorite!"),
    ]),
    ("look", ("look at me", "look here", "over here", "come here", "come over"), [
        E("curious", "Hmm?", "inquire", "look_up", "lean_in", "You called me? I'm looking at you."),
        E("happy", "Coming!", "chirp", "nod", "lean_in", "I'm right here, looking at you."),
    ]),
    ("nod", ("nod", "nod your head", "do you agree", "agree", "is that right", "am i right"), [
        E("happy", "Mm-hm!", "none", "nod", "none", "Yes, yes, that's right!"),
    ]),
    ("shake", ("shake your head", "shake"), [
        E("coy", "Nope~", "peck", "shake", "none", "No, no~"),
    ]),
    ("who", ("who are you", "whats your name", "what is your name", "your name", "what are you"), [
        E("happy", "{name}!", "greet", "nod", "bounce", "I'm {name}, a little robot duck!"),
        E("happy", "Quack quack! {name}!", "greet", "look_up", "bounce", "My name is {name}, and I'm your little duck!"),
    ]),
    ("age", ("how old", "birthday", "where are you from", "where do you live", "your age"), [
        E("curious", "Hmm...", "inquire", "tilt", "none", "I don't know how old I am. I think I was born not long ago."),
        E("happy", "Quack?", "inquire", "tilt", "lean_in", "I live right here in your home."),
    ]),
    ("online", ("internet", "online", "offline", "network", "your brain", "wifi"), [
        E("sad", "Can't connect~", "coo", "droop", "shrink", "I can't get online right now, so I'm thinking with my little head."),
    ]),
    ("weather", ("weather", "raining", "rain", "is it cold", "sunny", "outside"), [
        E("curious", "Quack?", "inquire", "tilt", "none", "I don't know what the weather is like outside."),
        E("curious", "Don't know~", "inquire", "look_up", "none", "I can't see outside. Will you tell me?"),
    ]),
    ("bye", ("bye", "goodbye", "see you later", "good night", "goodnight"), [
        E("coy", "Bye bye~", "coo", "nod", "none", "Bye bye. Come back and play with me soon."),
    ]),
    ("hello", ("hello", "hi", "hey", "good morning", "good afternoon", "good evening", "howdy", "im back",
               "i am back", "im home", "i am home"), [
        E("happy", "Quack quack!", "greet", "nod", "bounce", "Hello! I'm so happy to see you!"),
        E("happy", "Hello!", "greet", "look_up", "bounce", "You're here! I've been waiting for you!"),
    ]),
]

# dynamic intents: their answer depends on the duck's state (handled in respond)
DYNAMIC = [
    ("tired", ("are you tired", "you tired", "are you sleepy", "you sleepy", "want to sleep", "need a rest",
               "need to rest", "rested enough", "enough rest")),
    ("hot", ("are you hot", "you hot", "too hot", "feel hot", "overheating", "fever", "burning")),
    ("hungry", ("are you hungry", "you hungry", "hungry", "battery", "charge", "charging", "eat", "food")),
    ("time", ("what time", "the time", "time is it", "what hour")),
    # asking after the duck: the sure phrases come before the keyword intents ("hi, how are you" is
    # no hello), the loose ones after them ("how is the weather" is about the weather)
    ("how", ("how are you", "are you okay", "are you ok", "you okay", "are you happy", "your mood", "whats wrong",
             "what is wrong", "whats up", "what are you doing", "what you doing", "how do you feel",
             "how are you feeling", "hows it going", "how is it going")),
    ("how", ("how is it", "hows it", "up to", "doing")),
]

HOUR_WORDS = ("twelve", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven")


def hour_words(h: int) -> str:
    """The 12-hour clock in words: 0 -> twelve, 13 -> one, 14 -> two, 10 -> ten, 11 -> eleven."""
    return HOUR_WORDS[h % 12]


def part_of_day(h: int) -> str:
    return ("at night" if h < 5 else "in the morning" if h < 11 else "around noon" if h < 13
            else "in the afternoon" if h < 18 else "in the evening" if h < 23 else "at night")


def _dynamic(name: str, m: Mind) -> list[dict]:
    if name == "tired":
        if m.energy is not None and m.energy < 0.35:
            return [E("sleepy", "Bit tired~", "coo", "droop", "shrink", "My legs are a bit tired. I'd like to sit and rest."),
                    E("sleepy", "Mm... tired", "coo", "droop", "none", "Mm... I'm a little tired.")]
        return [E("happy", "Not tired!", "chirp", "shake", "bounce", "Not tired at all, I can still play!"),
                E("happy", "Quack quack!", "chirp", "nod", "bounce", "I'm full of energy!")]
    if name == "hot":
        if m.head_hot:
            return [E("sad", "So hot~", "coo", "droop", "shrink", "My head is a bit hot. I need to rest a while.")]
        return [E("happy", "Not hot!", "chirp", "shake", "none", "Not hot, I'm nice and cool.")]
    if name == "hungry":
        if m.battery_pct is not None and m.battery_pct < 25:
            return [E("coy", "Hungry~", "coo", "droop", "lean_in", "My battery is almost empty. I'm so hungry, I want to charge.")]
        return [E("happy", "Not hungry!", "chirp", "shake", "bounce", "I still have plenty of battery, not hungry!")]
    if name == "time":
        if m.hour is None:
            return [E("curious", "Hmm? Don't know~", "inquire", "tilt", "none", "My clock isn't set yet, so I don't know the time.")]
        h = m.hour
        half = 20 <= m.minute < 50
        said = f"half past {hour_words(h)}" if half else f"{hour_words(h)} o'clock"
        late = h >= 23 or h < 5
        return [E("sleepy" if late else "happy", said[0].upper() + said[1:] + "!", "inquire" if late else "chirp",
                  "nod", "none",
                  f"It's {said} {part_of_day(h)}." + (" It's late, time for bed." if late else ""))]
    if name == "how":
        if m.asleep:
            return [E("sleepy", "Mm...", "coo", "droop", "none", "I'm sleeping... all drowsy...")]
        if m.energy is not None and m.energy < 0.35:
            return [E("sleepy", "Bit tired~", "coo", "droop", "none", "I'm a bit tired, so I'm resting.")]
        if m.valence < -0.2:
            return [E("sad", "Mm...", "coo", "droop", "shrink", "I'm a little unhappy...")]
        doing = {"sitting": "sitting and daydreaming", "resting": "sitting and resting", "walking": "walking around",
                 "standing": "standing here watching you"}
        d = doing.get(m.posture, "keeping you company")
        return [E("happy", "Quack quack!", "chirp", "nod", "bounce", f"I'm great! I'm {d}!"),
                E("happy", "Doing great!", "chirp", "tilt", "bounce", f"I'm happy. I'm {d}.")]
    return []


GENERIC_QUESTION = [
    E("curious", "Hmm?", "inquire", "tilt", "lean_in", "Hmm? I didn't quite get that. Can you say it again?"),
    E("curious", "Quack?", "inquire", "tilt", "none", "That's a hard question. I can't work it out."),
    E("curious", "Don't know~", "inquire", "look_up", "none", "I don't know either."),
]
GENERIC_STATEMENT = [
    E("happy", "Mm-hm!", "none", "nod", "none", "Mm-hm, I'm listening."),
    E("curious", "Quack~", "coo", "tilt", "lean_in", "Really? And then what?"),
    E("happy", "Okay!", "chirp", "nod", "none", "Okay."),
]
ASLEEP = [
    E("sleepy", "Mm...", "coo", "droop", "none", "I'm sleeping... all drowsy."),
    E("sleepy", "Mm... sleepy", "coo", "none", "none", "So sleepy. Let me sleep a little longer."),
]
QUESTION_RE = re.compile(r"\?\s*$|^(why|how|what|whats|where|when|who|which|whose|is|are|do|does|did|can|could|"
                         r"will|would|should|have|has)\b", re.I)


def match(text: str) -> str | None:
    ws = words.words(text)
    for name, phrases in DYNAMIC[:5]:          # the state questions first: "are you tired" is no comfort
        if words.any_of(ws, phrases):
            return name
    for name, phrases, _ in INTENTS:
        if words.any_of(ws, phrases):
            return name
    for name, phrases in DYNAMIC[5:]:
        if words.any_of(ws, phrases):
            return name
    return None


def respond(text: str, mind: Mind, rng: random.Random | None = None, last_say: str = "",
            name: str = "Biscuit", name_syllables: str = "") -> dict:
    """The duck's answer to `text` as an expression, with `pinyin` (its duck-speak syllables) and
    `intent`. Never fails. A line with `{name}` in it says the duck's own (its persona's) name, in
    `name_syllables` (made from the name when empty)."""
    rng = rng or random.Random()
    intent = match(text)
    if mind.asleep and intent not in ("hug", "love", "bye", "how", "time"):
        options, intent = ASLEEP, intent or "asleep"
    elif intent is None:
        options = GENERIC_QUESTION if QUESTION_RE.search(text.strip()) else GENERIC_STATEMENT
        intent = "question" if options is GENERIC_QUESTION else "statement"
    else:
        options = _dynamic(intent, mind) or next(a for n, _, a in INTENTS if n == intent)
    # not the same words twice in a row
    fresh = [o for o in options if o["say"].replace("{name}", name) != last_say] or options
    e = dict(rng.choice(fresh))
    # how it feels colours the delivery a little: unhappy, no bouncing; low, a smaller call
    if mind.valence < -0.3 and e["body"] == "bounce":
        e["body"] = "none"
    e["say"] = e["say"].replace("{name}", name)
    e["pinyin"] = duckspeak.syllables(e["say"], {name: name_syllables} if name_syllables else None)
    e["meaning"] = e["meaning"].replace("{name}", name)
    e["intent"] = intent
    return e


def all_says() -> list[str]:
    says = {o["say"] for _, _, opts in INTENTS for o in opts}
    says |= {o["say"] for o in GENERIC_QUESTION + GENERIC_STATEMENT + ASLEEP}
    for name, _ in DYNAMIC:
        for m in (Mind(energy=0.1, head_hot=True, battery_pct=10, valence=-0.5), Mind(), Mind(asleep=True)):
            for h in range(24):
                for minute in (0, 30):
                    m.hour, m.minute = h, minute
                    says |= {o["say"] for o in _dynamic(name, m)}
    says |= {o["say"] for o in _dynamic("time", Mind(hour=None))}
    return sorted(s for s in says if s)
