# -*- coding: utf-8 -*-
"""voiced, part 3: who is speaking. Each utterance becomes a voice print (NVIDIA TitaNet-small,
English, sherpa-onnx, about 40 ms on the brain's CPU per phrase) and is compared with the voice prints
of the people the duck has met; the best match above THRESHOLD is the speaker, otherwise nobody it
knows.

A person is met by saying so, to the duck: "Phoebe, my name is Rafael" (or "call me Rafael"). That
utterance is their first voice print; each later utterance that matches them well and is long enough
adds another (up to MAX_PRINTS, the oldest dropped), so the duck learns the voice across rooms and
moods. The voice prints live in ~/.config/duck/voices.json, one list per name; voiced reads the file
again whenever it changes, so the commands below take effect without a restart.

    ~/voiced/.venv/bin/python voices.py list
    ~/voiced/.venv/bin/python voices.py forget NAME
    ~/voiced/.venv/bin/python voices.py add NAME a.wav [b.wav ...]     # 16 kHz mono wavs
    ~/voiced/.venv/bin/python voices.py who a.wav
"""
import argparse
import json
import os
import re
import sys
import tempfile

import numpy as np

MODEL = "nemo_en_titanet_small.onnx"
STORE = os.path.expanduser(os.environ.get("DUCK_VOICES", "~/.config/duck/voices.json"))   # $DUCK_VOICES: another file
# Cosine similarity to a person's mean voice print. Measured with TitaNet-small on clean clips: the
# same person 0.72-0.80, another person at least 0.45 below that. A phrase through the robot's mic,
# with servo and fan noise, scores lower: tune this on the robot (the log shows each score).
THRESHOLD = 0.55
# A later utterance joins its speaker's voice prints when it matches this well and lasts this long.
LEARN_SCORE = 0.70
LEARN_MIN_S = 1.5
MIN_S = 0.8                 # shorter phrases are not identified (a voice print needs some speech)
MAX_PRINTS = 12
SR = 16000

# "my name is Rafael", "call me Rafael": the name is one word; these are never names
INTRO_RE = re.compile(r"\b(?:my name is|my name's|call me)\s+([a-z][a-z'-]{1,20})\b", re.I)
NOT_NAMES = {"not", "no", "the", "a", "an", "just", "now", "here", "back", "later", "please", "what", "your",
             "that", "this", "it", "so", "very", "too", "also", "still", "maybe", "actually", "really"}


def introduced(text: str) -> str | None:
    """The name in "my name is X" / "call me X", title-cased, or None."""
    m = INTRO_RE.search(text)
    if not m or m.group(1).lower() in NOT_NAMES:
        return None
    return m.group(1).strip("'-").capitalize()


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


class Voices:
    """The people the duck knows by voice. `embed` turns 16 kHz samples into a voice print; the
    sherpa-onnx extractor by default, a stand-in in the tests."""

    def __init__(self, models: str | None = None, store: str = STORE, embed=None):
        self.store = store
        self.people: dict[str, list[np.ndarray]] = {}
        self.mtime = None
        if embed is None:
            import sherpa_onnx
            ex = sherpa_onnx.SpeakerEmbeddingExtractor(sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=os.path.join(models, MODEL), num_threads=1))

            def embed(samples):
                st = ex.create_stream()
                st.accept_waveform(SR, samples)
                st.input_finished()
                return unit(ex.compute(st))
        self.embed = embed
        self.load()

    def load(self):
        try:
            self.mtime = os.stat(self.store).st_mtime_ns
            with open(self.store, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.mtime, data = None, {}
        self.people = {name: [unit(p) for p in prints] for name, prints in data.items() if prints}

    def refresh(self):
        """Read the file again if something else (voices.py on the command line) changed it."""
        try:
            m = os.stat(self.store).st_mtime_ns
        except FileNotFoundError:
            m = None
        if m != self.mtime:
            self.load()

    def save(self):
        os.makedirs(os.path.dirname(self.store), exist_ok=True)
        data = {name: [[round(float(x), 5) for x in p] for p in prints] for name, prints in self.people.items()}
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.store), prefix=".voices-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self.store)
        self.mtime = os.stat(self.store).st_mtime_ns

    def match(self, print_) -> tuple[str | None, float]:
        """The best-matching person and the score, or (None, best score) below THRESHOLD."""
        best, score = None, -1.0
        for name, prints in self.people.items():
            s = float(unit(np.mean(prints, axis=0)) @ print_)
            if s > score:
                best, score = name, s
        return (best, score) if score >= THRESHOLD else (None, score)

    def add(self, name: str, print_):
        prints = self.people.setdefault(name, [])
        prints.append(unit(print_))
        del prints[:-MAX_PRINTS]
        self.save()

    def forget(self, name: str) -> bool:
        if self.people.pop(name, None) is None:
            return False
        self.save()
        return True

    def hear(self, samples, text: str) -> dict:
        """One utterance: who said it, and whether it introduced someone (or taught a known voice).
        Returns {"speaker", "score", "met"}: the name or None, the cosine score or None (too short to
        tell), and the name of a person just met or None."""
        self.refresh()
        seconds = len(samples) / SR
        name = introduced(text)
        if seconds < MIN_S:
            return {"speaker": None, "score": None, "met": None}
        p = self.embed(samples)
        if name:
            self.add(name, p)
            return {"speaker": name, "score": 1.0, "met": name}
        who, score = self.match(p)
        if who and score >= LEARN_SCORE and seconds >= LEARN_MIN_S:
            self.add(who, p)
        return {"speaker": who, "score": round(score, 3), "met": None}


def _wav(path):
    import wave
    with wave.open(path) as w:
        if w.getframerate() != SR or w.getnchannels() != 1:
            sys.exit(f"{path}: needs 16 kHz mono, is {w.getframerate()} Hz, {w.getnchannels()} channels")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", default=os.path.expanduser("~/models/hearing"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    f = sub.add_parser("forget")
    f.add_argument("name")
    a = sub.add_parser("add")
    a.add_argument("name")
    a.add_argument("wavs", nargs="+")
    w = sub.add_parser("who")
    w.add_argument("wav")
    args = ap.parse_args()
    if args.cmd in ("list", "forget"):
        v = Voices(embed=lambda s: s)          # no model needed
        if args.cmd == "list":
            for name, prints in sorted(v.people.items()):
                print(f"{name}: {len(prints)} voice prints")
            if not v.people:
                print(f"nobody yet ({v.store})")
        else:
            print("forgotten" if v.forget(args.name) else f"{args.name}: not known")
        return
    v = Voices(args.models)
    if args.cmd == "add":
        for path in args.wavs:
            v.add(args.name.capitalize(), v.embed(_wav(path)))
        print(f"{args.name.capitalize()}: {len(v.people[args.name.capitalize()])} voice prints")
    else:
        who, score = v.match(v.embed(_wav(args.wav)))
        print(f"{who or 'nobody known'} (score {score:.2f}, threshold {THRESHOLD})")


if __name__ == "__main__":
    main()
