# -*- coding: utf-8 -*-
"""The brain's expression, with the language model faked: python -m pytest tools/duckbrain/test_server.py
(needs numpy and soundfile, as the service does)."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402
import duckspeak  # noqa: E402  (tools/persona, put on the path by server)


class ExpressTest(unittest.TestCase):
    def setUp(self):
        self.real = server.complete
        self.sent = []

    def tearDown(self):
        server.complete = self.real
        server._sessions.clear()

    def answer(self, reply):
        def fake(body, timeout=20):
            self.sent.append(body)
            return reply if isinstance(reply, str) else json.dumps(reply)
        server.complete = fake

    def test_an_english_expression_with_its_duck_speak(self):
        self.answer({"emotion": "Happy", "say": "Quack quack! Hello there, my friend, nice day", "pre": "chirp",
                     "gesture": "nod", "body": "bounce", "action": "none", "meaning": "Hello! I'm glad you're here.",
                     "end": False})
        out = server.express("Hello", "standing, calm", "t1")
        self.assertEqual(out["emotion"], "happy")
        self.assertEqual(len(out["say"].split()), server.SAY_WORDS, "cut at a word")
        self.assertEqual(out["pinyin"], duckspeak.syllables(out["say"], {server.P.name: server.P.name_syllables}))
        self.assertTrue(duckspeak.parses(out["pinyin"]))
        prompt = self.sent[0]["messages"][0]["content"]
        self.assertIn("English", prompt)
        self.assertIn("(You right now: standing, calm.)", prompt)
        for e in server.EMOTIONS:
            self.assertIn(e, prompt)

    def test_its_name_is_said_as_the_persona_writes_it(self):
        self.answer({"emotion": "happy", "say": f"{server.P.name}!", "meaning": "That's me!"})
        out = server.express("Who are you?", "", "t2")
        self.assertIn(server.P.name_syllables, out["pinyin"])

    def test_an_unreadable_answer_is_a_confused_tilt(self):
        self.answer("I am a duck")
        out = server.express("Hmm", "", "t3")
        self.assertEqual((out["emotion"], out["gesture"], out["say"]), ("curious", "tilt", "Quack?"))
        self.assertTrue(out["pinyin"])

    def test_an_unknown_emotion_is_happy(self):
        self.answer({"emotion": "\u5f00\u5fc3", "say": "Yay!", "meaning": "Yay!"})
        self.assertEqual(server.express("Hi", "", "t4")["emotion"], "happy")

    def test_the_chat_tag_is_english(self):
        self.answer("[sleepy] I am so sleepy.")
        self.assertEqual(server.llm("Are you tired?", "", "t5"), ("sleepy", "I am so sleepy."))


if __name__ == "__main__":
    unittest.main()
