# -*- coding: utf-8 -*-
"""python -m pytest tools/persona/test_duckspeak.py — English text as robotd's duck-speak syllables."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duckspeak import number_words, parses, syllables  # noqa: E402

# robotd's laughing syllables (sounds/src/speak.rs LAUGHS)
LAUGHS = ("ha", "he", "hei", "hi", "xi", "ga", "gua")


def bodies(spec):
    return [re.sub(r"\d$", "", w) for w in spec.split() if w[0].isalpha()]


def tones(spec):
    return [int(w[-1]) for w in spec.split() if w[0].isalpha()]


class SyllablesTest(unittest.TestCase):
    def test_one_syllable_per_english_syllable(self):
        for text, n in (("duck", 1), ("hello", 2), ("happy", 2), ("banana", 3), ("time", 1), ("little", 2),
                        ("jumped", 1), ("wanted", 2), ("makes", 1), ("boxes", 2), ("today", 2), ("I", 1)):
            self.assertEqual(len(bodies(syllables(text))), n, text)

    def test_the_vowels_and_the_hard_starts(self):
        self.assertEqual(bodies(syllables("time")), ["tai"])
        self.assertEqual(bodies(syllables("make")), ["mei"])
        self.assertEqual(bodies(syllables("cat")), ["ka"])
        self.assertEqual(bodies(syllables("city")), ["si", "ti"])
        self.assertEqual(bodies(syllables("you")), ["wu"], "not yu: robotd reads that as the French u")

    def test_stress_and_melody(self):
        self.assertEqual(syllables("Hello, friend!"), "he1 lo5 , fe4 !")
        self.assertEqual(tones(syllables("Are you okay?")), [5, 5, 2, 5], "a question rises")
        self.assertEqual(tones(syllables("today")), [5, 4], "to-DAY")
        self.assertEqual(syllables("Hmm?"), "m2 ?")

    def test_punctuation_is_pauses_one_per_run(self):
        self.assertEqual(syllables("Okay~"), "o1 kei5 ~")
        self.assertEqual(syllables("Really?!"), "ri2 li5 ?")
        self.assertEqual(syllables("Wait... what"), "wei4 . wa4")
        self.assertEqual(syllables("Yes — no"), "ye1 , no4")
        self.assertFalse(syllables("...!").strip(), "nothing to say")

    def test_laughs_are_runs_of_one_syllable(self):
        for text in ("Hahaha!", "ha ha ha", "Quack quack quack!", "hehehe"):
            b = bodies(syllables(text))
            self.assertGreaterEqual(len(b), 3, text)
            self.assertTrue(len(set(b)) == 1 and b[0] in LAUGHS, (text, b))
        self.assertEqual(bodies(syllables("Quack quack!")), ["gua", "gua"], "two is not a laugh")

    def test_numbers_are_said(self):
        self.assertEqual(number_words("1.5"), "one point five")
        self.assertEqual(number_words("2026"), "two thousand twenty six")
        self.assertEqual(len(bodies(syllables("7"))), 2)

    def test_the_duck_says_its_name_as_given(self):
        self.assertEqual(syllables("Hi, Biscuit!", {"Biscuit": "bis1 kit5"}), "hai1 , bis1 kit5 !")
        self.assertEqual(syllables("I'm Mister Quack.", {"Mister Quack": "mis1 te5 gua4"}), "ai5 mis1 te5 gua4 .")

    def test_whatever_it_is_given_robotd_can_parse_it(self):
        for text in ("Connected!", "Can't find it~", "Not Wi-Fi~", "It's 11:30 pm, isn't it?", "Caf\u00e9 au lait",
                     "\uff1f\uff01", "Hello \u2026 world", "(quietly) mm-hm", "e-mail me @ 9", "rhythm psst nth",
                     "Ni\u00f1o 100%", "\u00fcber", "\U0001f986 quack", "'quoted' \"words\"", "x" * 50):
            s = syllables(text)
            self.assertTrue(parses(s), (text, s))
            self.assertTrue(s.isascii(), (text, s))


class ParsesTest(unittest.TestCase):
    """The mirror of robotd's parser (sounds::speak::parse): its own test lines, and what it refuses."""

    def test_what_robotd_takes(self):
        self.assertTrue(parses("kai1 xin1 ya5 \uff01zhu3 ren2\uff0cni3 hao3 ma\uff1f"))
        self.assertTrue(parses("ha1 ha1 ha1 ! hao3 ya5"))
        self.assertTrue(parses("he1 lo4 ,"))
        self.assertTrue(parses(""))

    def test_what_it_refuses(self):
        self.assertFalse(parses("ni3 h@o"))
        self.assertFalse(parses("he1lo4"), "one tone digit, at the end")
        self.assertFalse(parses("don't"))
        self.assertFalse(parses("hi6"))


if __name__ == "__main__":
    unittest.main()
