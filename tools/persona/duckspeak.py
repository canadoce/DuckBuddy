# -*- coding: utf-8 -*-
"""English text as duck-speak syllables, the input of robotd's `robot.speak`.

The duck does not say words. robotd (sounds/src/speak.rs) makes one quack per syllable, and takes
the sentence as ASCII syllables with a tone digit, pinyin style: `he5 lo4 !`. This module writes
English text in that form, the same way for every service that makes the duck talk: the brain
(tools/duckbrain), the small brain and the life layer (tools/lifed).

What is kept of the English:

- one syllable per English syllable, counted from the spelling (vowel groups, a silent final e);
- the vowel of each syllable, as letters robotd reads (a, e, i, o, u and the pairs ai, ei, ao,
  ou, oi), so the beak and the voice colour follow it;
- the first consonant, so b p d t g k start hard (the "k" of a quack);
- the stress: the stressed syllable of a content word gets tone 1 (high and level); the other
  syllables, and small words such as "the" or "to", get the neutral tone 5 (short);
- the sentence melody: the last stressed syllable before a full stop or an exclamation mark, or at
  the end, falls (tone 4); before a question mark it rises (tone 2);
- the punctuation, as pauses: `,` `;` `:` `~` and dashes are a short breath, `.` `!` `?` a longer one.

Laughing words ("haha", "hehe") come out as runs of one syllable, and robotd laughs on three or
more of them in a row; "quack" is `gua`, so "quack quack quack" is a laugh too.

Pure, standard library only: it runs on the robot and on the brain's box. `parses(spec)` checks a
result against what robotd's parser accepts (`sounds::speak::parse`).
"""
from __future__ import annotations

import re
import unicodedata

# Small words said without stress (neutral tone): articles, pronouns, helpers, prepositions.
FUNCTION = {
    "a", "an", "the", "to", "of", "and", "or", "but", "in", "on", "at", "for", "with", "from", "by",
    "is", "am", "are", "was", "were", "be", "been", "it", "its", "me", "my", "your", "you", "we",
    "us", "our", "he", "him", "his", "she", "her", "they", "them", "their", "this", "that", "as",
    "if", "so", "do", "does", "did", "can", "will", "would", "could", "should", "has", "have", "had",
    "im", "youre", "its", "lets", "dont", "just", "than", "then", "there",
}

# Words whose spelling would mislead the rules below, written as robotd syllables (no tone yet).
SPECIAL = {
    "quack": ["gua"], "quacks": ["gua"], "quacky": ["gua", "ki"],
    "hmm": ["m"], "hm": ["m"], "mm": ["m"], "mmm": ["m"], "mhm": ["m", "m"], "shh": ["m"],
    "uh": ["e"], "um": ["e"], "umm": ["e"], "er": ["e"], "erm": ["e"], "huh": ["he"],
    "oh": ["o"], "ooh": ["u"], "ah": ["a"], "aah": ["a"], "aw": ["ao"], "aww": ["ao"],
    "wow": ["wao"], "yay": ["yei"], "yeah": ["ye"], "ok": ["o", "kei"], "okay": ["o", "kei"],
    "hey": ["hei"], "hi": ["hai"], "bye": ["bai"], "i": ["ai"], "im": ["ai"], "ill": ["ai"], "ive": ["ai"],
    "id": ["ai"], "a": ["e"], "the": ["de"], "friend": ["fe"], "friends": ["fe"],
    "you": ["wu"], "your": ["wu"], "youre": ["wu"], "to": ["tu"], "do": ["du"], "who": ["hu"],
    "two": ["tu"], "through": ["su"], "one": ["wa"], "once": ["wa"], "eye": ["ai"], "are": ["a"],
    "were": ["we"], "have": ["ha"], "give": ["gi"], "live": ["li"], "love": ["la"], "come": ["ka"],
    "some": ["sa"], "done": ["da"], "gone": ["go"], "none": ["na"], "move": ["mu"], "could": ["ku"],
    "would": ["wu"], "should": ["shu"], "there": ["sei"], "where": ["wei"], "here": ["hi"],
    "they": ["sei"], "eight": ["ei"], "great": ["gei"], "said": ["se"], "says": ["se"],
    "does": ["da"], "goes": ["gou"], "know": ["nou"], "what": ["wa"], "want": ["wa"],
    "water": ["wa", "te"], "people": ["pi", "pe"], "because": ["bi", "ko"], "every": ["e", "wi"],
}

# Monosyllables where "ow" is the "o" of "go", not the "ow" of "now"
OW_O = {"know", "show", "slow", "low", "grow", "blow", "snow", "throw", "row", "bow", "tow", "mow",
        "flow", "glow", "own", "bowl", "crow"}

# Vowel spellings, as the syllable's vowel letters (robotd reads a / e / i / o / u from them)
PAIRS = {
    "ai": "ei", "ay": "ei", "ei": "ei", "ey": "ei", "ee": "i", "ea": "i", "ie": "i", "oa": "ou",
    "oe": "ou", "oo": "u", "ou": "ao", "ow": "ao", "au": "ao", "aw": "ao", "oi": "oi", "oy": "oi",
    "ue": "u", "ew": "u", "ui": "u", "eu": "u", "uy": "ai", "eau": "ou", "ye": "ai",
}
SHORT = {"a": "a", "e": "e", "i": "i", "o": "o", "u": "e", "y": "i"}
LONG = {"a": "ei", "e": "i", "i": "ai", "o": "ou", "u": "u", "y": "ai"}
CONSONANT = {"j": "zh", "q": "k", "v": "f", "x": "s", "c": "k"}
DIGRAPHS = {"sh": "sh", "ch": "ch", "th": "s", "ph": "f", "wh": "w", "kn": "n", "wr": "r",
            "gh": "g", "ck": "k"}
# syllables that start a word without its stress: a-bout, be-fore, de-cide, re-member, to-day
UNSTRESSED_FIRST = {("", "a"), ("b", "e"), ("d", "e"), ("r", "e"), ("t", "o")}
LAUGH_RE = re.compile(r"(?:(ha)|(he)|(hi)|(hee)|(ho))(?:\1|\2|\3|\4|\5)+h?")
LAUGH_OF = {"ha": "ha", "he": "he", "hi": "hi", "hee": "hi", "ho": "ho"}

NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
                "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

# What robotd takes as a pause (sounds/src/speak.rs `pause_of`), ASCII and full-width
PAUSE_CHARS = set(",;:~.?!") | {"\u3001", "\uff0c", "\uff1b", "\uff1a", "\u2026", "\uff5e", "—",
                                "\u3002", "\uff1f", "\uff01"}
SYLLABLE_RE = re.compile("[a-z\u00fc]+[0-5]?")

TOKEN_RE = re.compile(r"\d+(?:\.\d+)?|[a-z]+(?:'[a-z]+)*|[.!?,;:~]")
MARK_OF = {".": ".", "!": "!", "?": "?", ",": ",", ";": ",", ":": ",", "~": "~"}
STRENGTH = {",": 0, "~": 0, ".": 1, "!": 2, "?": 3}


def number_words(n: str) -> str:
    """'1.5' -> 'one point five', '2026' -> 'two thousand twenty six'."""
    whole, _, frac = n.partition(".")
    out = _int_words(int(whole))
    if frac:
        out += " point " + " ".join(NUMBER_WORDS[int(d)] for d in frac)
    return out


def _int_words(n: int) -> str:
    if n < 20:
        return NUMBER_WORDS[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + NUMBER_WORDS[n % 10])
    if n < 1000:
        return NUMBER_WORDS[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + _int_words(n % 100))
    if n < 1_000_000:
        return _int_words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + _int_words(n % 1000))
    return " ".join(NUMBER_WORDS[int(d)] for d in str(n))


def _is_vowel(w: str, i: int) -> bool:
    c = w[i]
    if c in "aeiou":
        return True
    # y is a vowel inside or at the end of a word ("happy", "my"), a consonant before a vowel ("yes")
    return c == "y" and i > 0 and not (i + 1 < len(w) and w[i + 1] in "aeiou")


def _initial(onset: str, nucleus: str) -> str:
    if not onset:
        return ""
    if onset[:2] in DIGRAPHS:
        return DIGRAPHS[onset[:2]]
    c = onset[0]
    if c == "c" and len(onset) == 1 and nucleus[:1] in ("e", "i", "y"):
        return "s"                       # "city", "dance"
    return CONSONANT.get(c, c)


def _vowel(nucleus: str, coda: str, long: bool, only: bool, last: bool, word: str) -> str:
    if long:
        return LONG[nucleus[0]]
    if nucleus == "y":
        return "ai" if only else "i"     # "my", "happy"
    if nucleus == "ow" and (not only or word in OW_O):
        return "ou"                      # "window", "know"
    if nucleus == "ey" and last and not only:
        return "i"                       # "monkey"
    if nucleus == "ie" and only and last and not coda:
        return "ai"                      # "pie"
    if nucleus in PAIRS:
        return PAIRS[nucleus]
    if len(nucleus) == 1:
        if nucleus in "iu" and coda.startswith("r"):
            return "e"                   # "bird", "fur"
        return SHORT[nucleus]
    for v in "aoeiu":                    # an unusual spelling: its strongest vowel
        if v in nucleus:
            return SHORT[v]
    return "e"


def _syllables(word: str) -> tuple[list[str], int]:
    """A word's syllables (robotd's letters, no tone yet) and which one carries the stress."""
    if word in SPECIAL:
        return SPECIAL[word], 0
    m = LAUGH_RE.fullmatch(word)
    if m:
        unit = next(g for g in m.groups() if g)
        return [LAUGH_OF[unit]] * max(2, len(word) // len(unit)), -1      # -1: every one stressed
    w = word.replace("qu", "kw")
    long_last = False
    n = len(w)
    if n >= 3 and w.endswith("e") and not _is_vowel(w, n - 2) and any(_is_vowel(w, i) for i in range(n - 2)):
        if not (w.endswith("le") and n >= 4 and not _is_vowel(w, n - 3)):          # "little": its own
            long_last = _is_vowel(w, n - 3)                                         # "time", not "dance"
            w = w[:-1]
    elif n >= 4 and w.endswith("ed") and w[-3] not in "td" and not _is_vowel(w, n - 3):
        w = w[:-2] + "d"                                                            # "jumped"
    elif n >= 4 and w.endswith("es") and w[-3] not in "sxzhcg" and not _is_vowel(w, n - 3):
        long_last = n >= 5 and _is_vowel(w, n - 4) and not _is_vowel(w, n - 5)      # "makes"
        w = w[:-2] + "s"
    groups = []
    i = 0
    while i < len(w):
        if _is_vowel(w, i):
            j = i
            while j < len(w) and _is_vowel(w, j):
                j += 1
            groups.append((i, j))
            i = j
        else:
            i += 1
    if not groups:
        return ["m"], 0                  # "psst", "nth": a hum
    onsets, codas = [w[:groups[0][0]]], []
    for (_, end), (start, _) in zip(groups, groups[1:]):
        between = w[end:start]
        if len(between) >= 2 and between[-2:] in DIGRAPHS and between[-2:] != "ck":
            codas.append(between[:-2])
            onsets.append(between[-2:])
        elif len(between) >= 1:
            codas.append(between[:-1])
            onsets.append(between[-1:])
        else:
            codas.append("")
            onsets.append("")
    codas.append(w[groups[-1][1]:])
    out = []
    only = len(groups) == 1
    for k, (a, b) in enumerate(groups):
        nucleus, last = w[a:b], k == len(groups) - 1
        vowel = _vowel(nucleus, codas[k], long_last and last, only, last, word)
        initial = _initial(onsets[k], nucleus)
        if initial == "y" and vowel.startswith("u"):
            initial = "w"                # robotd reads "yu" as the French u
        out.append(initial + vowel)
    stress = 0
    if len(groups) >= 2:
        if word.endswith(("tion", "sion", "cian", "ic")):
            stress = len(groups) - 2
        elif (onsets[0], w[groups[0][0]:groups[0][1]]) in UNSTRESSED_FIRST and not codas[0]:
            stress = 1
    return out, stress


def _normalise(text: str) -> str:
    t = text.replace("\u3002", ".").replace("\u3001", ",")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().replace("\u2019", "'").replace("\u2018", "'").replace("`", "'")
    t = t.replace("\u2026", "...").replace("—", ",").replace("\u2013", ",")
    return re.sub(r"(?<=\s)-+(?=\s)|--+", ",", t)


def syllables(text: str, names: dict[str, str] | None = None) -> str:
    """English text as robotd's duck-speak: 'Hello, friend!' -> 'he1 lo5 , fe4 !'. Empty for text
    with nothing to say (an empty `robot.speak` hushes the duck: callers skip it). `names`: words
    said with syllables of their own, as they are ({"Biscuit": "bis1 kit5"}: the duck's name)."""
    items = []        # [body, stressed, content] for a syllable; a str for a pause mark; a tuple
    # for syllables said as given
    fixed = [(n.lower().split(), said.split()) for n, said in (names or {}).items() if n.split() and said.split()]
    tokens = TOKEN_RE.findall(_normalise(text))
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        name = next(((n, said) for n, said in fixed if tokens[i - 1:i - 1 + len(n)] == n), None)
        if name:
            items += [(x,) for x in name[1]]
            i += len(name[0]) - 1
            continue
        if tok in MARK_OF:
            mark = MARK_OF[tok]
            if not items:
                continue
            if isinstance(items[-1], str):
                if STRENGTH[mark] > STRENGTH[items[-1]]:
                    items[-1] = mark
                continue
            items.append(mark)
            continue
        words = number_words(tok).split() if tok[0].isdigit() else [tok.replace("'", "")]
        for word in words:
            syls, stress = _syllables(word)
            content = word not in FUNCTION
            for k, body in enumerate(syls):
                items.append([body, stress < 0 or k == stress, content])
    # the tones: stress, and each phrase's melody on its last stressed syllable
    phrase: list[list] = []
    for item in items + [None]:
        if isinstance(item, (list, tuple)):
            phrase.append(item)
            continue
        own = [s for s in phrase if isinstance(s, list)]
        for s in own:
            s.append(1 if s[1] and s[2] else 5)
        # the melody on the last stressed syllable, unless the phrase ends on a name said as given
        if own and not isinstance(phrase[-1], tuple):
            stressed = [s for s in own if s[1] and s[2]] or own
            end = item or "."
            stressed[-1][3] = 2 if end == "?" else 4 if end in ".!" else 1
        phrase = []
    return " ".join(x if isinstance(x, str) else x[0] if isinstance(x, tuple) else f"{x[0]}{x[3]}" for x in items)


def parses(spec: str) -> bool:
    """Whether robotd's parser (sounds::speak::parse) takes `spec`: words split on spaces; in each,
    pause marks, and between them syllables of lowercase letters (or u-umlaut) with an optional
    tone digit 0-5 at the end."""
    for word in spec.split():
        syllable = ""
        for c in word + " ":
            if c in PAUSE_CHARS or c == " ":
                if syllable and not SYLLABLE_RE.fullmatch(syllable.lower()):
                    return False
                syllable = ""
            else:
                syllable += c
    return True
