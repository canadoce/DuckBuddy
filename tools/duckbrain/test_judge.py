# -*- coding: utf-8 -*-
"""Jev judgment requests, without calling the API: python -m unittest tools/duckbrain/test_judge.py"""
import base64
import json
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge  # noqa: E402

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()


class BuildTest(unittest.TestCase):
    def test_utterance_is_text_only_with_an_unclear_way_out(self):
        s, q, assets, headers, model = judge.build("utterance", {"text": "go and have a rest", "named": False,
                                                                "in_conversation": True})
        self.assertEqual(assets, {})
        self.assertEqual(headers, {})
        self.assertEqual(model, judge.TEXT_MODEL)
        self.assertEqual(s["text"], "go and have a rest")
        self.assertEqual({k: v["type"] for k, v in q.items()}, {"for_duck": "noul", "intent": "choice", "reply": "choice"})
        self.assertIn("unclear", q["intent"]["criteria"])
        self.assertIn("none", q["reply"]["criteria"])
        self.assertEqual(q["for_duck"]["instructions"], f"Is `text` said to {judge.NAME}?", "English, with its name")
        self.assertTrue(json.dumps(q, ensure_ascii=False).isascii(), "no Chinese left in the questions")

    def test_images_become_referenced_assets_with_the_header(self):
        s, q, assets, headers, model = judge.build("person", {"tof_distance_m": 0.5}, {"view": JPEG})
        (ref, asset), = assets.items()
        self.assertEqual(s["view"], ref, "the state points at the asset")
        self.assertEqual(asset, {"type": "image", "format": "jpg", "data_base64": JPEG})
        self.assertEqual(headers, judge.IMAGE_HEADER)
        self.assertEqual(model, judge.IMAGE_MODEL)
        self.assertEqual(q["face"]["type"], "box")
        self.assertIn("`view`", q["person"]["instructions"])

    def test_bad_requests_are_refused_before_any_call(self):
        with self.assertRaises(judge.JudgeError):
            judge.build("person", {}, {})                       # no image
        with self.assertRaises(judge.JudgeError):
            judge.build("person", {}, {"view": base64.b64encode(b"GIF89a").decode()})
        with self.assertRaises(judge.JudgeError):
            judge.build("horoscope", {})

    def test_no_key_no_call(self):
        old = os.environ.pop("TYPESAFE_API_KEY", None)
        try:
            with self.assertRaises(judge.JudgeError) as e:
                judge.judge("utterance", {"text": "hello"})
            self.assertEqual(str(e.exception), "no_api_key")
        finally:
            if old is not None:
                os.environ["TYPESAFE_API_KEY"] = old

    def test_answers_come_back_plain(self):
        class Fake:
            def system_one(self, s, q, **kw):
                self.kw = kw
                return types.SimpleNamespace(model="jev-test", answers={
                    "for_duck": {"type": "noul", "noul": 0.9},
                    "intent": {"type": "choice", "choice": "rest", "confidence": 0.8, "probabilities": {"rest": 0.9}}})
        fake = Fake()
        old_client, old_log = judge._client, judge.LOG
        os.environ["TYPESAFE_API_KEY"] = "test"
        judge._client, judge.LOG = fake, os.devnull
        try:
            out = judge.judge("utterance", {"text": "go and have a rest", "named": True})
        finally:
            judge._client, judge.LOG = old_client, old_log
            del os.environ["TYPESAFE_API_KEY"]
        self.assertEqual(out["answers"]["intent"]["choice"], "rest")
        self.assertEqual(out["model"], "jev-test")
        self.assertIsNone(fake.kw["extra_body"])

    def test_a_local_server_needs_no_key(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        seen = {}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                seen["path"], seen["auth"] = self.path, self.headers.get("Authorization")
                seen["images"] = self.headers.get("TypeSafe-Danger-Zone-Images")
                seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                body = json.dumps({"model": "glide-test", "answers": {
                    "for_duck": {"type": "noul", "noul": 0.9},
                    "intent": {"type": "choice", "choice": "sit", "confidence": 0.9,
                               "probabilities": {"sit": 0.95}}}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        old = (judge.SYSTEMONE_URL, judge._client, judge.LOG, os.environ.pop("TYPESAFE_API_KEY", None))
        judge.SYSTEMONE_URL, judge._client, judge.LOG = f"http://127.0.0.1:{srv.server_port}", None, os.devnull
        try:
            out = judge.judge("utterance", {"text": "sit down", "named": True})
            self.assertEqual(out["answers"]["intent"]["choice"], "sit")
            self.assertEqual(out["model"], "glide-test")
            self.assertEqual(seen["path"], "/v1/systemone")
            self.assertIsNone(seen["auth"])
            self.assertEqual(set(seen["body"]), {"state", "questions", "model"})
            judge.judge("person", {}, {"view": JPEG})
            self.assertEqual(seen["images"], "true")
            self.assertEqual(seen["body"]["assets"][seen["body"]["state"]["view"]]["format"], "jpg")
            self.assertEqual(seen["body"]["questions"]["face"]["type"], "box")
            judge.BOX = False      # a server without Box questions
            judge.judge("person", {}, {"view": JPEG})
            self.assertNotIn("face", seen["body"]["questions"])
            self.assertIn("person", seen["body"]["questions"])
        finally:
            judge.BOX = True
            srv.shutdown()
            judge.SYSTEMONE_URL, judge._client, judge.LOG = old[:3]
            if old[3] is not None:
                os.environ["TYPESAFE_API_KEY"] = old[3]


if __name__ == "__main__":
    unittest.main()
