# -*- coding: utf-8 -*-
"""python -m pytest tools/persona/test_persona.py — who the duck is, apart from the framework."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import duckspeak  # noqa: E402
import persona  # noqa: E402


class PersonaTest(unittest.TestCase):
    def setUp(self):
        self.env = os.environ.pop("DUCK_PERSONA", None)
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        if self.env is not None:
            os.environ["DUCK_PERSONA"] = self.env

    def write(self, d):
        p = os.path.join(self.dir, "p.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        return p

    def test_the_example_is_a_whole_duck(self):
        p = persona.load(persona.EXAMPLE)
        self.assertEqual(p.source, persona.EXAMPLE)
        for f in ("name", "name_syllables", "description", "character", "chat_character", "say_style",
                  "say_examples", "express_style", "tts_instruct"):
            self.assertTrue(getattr(p, f), f)
        self.assertIsInstance(p.name_aliases, tuple)
        self.assertIn("biscuits", p.name_aliases, "a list of names, not of letters")
        self.assertIn(p.name, p.character)
        self.assertTrue(duckspeak.parses(p.name_syllables), "robotd can say its name")
        self.assertTrue(all(a == a.lower() and a.isascii() for a in p.name_aliases), "English words, any case")

    def test_a_persona_names_only_what_differs(self):
        p = persona.load(self.write({"name": "Waddles", "character": ["You are Waddles, ", "a duck."], "lively": 0.9}))
        self.assertEqual((p.name, p.character, p.lively), ("Waddles", "You are Waddles, a duck.", 0.9))
        self.assertEqual(p.tts_level, persona.load(persona.EXAMPLE).tts_level, "the rest from the example")

    def test_the_old_pinyin_field_is_refused(self):
        with self.assertRaises(ValueError):
            persona.load(self.write({"name_pinyin": "xiao3 bai2"}))

    def test_a_typo_is_refused_not_ignored(self):
        with self.assertRaises(ValueError):
            persona.load(self.write({"nmae": "Waddles"}))

    def test_the_environment_picks_the_file(self):
        os.environ["DUCK_PERSONA"] = self.write({"name": "Waddles"})
        try:
            self.assertEqual(persona.load().name, "Waddles")
        finally:
            del os.environ["DUCK_PERSONA"]

    def test_every_persona_in_the_tree_loads(self):
        here = os.path.dirname(os.path.abspath(__file__))
        for f in os.listdir(here):
            if f.endswith(".json"):
                p = persona.load(os.path.join(here, f))
                self.assertIn(p.name, p.description, f)


if __name__ == "__main__":
    unittest.main()
