# -*- coding: utf-8 -*-
"""What voiced makes of a transcript - noise or words, its name or not - without the models:
python -m pytest tools/voiced/test_hearing.py"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.modules.setdefault("sherpa_onnx", types.ModuleType("sherpa_onnx"))   # the models are not needed here
os.environ["DUCK_PERSONA"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                          "persona", "example.json")
import hearing  # noqa: E402


class NoiseTest(unittest.TestCase):
    def test_noise_is_dropped(self):
        for text in ("", ".", "...", "Okay.", "Mm.", "Uh, the.", "Hmm?", "I.", "you", "う", "Yeah, okay."):
            self.assertTrue(hearing.noise_text(text), text)

    def test_short_commands_are_kept(self):
        for text in ("Stop.", "stop", "STOP!", "Go.", "Sit.", "Wait!", "No.", "Yes.", "Bye.", "Sit down.", "Okay, stop.",
                     "Uh, stop!", "Louder.", "Hi!", "Rest", "Cancel."):
            self.assertFalse(hearing.noise_text(text), text)

    def test_a_sentence_is_kept(self):
        self.assertFalse(hearing.noise_text("What are you doing?"))
        self.assertFalse(hearing.noise_text("Walk forward 1.5 meters."))


class NameTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.real = hearing.to_lifed
        hearing.to_lifed = self.sent.append
        self.ears = hearing.Ears(None)

    def tearDown(self):
        hearing.to_lifed = self.real

    def test_the_name_in_any_case_and_its_mishearings(self):
        self.assertEqual(hearing.NAME, "Biscuit")
        for text, rest in (("Biscuit, sit down.", "sit down."), ("hey BISCUIT stop!", "hey stop!"),
                           ("Biscuits, what is this?", "what is this?"), ("Okay, biskit.", "Okay."),
                           ("Bis kit, come here", "come here"), ("Biscuit!", "")):
            self.assertEqual(hearing.named_in(text), (True, rest), text)

    def test_only_whole_words(self):
        for text in ("I had a biscuitry class", "Pass the biscuitbox", "Want a cookie?"):
            self.assertEqual(hearing.named_in(text), (False, text), text)

    def test_a_call_then_what_was_said(self):
        self.ears.heard("Biscuit, stop!")
        self.assertEqual([(e["type"], e.get("text")) for e in self.sent], [("call", "Biscuit, stop!"), ("say", "stop!")])
        self.assertTrue(self.sent[1]["named"])

    def test_the_name_alone_is_only_a_call(self):
        self.ears.heard("Biscuit?")
        self.assertEqual([e["type"] for e in self.sent], ["call"])

    def test_without_the_name_it_is_said_unnamed(self):
        self.ears.heard("This is interesting.")
        self.assertEqual([(e["type"], e["text"], e["named"]) for e in self.sent],
                         [("say", "This is interesting", False)])


class RecognizerTest(unittest.TestCase):
    def test_moonshine_v2_english(self):
        seen = {}

        class Rec:
            @staticmethod
            def from_moonshine_v2(**kw):
                seen.update(kw)
                return "rec"
        hearing.sherpa_onnx.OfflineRecognizer = Rec
        self.assertEqual(hearing.make_recognizer("/models"), "rec")
        self.assertEqual(seen["encoder"], "/models/moonshine/encoder_model.ort")
        self.assertEqual(seen["decoder"], "/models/moonshine/decoder_model_merged.ort")


class SpeakerTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.real = hearing.to_lifed
        hearing.to_lifed = self.sent.append

    def tearDown(self):
        hearing.to_lifed = self.real

    def test_the_speaker_goes_with_what_was_said(self):
        hearing.Ears(None).heard("Biscuit, sit down.", None, {"speaker": "Rafael", "score": 0.81, "met": None})
        self.assertEqual([(e["type"], e["speaker"], e["speaker_score"]) for e in self.sent],
                         [("call", "Rafael", 0.81), ("say", "Rafael", 0.81)])
        self.assertNotIn("met", self.sent[1])

    def test_meeting_someone_is_marked(self):
        hearing.Ears(None).heard("Biscuit, my name is Rafael.", None, {"speaker": "Rafael", "score": 1.0, "met": "Rafael"})
        self.assertEqual(self.sent[-1]["met"], "Rafael")

    def test_without_voice_prints_nobody_is_named(self):
        hearing.Ears(None).heard("What is this?")
        self.assertIsNone(self.sent[0]["speaker"])


if __name__ == "__main__":
    unittest.main()
