# -*- coding: utf-8 -*-
"""Who is speaking, with stand-in voice prints (no model): python -m unittest tools/voiced/test_voices.py"""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voices  # noqa: E402

SR = voices.SR


def speech(seconds, voice):
    """`seconds` of 'speech' whose first sample says which stand-in voice it is."""
    x = np.zeros(int(seconds * SR), dtype=np.float32)
    x[0] = voice
    return x


# stand-in voice prints: voice 1 and 2 are far apart; 1.1 is voice 1 on another day
PRINTS = {1.0: [1.0, 0.0, 0.0], 2.0: [0.0, 1.0, 0.0], 1.1: [0.9, 0.1, 0.3]}


class VoicesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.store = os.path.join(self.dir, "voices.json")
        self.v = self.voices()

    def voices(self):
        return voices.Voices(store=self.store, embed=lambda s: voices.unit(PRINTS[round(float(s[0]), 1)]))

    def test_introductions(self):
        for text, name in (("my name is rafael", "Rafael"), ("Phoebe, my name is Ana.", "Ana"),
                           ("Hi! Call me Jo", "Jo"), ("My name's Sam", "Sam"), ("my name is not important", None),
                           ("I am tired", None), ("what is my name", None)):
            self.assertEqual(voices.introduced(text), name, text)

    def test_meeting_then_knowing(self):
        self.assertEqual(self.v.hear(speech(2, 1.0), "Phoebe, my name is Rafael"),
                         {"speaker": "Rafael", "score": 1.0, "met": "Rafael"})
        r = self.v.hear(speech(2, 1.1), "what time is it")
        self.assertEqual(r["speaker"], "Rafael")
        self.assertGreater(r["score"], voices.THRESHOLD)
        self.assertIsNone(self.v.hear(speech(2, 2.0), "hello there")["speaker"])     # someone else

    def test_two_people(self):
        self.v.hear(speech(2, 1.0), "my name is Rafael")
        self.v.hear(speech(2, 2.0), "call me Ana")
        self.assertEqual(self.v.hear(speech(2, 2.0), "sit down")["speaker"], "Ana")
        self.assertEqual(self.v.hear(speech(2, 1.1), "sit down")["speaker"], "Rafael")

    def test_too_short_to_tell(self):
        self.v.hear(speech(2, 1.0), "my name is Rafael")
        self.assertEqual(self.v.hear(speech(0.5, 1.0), "stop"), {"speaker": None, "score": None, "met": None})

    def test_a_good_match_teaches_the_voice(self):
        self.v.hear(speech(2, 1.0), "my name is Rafael")
        self.v.hear(speech(2, 1.0), "tell me a story")
        self.assertEqual(len(self.v.people["Rafael"]), 2)
        self.v.hear(speech(1.0, 1.0), "sit")                    # too short to learn from
        self.assertEqual(len(self.v.people["Rafael"]), 2)

    def test_prints_are_kept_and_capped(self):
        for _ in range(voices.MAX_PRINTS + 5):
            self.v.hear(speech(2, 1.0), "my name is Rafael")
        self.assertEqual(len(self.voices().people["Rafael"]), voices.MAX_PRINTS)

    def test_a_change_from_the_command_line_is_seen(self):
        self.v.hear(speech(2, 1.0), "my name is Rafael")
        other = self.voices()
        other.forget("Rafael")
        os.utime(self.store, ns=(1, 1))          # a different mtime, even within the clock's resolution
        self.assertIsNone(self.v.hear(speech(2, 1.0), "hello")["speaker"])


if __name__ == "__main__":
    unittest.main()
