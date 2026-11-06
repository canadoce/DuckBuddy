# -*- coding: utf-8 -*-
"""What was heard, as words to match: voiced's English text (any case, punctuation, "Wi-Fi",
"don't") as lowercase words, and whole-word phrase matching on them, so "hi" is found in "hi
there" but not in "this", and "go" not in "good".

A phrase can be negated: "don't sit down" does not ask it to sit. The command words that only ever
stop something ("stop", "cancel") are matched without that check, so they are never missed.

Pure: tested in test_core.py.
"""
from __future__ import annotations

import re

_APOSTROPHE = re.compile("['’‘`]")
_WIFI = re.compile(r"\bwi[\s-]?fi\b")
_QR = re.compile(r"\bq[\s-]r\b")
_NOT_WORD = re.compile(r"[^a-z0-9]+")
# words that turn the next phrase (within two words) into its opposite
NEGATIONS = {"dont", "not", "never", "cant", "cannot", "wont", "shouldnt", "didnt", "doesnt", "mustnt"}


def words(text: str) -> list[str]:
    """'Don't connect to the Wi-Fi!' -> ['dont', 'connect', 'to', 'the', 'wifi']"""
    t = _APOSTROPHE.sub("", text.lower())
    t = _QR.sub("qr", _WIFI.sub("wifi", t))
    return [w for w in _NOT_WORD.split(t) if w]


def has(ws: list[str], phrase: str, negatable: bool = True) -> bool:
    """Whether the words `ws` hold `phrase` as whole words, in order. `negatable`: an occurrence
    right after a negation ("don't", "never", ...) does not count."""
    p = words(phrase)
    if not p:
        return False
    for i in range(len(ws) - len(p) + 1):
        if ws[i:i + len(p)] == p:
            if negatable and any(w in NEGATIONS for w in ws[max(0, i - 2):i]):
                continue
            return True
    return False


def any_of(ws: list[str], phrases, negatable: bool = True) -> bool:
    return any(has(ws, p, negatable) for p in phrases)
