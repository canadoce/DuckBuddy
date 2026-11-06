# -*- coding: utf-8 -*-
"""Jev judgments for the duck: typed facts at the duck's decision points
(docs/project/duck-life-jev-framework-20261017-CN.md §3).

Jev (TypeSafe's System One) answers atomic questions about a state with probabilities, no free
text. Following the official rules and what AI4Robot learned the hard way: ask facts, never the
next action (lifed's code decides); every choice has an `unclear` way out; each option says what it
is and what it is not; only the context the questions need.

    judge(kind, state, images) -> {"kind", "model", "llm_s", "answers": {name: {...}}}

`kind` is one of JUDGMENTS. Images (base64 JPEG) go in as assets, referenced from the state, with
the danger-zone header the API wants for them; Box questions need jev-1.14.0 or later. The key is
TYPESAFE_API_KEY in the environment (duckbrain's service reads ~/.config/duckbrain/typesafe.env).
Every call is logged (text, answers, timing; images only as size and hash) for offline calibration.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time

LOG = os.environ.get("DUCKBRAIN_JUDGE_LOG", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                         "judge-log.jsonl"))
TEXT_MODEL = os.environ.get("DUCKBRAIN_JEV_MODEL", "jev-latest")
IMAGE_MODEL = os.environ.get("DUCKBRAIN_JEV_IMAGE_MODEL", "jev-1.14.0")   # Box needs 1.14+
TIMEOUT_S = float(os.environ.get("DUCKBRAIN_JEV_TIMEOUT", "3.0"))
IMAGE_HEADER = {"TypeSafe-Danger-Zone-Images": "true"}

# what the duck is, and its name, from its persona (tools/persona); the questions are the framework
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "persona"))
from persona import load as load_persona  # noqa: E402

P = load_persona()
NAME = P.name
DUCK = P.description
CAMERA = (f"`view` is one frame from the camera on {NAME}'s head. The centre of the picture is straight ahead of"
          " it, the horizontal field of view is about 62 degrees, and the camera is about 20 cm above the floor,"
          " so people often show only as legs, or are seen from below.")


class JudgeError(Exception):
    """Why a judgment could not be made: no_api_key, sdk_missing, unknown_kind, bad_image, api, timeout."""


def _opt(what: str, not_for: str = "", examples: list[str] | None = None) -> dict:
    o = {"what": what}
    if not_for:
        o["not_for"] = not_for
    if examples:
        o["examples"] = examples
    return o


# ── J1 utterance (text) ────────────────────────────────────────────────────────────────────────

def _utterance(state: dict) -> tuple[dict, dict]:
    s = {
        "duck": DUCK,
        "text": state.get("text", ""),
        "named": bool(state.get("named")),
        "in_conversation": bool(state.get("in_conversation")),
        "duck_last_said": state.get("duck_last_said") or "",
        "duck_is": state.get("duck_is") or "",
        "note": f"`text` comes from speech recognition and may have misheard words; `named` means the"
                f" sentence called it by its name, {NAME}.",
    }
    q = {
        "for_duck": {
            "type": "noul",
            "instructions": f"Is `text` said to {NAME}?",
            "criteria": {
                "true": "calls it, asks it something, asks it to do something, answers what it just said"
                        " (`duck_last_said`), praises it or tells it off",
                "false": "said to someone else, talking to oneself, sound from a TV or a video, or a recognition"
                         " result that is cut off, makes no sense or is not a sentence",
            },
        },
        "intent": {
            "type": "choice",
            "instructions": f"What does `text` want {NAME} to do?",
            "criteria": {
                "sleep": _opt("go to sleep", "only asks whether it is sleepy",
                              ["go to sleep", "time for bed", "good night", f"go to sleep, {NAME}"]),
                "rest": _opt("rest, take a break, lie still", "asks whether it is tired",
                             ["take a rest", "go and have a rest", "take a break"]),
                "sit": _opt("sit down", "", ["sit down", "sit", "take a seat"]),
                "stand": _opt("stand up from sitting", "wake up (use wake while it is asleep)",
                              ["stand up", "get up and stand"]),
                "wake": _opt("wake up while it is asleep or resting", "asks whether it is awake",
                             ["wake up", "time to get up", "come on, get up"]),
                "net": _opt("connect to a network, scan a QR code", "asks whether it can go online",
                            ["connect to wifi", "scan this code", "join this hotspot"]),
                "bye": _opt("say goodbye, end the chat, the owner is leaving", "",
                            ["bye", "I'm off to work", "that's all for now", "see you later"]),
                "chat": _opt("chat, ask a question, praise it, tell it off, tell it about something",
                             "ask it to do one of the moves above",
                             ["what are you doing", "you're so cute", "I'm so tired today"]),
                "unclear": _opt("cannot tell what is said, or the recognition result is garbled", "",
                                ["apply then", "the the of", "hmm"]),
            },
        },
        "reply": {
            "type": "choice",
            "instructions": f"How does {NAME} need to respond to `text`?",
            "criteria": {
                "none": _opt("no answer needed", "", ["hmm", "oh", "okay", "talking to oneself"]),
                "simple": _opt("a fixed line will do: a hello, praise, a simple greeting, thanks, sorry",
                               "a question or chat that needs some thought",
                               ["hello there", "good boy", "thank you", "good morning"]),
                "think": _opt("needs some thought: a question, a chat, a story, asking how it feels", "",
                              ["what did you do today", "do you like rain", "I'm so tired today"]),
            },
        },
    }
    return s, q


# ── J2 person (image) ──────────────────────────────────────────────────────────────────────────

def _person(state: dict) -> tuple[dict, dict]:
    s = {"duck": DUCK, "camera": CAMERA, "view": state["view"], "tof_distance_m": state.get("tof_distance_m")}
    q = {
        "person": {
            "type": "noul",
            "instructions": "Is there a real person in `view`?",
            "criteria": {"true": "a real person, even if only the legs, a hand or half a face show",
                         "false": "nobody; or only a person in a photo, a poster, a doll or on a TV screen"},
        },
        "activity": {
            "type": "choice",
            "instructions": f"What is the person in `view` nearest to {NAME} doing?",
            "criteria": {
                "looking_at_duck": _opt(f"looking at {NAME}, or walking toward it",
                                        "has their back to it, or is looking somewhere else"),
                "waving": _opt("waving at it, or beckoning it"),
                "thumbs_up": _opt("giving it a thumbs up"),
                "reaching": _opt("reaching out to touch it or pick it up"),
                "passing": _opt("walking past, not looking at it"),
                "busy": _opt("doing something else (looking at a phone, working), not paying attention to it"),
                "unclear": _opt("cannot tell, or there is nobody in the picture"),
            },
        },
        "facing": {
            "type": "noul",
            "instructions": f"Is the face or body of the person nearest to {NAME} turned toward the camera?",
        },
        "face": {
            "type": "box",
            "instructions": "the face of the person in `view` nearest to the camera; if no face shows, the whole person",
        },
    }
    return s, q


# ── J3 floor, J4 presence (image) ──────────────────────────────────────────────────────────────

def _floor(state: dict) -> tuple[dict, dict]:
    s = {"duck": DUCK, "camera": CAMERA, "view": state["view"], "tof_ahead_m": state.get("tof_ahead_m")}
    q = {
        "floor": {
            "type": "choice",
            "instructions": f"What floor is under {NAME} and straight ahead of it?",
            "criteria": {
                "carpet": _opt("carpet, a soft rug or mat"),
                "smooth_hard": _opt("tiles, marble, polished concrete or another smooth hard floor"),
                "wood": _opt("a wooden floor"),
                "mat_edge": _opt("the edge of a mat or a rug: the floor ahead changes"),
                "outdoor": _opt("ground outdoors: a road, grass, paving"),
                "unclear": _opt("cannot see the floor clearly"),
            },
        },
        "path_clear": {
            "type": "noul",
            "instructions": f"Can {NAME} walk over the floor about 1 meter straight ahead of it?",
            "criteria": {"true": "flat, nothing in the way",
                         "false": "something in the way, a step, the edge of a table or sofa, a cable, uneven ground"},
        },
    }
    return s, q


def _presence(state: dict) -> tuple[dict, dict]:
    s = {"camera": CAMERA, "view": state["view"]}
    q = {"anyone": {"type": "noul", "instructions": "Is there anyone in `view`?",
                    "criteria": {"true": "a real person, even if only part of them shows",
                                 "false": "nobody, or only people in photos or on a TV"}}}
    return s, q


JUDGMENTS = {"utterance": (_utterance, False), "person": (_person, True),
             "floor": (_floor, True), "presence": (_presence, True)}


# ── Request assembly ───────────────────────────────────────────────────────────────────────────

def build(kind: str, state: dict, images: dict[str, str] | None = None):
    """The request for a judgment: (state, questions, assets, headers, model). Each image (base64
    JPEG) becomes an asset referenced from the state by a unique token in place of its name."""
    if kind not in JUDGMENTS:
        raise JudgeError("unknown_kind")
    make, needs_images = JUDGMENTS[kind]
    images = images or {}
    assets, state = {}, dict(state)
    if needs_images:
        if "view" not in images:
            raise JudgeError("bad_image")
        for name, b64 in images.items():
            try:
                raw = base64.b64decode(b64, validate=True)
            except ValueError as e:
                raise JudgeError("bad_image") from e
            if raw[:2] != b"\xff\xd8":
                raise JudgeError("bad_image")
            ref = f"img-{name}-{hashlib.sha1(raw).hexdigest()[:10]}"
            assets[ref] = {"type": "image", "format": "jpg", "data_base64": b64}
            state[name] = ref
    s, q = make(state)
    headers = IMAGE_HEADER if assets else {}
    model = IMAGE_MODEL if assets else TEXT_MODEL
    return s, q, assets, headers, model


_client = None


def _get_client():
    global _client
    if not os.environ.get("TYPESAFE_API_KEY"):
        raise JudgeError("no_api_key")
    if _client is None:
        try:
            from typesafe_sdk import TypeSafeClient
        except ImportError as e:
            raise JudgeError("sdk_missing") from e
        _client = TypeSafeClient()
    return _client


def _plain(answer) -> dict:
    if hasattr(answer, "model_dump"):
        answer = answer.model_dump(mode="json")
    return {k: v for k, v in dict(answer).items() if k != "legend"}


def _log(entry: dict):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def judge(kind: str, state: dict, images: dict[str, str] | None = None) -> dict:
    """Ask Jev; JudgeError if it cannot be asked or does not answer."""
    s, q, assets, headers, model = build(kind, state, images)
    client = _get_client()
    t0 = time.time()
    try:
        r = client.system_one(s, q, model=model, timeout=TIMEOUT_S, extra_headers=headers or None,
                              extra_body={"assets": assets} if assets else None)
    except Exception as e:  # noqa: BLE001 - the SDK's errors, a timeout, the network
        name = type(e).__name__
        _log({"t": t0, "kind": kind, "error": name, "detail": str(e)[:200]})
        raise JudgeError("timeout" if "Timeout" in name or "Connection" in name else "api") from e
    out = {"kind": kind, "model": getattr(r, "model", model), "llm_s": round(time.time() - t0, 3),
           "answers": {name: _plain(a) for name, a in (getattr(r, "answers", {}) or {}).items()}}
    _log({"t": t0, "kind": kind, "state": {k: v for k, v in s.items() if k not in ("duck", "camera", "note")},
          "images": {n: {"bytes": len(a["data_base64"]) * 3 // 4} for n, a in assets.items()},
          "answers": out["answers"], "llm_s": out["llm_s"], "model": out["model"]})
    return out


# ── duckjev: this module as its own small service ──────────────────────────────────────────────
# typesafe-sdk needs pydantic >= 2.12 and the brain's venv has 2.7 (FastAPI, CosyVoice), so Jev runs
# in its own venv (/data/microduck/tts/jev-venv) as `duckjev` on 127.0.0.1:8211, and duckbrain's
# /judge forwards to it. Standard library only, besides the SDK.

def serve(port: int = 8211):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                try:
                    import typesafe_sdk  # noqa: F401
                    sdk = True
                except ImportError:
                    sdk = False
                self._send({"ok": True, "key": bool(os.environ.get("TYPESAFE_API_KEY")), "sdk": sdk})
            else:
                self._send({"ok": False, "error": "not here"}, 404)

        def do_POST(self):
            if self.path != "/judge":
                return self._send({"ok": False, "error": "not here"}, 404)
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                out = judge(req.get("kind", ""), req.get("state") or {}, req.get("images") or None)
                self._send({"ok": True, **out})
            except JudgeError as e:
                self._send({"ok": False, "error": str(e)})
            except ValueError:
                self._send({"ok": False, "error": "bad_request"}, 400)

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(time.strftime("%Y-%m-%d %H:%M:%S"), f"duckjev on 127.0.0.1:{port}, key {'set' if os.environ.get('TYPESAFE_API_KEY') else 'missing'}",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    import sys
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8211)
