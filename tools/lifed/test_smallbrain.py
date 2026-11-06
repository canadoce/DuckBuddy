# -*- coding: utf-8 -*-
"""The small brain (offline answers): python -m unittest tools/lifed/test_smallbrain.py"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from smallbrain import Mind, all_says, match, respond  # noqa: E402
import duckspeak  # noqa: E402  (tools/persona, put on the path by smallbrain)

CALLS = ("greet", "inquire", "coo", "chirp", "peck", "none")
GESTURES = ("nod", "shake", "tilt", "look_up", "droop", "nuzzle", "none")
BODIES = ("bounce", "lean_in", "shrink", "none")
EMOTIONS = ("happy", "curious", "coy", "shy", "sleepy", "sad", "surprised")


class SmallBrainTest(unittest.TestCase):
    def test_every_line_is_duck_speak_robotd_can_say(self):
        for s in all_says():
            spec = duckspeak.syllables(s.replace("{name}", "Biscuit"))
            self.assertTrue(spec and duckspeak.parses(spec), (s, spec))

    def test_it_says_its_own_name(self):
        for seed in range(6):
            e = respond("Who are you?", Mind(), random.Random(seed), name="Waddles", name_syllables="wa1 dels5")
            self.assertIn("Waddles", e["say"] + e["meaning"])
            self.assertNotIn("{name}", e["say"] + e["meaning"] + e["pinyin"])
            if "Waddles" in e["say"]:
                self.assertIn("wa1 dels5", e["pinyin"])
        e = respond("what is your name", Mind(), random.Random(1), name="Waddles")
        self.assertTrue(duckspeak.parses(e["pinyin"]), "made from the name when the persona gives none")

    def test_intents(self):
        cases = {
            "Are you tired?": "tired", "are you hot": "hot", "Are you hungry?": "hungry", "What time is it?": "time",
            "How are you?": "how", "What's wrong?": "how", "How is the weather today?": "weather",
            "Hello there, Biscuit": "hello", "You're so smart": "praise", "You're so dumb": "scold", "Hug!": "hug",
            "I'm so sad": "comfort", "Sing me a song": "sing", "Who are you?": "who", "Thank you": "thanks",
            "Sorry": "sorry", "I love you": "love", "Play with me": "dance", "What are you doing?": "how",
            "Tell me a joke": "joke", "Hi, how are you?": "how", "Don't move for now": None,
            # whole words only
            "This is interesting": None, "Something good": None, "Which shed?": None,
        }
        for text, want in cases.items():
            self.assertEqual(match(text), want, text)

    def test_answers_are_well_formed(self):
        rng = random.Random(1)
        for text in ("Hello", "What time is it", "Are you tired", "Say something", "What is this?", "You're cute",
                     "Sing"):
            for mind in (Mind(), Mind(asleep=True), Mind(energy=0.1, head_hot=True, battery_pct=8, valence=-0.6),
                         Mind(hour=21, minute=35)):
                e = respond(text, mind, rng)
                self.assertTrue(e["pinyin"] and duckspeak.parses(e["pinyin"]), (text, e))
                self.assertIn(e["emotion"], EMOTIONS)
                self.assertIn(e["pre"], CALLS)
                self.assertIn(e["gesture"], GESTURES)
                self.assertIn(e["body"], BODIES)
                self.assertEqual(e["action"], "none", "the small brain never moves the body")
                self.assertTrue(e["meaning"])

    def test_the_state_colours_the_answer(self):
        rng = random.Random(1)
        self.assertEqual(respond("Are you tired?", Mind(energy=0.1), rng)["emotion"], "sleepy")
        self.assertEqual(respond("Are you tired?", Mind(energy=0.9), rng)["emotion"], "happy")
        self.assertIn("battery", respond("Are you hungry?", Mind(battery_pct=10), rng)["meaning"])
        self.assertEqual(respond("You're so smart", Mind(asleep=True), rng)["emotion"], "sleepy", "asleep, it mumbles")

    def test_questions_and_statements(self):
        rng = random.Random(1)
        self.assertEqual(respond("Why is the sky blue", Mind(), rng)["intent"], "question")
        self.assertEqual(respond("The sky is blue?", Mind(), rng)["intent"], "question")
        self.assertEqual(respond("The sky is blue.", Mind(), rng)["intent"], "statement")

    def test_the_time_only_if_the_clock_is_set(self):
        rng = random.Random(1)
        self.assertIn("don't know", respond("What time is it?", Mind(hour=None), rng)["meaning"])
        e = respond("What time is it?", Mind(hour=21, minute=35), rng)
        self.assertEqual(e["say"], "Half past nine!")
        self.assertIn("half past nine in the evening", e["meaning"])
        self.assertEqual(respond("What time is it?", Mind(hour=13, minute=5), rng)["say"], "One o'clock!")
        self.assertIn("time for bed", respond("What time is it?", Mind(hour=0, minute=5), rng)["meaning"])

    def test_not_the_same_words_twice_running(self):
        rng = random.Random(3)
        last = ""
        for _ in range(20):
            e = respond("Let's chat", Mind(), rng, last_say=last)
            self.assertNotEqual(e["say"], last)
            last = e["say"]


if __name__ == "__main__":
    unittest.main()
