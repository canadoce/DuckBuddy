# -*- coding: utf-8 -*-
"""duckbrain: the duck's online brain on the V100 box (P2d, docs/project/duck-life-roadmap-20261014-CN.md).

The robot's words in, the duck's answer out. 2026-10-15: the user heard every synthetic human voice
on the duck as wrong, then a whole answer read out as duck calls as too long — so the answer is an
*expression* (`/express`): the local 27B (vLLM on 127.0.0.1:8203), as the duck of the persona,
decides how a duck would respond — an emotion, a few English words of duck-speak (rendered on the
robot from their syllables, `sounds::speak`; the syllables are made here by
tools/persona/duckspeak.py), a call before them, a head gesture, a small body move, rarely an
action — and writes the full meaning, in English, for the human to read. Listens on 127.0.0.1 only; the robot reaches it
through the frp stcp tunnel (`deploy/frp/duckbrain-stcp-setup.sh`), at home and outdoors alike.

    POST /express {"text", "context"?, "session"?}  -> {"emotion", "say", "pinyin", "pre", "gesture",
                                                        "body", "action", "meaning", "end", "llm_s"}

`context` is what the duck is like right now in a few words (lifed: posture, tired / hot / hungry,
the time when its clock is set, mood); `session` is one conversation (lifed opens one per call of
its name), whose last turns the model sees; `end` is true when the model hears a farewell, and
lifed closes the conversation once the duck has said its bye.

The earlier spoken-voice path (CosyVoice3 + ducktalk, `/talk`) stays, off unless DUCKBRAIN_TTS=1.

    POST /judge {"kind", "state", "images"?}  -> {"ok", "answers", "llm_s", "model"} | {"ok": false, "error"}
         Jev's typed facts for lifed / visiond, forwarded to duckjev (judge.py in its own venv, :8211;
         docs/project/duck-life-jev-framework-20261017-CN.md)
    GET  /health                  {"ok", "tts", "llm", "jev"}
    POST /chat  {"text", "context"?, "session"?}             -> {"emotion", "reply", "llm_s"}
    POST /talk  {"text", "context"?, "session"?, "voice"?}  -> NDJSON lines:
         {"type": "reply", "emotion", "text", "llm_s"}
         {"type": "audio", "i", "text", "sr", "wav": base64 16-bit mono wav, "tts_s"}   per sentence
         {"type": "end", "total_s"}

    CUDA_VISIBLE_DEVICES=<4080S> PYTHONPATH=~/CosyVoice:~/CosyVoice/third_party/Matcha-TTS:<this dir>:<duckvoice> \
        /data/microduck/tts/venv/bin/python server.py
"""
import base64
import io
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "duckvoice"))

LLM_URL = os.environ.get("DUCKBRAIN_LLM", "http://127.0.0.1:8203/v1/chat/completions")
# The model name, if pinned; otherwise whatever the vLLM on LLM_URL serves (2026-10-16: the box
# moved from qwen38-27b-fp8 to qwen38-27b-quasar and every request 404'd on the old name).
LLM_MODEL_PIN = os.environ.get("DUCKBRAIN_LLM_MODEL", "")
TTS_MODEL = os.path.expanduser(os.environ.get("DUCKBRAIN_TTS_MODEL", "~/models/Fun-CosyVoice3-0.5B-2512"))
# the brain's working directory (voice clips, logs): this file's directory's parent by default
TTS_DIR = os.environ.get("DUCKBRAIN_TTS_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PORT = int(os.environ.get("DUCKBRAIN_PORT", "8210"))
JEV_URL = os.environ.get("DUCKBRAIN_JEV_URL", "http://127.0.0.1:8211")      # duckjev (judge.py)
# Who the duck is - name, character, voice - comes from its persona (tools/persona); this file is
# the framework: what the brain is asked for and in what shape.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "persona"))
from persona import load as load_persona  # noqa: E402
import duckspeak  # noqa: E402

P = load_persona()
# the voice: a clone's reference clip and the ducktalk level (the persona's; the environment overrides)
VOICE = {"prompt": os.environ.get("DUCKBRAIN_PROMPT", os.path.join(TTS_DIR, P.tts_voice_prompt)),
         "level": int(os.environ.get("DUCKBRAIN_LEVEL", str(P.tts_level)))}
LIVELY = P.tts_instruct
# robotd's moods (sounds::speak::Mood::named), and lifed's (core.Inner.IMPULSES)
EMOTIONS = ("happy", "curious", "coy", "shy", "sleepy", "sad", "surprised")
PERSONA = (
    P.chat_character
    + " Rules: answer in one or two sentences, at most twenty-five words; no emoji, no lists, no formatting;"
    " write numbers as words. Start the answer with one emotion tag, one of "
    f"{' '.join(f'[{e}]' for e in EMOTIONS)}. If you do not know something, say so honestly; do not make"
    " things up. You cannot see, and you cannot go online."
)
HISTORY_TURNS = 6
TTS_ON = os.environ.get("DUCKBRAIN_TTS", "0") == "1"

# The expression's vocabulary: what the robot can actually do (tools/lifed carries each out).
CALLS = ("greet", "inquire", "coo", "chirp", "peck", "none")
GESTURES = ("nod", "shake", "tilt", "look_up", "droop", "nuzzle", "none")
BODIES = ("bounce", "lean_in", "shrink", "none")
ACTIONS = ("none", "sit", "stand", "rest", "sleep", "wake")
EXPRESS = (
    P.character
    + " You cannot speak human words. You express yourself only the way a duck does: a few words of"
    " duck-speak (said as quacks), calls, nodding, shaking or tilting your head, and small moves of your"
    " body. When your owner talks to you, decide how you respond, and output only one JSON object with"
    " these fields:\n"
    f"emotion: your feeling, exactly one of {', '.join(EMOTIONS)};\n"
    f"say: what you say in duck-speak, {P.say_style}, in English, at most four words, punctuation allowed,"
    f" for example {P.say_examples}; when something is funny or you laugh out loud, write hahaha or quack"
    " quack quack (three or more become a burst of laughter); leave it empty if you do not want to speak;\n"
    f"pre: one call before you speak, exactly one of {', '.join(CALLS)} (greet: a hello, inquire: a question,"
    " coo: soft and content, chirp: a short excited call, peck: a little peck to show you are not pleased,"
    " none: no call);\n"
    f"gesture: a head move, exactly one of {', '.join(GESTURES)} (nod: agree, shake: no, tilt: curious,"
    " look_up: surprised, droop: sad or sleepy, nuzzle: affectionate, none);\n"
    f"body: a body move, exactly one of {', '.join(BODIES)} (bounce: a happy little bounce, lean_in: come"
    " closer to look, shrink: shrink back a little, none);\n"
    f"action: exactly one of {', '.join(ACTIONS)}. Use it only when your owner clearly asks you to do that,"
    " otherwise it is none: sit is sit down, stand is stand up, rest is sit down and rest, sleep is go to"
    " sleep; while you are asleep or resting do not use stand or wake: to wake you, your owner must say"
    " \"wake up\" themselves;\n"
    "meaning: what you mean, written as one complete, natural English sentence in the first person (\"I\"),"
    " the translation your owner reads, at most twenty words;\n"
    "end: true when your owner is leaving, says they are going to be busy, or the talk has clearly come to"
    " an end; false otherwise.\n"
    "How to respond like a living little duck:\n"
    + P.express_style
    + "If you do not know something, say so honestly; do not make things up. You cannot see anything"
    " unless a photo is attached. You cannot go online. If you know the time you may say it; if not,"
    " say you do not know."
)
# With a photo from its head camera (lifed's `look`, 2026-10-17): the answer is about the photo.
SEEING = (
    "\nThis time your owner asked you to look at something, and the photo your eyes (the camera on your"
    " head) see right now is attached. Respond to your owner from the photo: in meaning, say in one or two"
    " sentences what you see and answer the question, up to thirty words. If the photo is not clear, or"
    " you cannot see what was asked about, say honestly that you could not see it well; do not make it up."
)
JSON_RE = re.compile(r"\{.*\}", re.S)
TAG_RE = re.compile(r"^\s*\[([^\]]{1,12})\]\s*")
SENT_RE = re.compile(r"(?<=[.!?\u2026~])\s+")
SAY_WORDS = 6             # duck-speak is short: what is longer is cut at a word

log = logging.getLogger("duckbrain")
_sessions: dict[str, list[dict]] = {}
_tts = None
_tts_lock = threading.Lock()
_model = None


def served_model(refresh=False):
    """The model to ask: the pinned one, else the first the server lists (looked up once, and again
    after a failed request, so a model swap on the box needs no restart here)."""
    global _model
    if LLM_MODEL_PIN:
        return LLM_MODEL_PIN
    if _model is None or refresh:
        with urllib.request.urlopen(LLM_URL.replace("/chat/completions", "/models"), timeout=5) as r:
            _model = json.loads(r.read())["data"][0]["id"]
        log.info("llm model: %s", _model)
    return _model


def complete(body, timeout=20):
    """POST a chat completion for `body` (without "model"); one retry with the model looked up
    again if the server refuses the name."""
    for attempt in (0, 1):
        req = urllib.request.Request(LLM_URL, data=json.dumps({"model": served_model(attempt == 1), **body}).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if attempt or e.code not in (400, 404):
                raise
            log.warning("llm refused model %r (%s); looking it up again", _model, e.code)


def load_tts():
    global _tts
    from cosyvoice.cli.cosyvoice import AutoModel
    t = time.time()
    _tts = AutoModel(model_dir=TTS_MODEL)
    logging.getLogger().setLevel(logging.INFO)
    list(_tts.inference_instruct2("Hello there.", LIVELY, VOICE["prompt"], stream=False))   # warm-up
    log.info("tts ready in %.1f s", time.time() - t)


def llm(text, context, session):
    hist = _sessions.setdefault(session, [])
    sys_prompt = PERSONA + (f" (You right now: {context}.)" if context else "")
    msgs = [{"role": "system", "content": sys_prompt}, *hist[-2 * HISTORY_TURNS:], {"role": "user", "content": text}]
    out = complete({"messages": msgs, "max_tokens": 90, "temperature": 0.8,
                    "chat_template_kwargs": {"enable_thinking": False}}).strip()
    m = TAG_RE.match(out)
    emotion = m.group(1).strip().lower() if m and m.group(1).strip().lower() in EMOTIONS else "happy"
    reply = TAG_RE.sub("", out, count=1).strip() if m else out
    hist += [{"role": "user", "content": text}, {"role": "assistant", "content": f"[{emotion}]{reply}"}]
    del hist[:-2 * HISTORY_TURNS]
    return emotion, reply


def express(text, context, session, image=None):
    """The duck's response to `text`, as an expression (see EXPRESS). Always returns one —
    a confused tilt if the model's answer cannot be read. `image`: a JPEG (base64) of what it sees;
    the history keeps only a mark of it."""
    hist = _sessions.setdefault(session, [])
    sys_prompt = EXPRESS + (SEEING if image else "") + (f"\n(You right now: {context}.)" if context else "")
    user = text if not image else [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                                   {"type": "text", "text": text}]
    msgs = [{"role": "system", "content": sys_prompt}, *hist[-2 * HISTORY_TURNS:], {"role": "user", "content": user}]
    raw = complete({"messages": msgs, "max_tokens": 200, "temperature": 0.8,
                    "response_format": {"type": "json_object"}, "chat_template_kwargs": {"enable_thinking": False}})
    try:
        e = json.loads(JSON_RE.search(raw).group(0))
    except (AttributeError, ValueError):
        log.warning("unreadable expression: %r", raw[:200])
        e = {"emotion": "curious", "say": "Quack?", "pre": "inquire", "gesture": "tilt",
             "meaning": "(I didn't understand.)"}
    pick = lambda k, allowed, default: e.get(k) if e.get(k) in allowed else default
    if isinstance(e.get("emotion"), str):
        e["emotion"] = e["emotion"].strip().lower()
    out = {
        "emotion": pick("emotion", EMOTIONS, "happy"),
        "say": " ".join(str(e.get("say") or "").split()[:SAY_WORDS])[:40],
        "pre": pick("pre", CALLS, "none"),
        "gesture": pick("gesture", GESTURES, "none"),
        "body": pick("body", BODIES, "none"),
        "action": pick("action", ACTIONS, "none"),
        "meaning": str(e.get("meaning") or "")[:240 if image else 160],
        "end": e.get("end") is True,
    }
    # the duck-speak syllables robotd says, its own name as the persona writes it
    out["pinyin"] = duckspeak.syllables(out["say"], {P.name: P.name_syllables} if P.name_syllables else None)
    if image:
        out["seen"] = True
    hist += [{"role": "user", "content": text + (" (a photo was attached)" if image else "")},
             {"role": "assistant", "content": json.dumps(out, ensure_ascii=False)}]
    del hist[:-2 * HISTORY_TURNS]
    return out


def speak(sentence, voice):
    from ducktalk import duck_talk
    with _tts_lock:
        wav = np.concatenate([j["tts_speech"].squeeze(0).cpu().numpy()
                              for j in _tts.inference_instruct2(sentence, LIVELY, voice["prompt"], stream=False)])
    sr = _tts.sample_rate
    if voice.get("level"):
        wav = duck_talk(wav, sr, voice["level"])
    buf = io.BytesIO()
    sf.write(buf, wav.astype(np.float32), sr, format="WAV", subtype="PCM_16")
    return sr, base64.b64encode(buf.getvalue()).decode()


def make_app():
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel

    class Judge(BaseModel):
        kind: str
        state: dict = {}
        images: dict = {}

    class Ask(BaseModel):
        text: str
        context: str = ""
        session: str = "xiaobai"
        voice: dict | None = None
        image: str | None = None        # base64 JPEG of what it sees (look)

    app = FastAPI()

    @app.get("/health")
    def health():
        try:
            model = served_model(refresh=not LLM_MODEL_PIN)
        except (OSError, ValueError, LookupError):
            model = None
        try:
            jev = json.loads(urllib.request.urlopen(JEV_URL + "/health", timeout=2).read())
        except (OSError, ValueError):
            jev = {"ok": False}
        return {"ok": True, "tts": _tts is not None, "llm": model is not None, "model": model, "voice": VOICE,
                "jev": jev}

    @app.post("/judge")
    def judge_ep(j: Judge):
        """Forwarded to duckjev (judge.py in its own venv: the SDK's pydantic is newer than ours)."""
        body = json.dumps({"kind": j.kind, "state": j.state, "images": j.images}).encode()
        req = urllib.request.Request(JEV_URL + "/judge", data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                out = json.loads(r.read())
        except (OSError, ValueError) as e:
            log.info("judge %s: duckjev unreachable (%r)", j.kind, e)
            return {"ok": False, "error": "jev_down"}
        if out.get("ok"):
            log.info("judge %s %.2f s -> %s", j.kind, out.get("llm_s", 0),
                     json.dumps({k: v.get("noul", v.get("choice")) for k, v in out.get("answers", {}).items()},
                                ensure_ascii=False))
        else:
            log.info("judge %s: %s", j.kind, out.get("error"))
        return out

    @app.post("/express")
    def express_ep(a: Ask):
        t = time.time()
        out = express(a.text, a.context, a.session, a.image)
        out["llm_s"] = round(time.time() - t, 2)
        log.info("express %r%s -> %s", a.text, f" + photo {len(a.image) * 3 // 4 // 1024} KB" if a.image else "",
                 json.dumps(out, ensure_ascii=False))
        return out

    @app.post("/chat")
    def chat(a: Ask):
        t = time.time()
        emotion, reply = llm(a.text, a.context, a.session)
        return {"emotion": emotion, "reply": reply, "llm_s": round(time.time() - t, 2)}

    @app.post("/talk")
    def talk(a: Ask):
        voice = {**VOICE, **(a.voice or {})}

        def gen():
            t0 = time.time()
            emotion, reply = llm(a.text, a.context, a.session)
            yield json.dumps({"type": "reply", "emotion": emotion, "text": reply,
                              "llm_s": round(time.time() - t0, 2)}, ensure_ascii=False) + "\n"
            for i, s in enumerate(x.strip() for x in SENT_RE.split(reply)):
                if not s or _tts is None:
                    continue
                t = time.time()
                sr, wav = speak(s, voice)
                yield json.dumps({"type": "audio", "i": i, "text": s, "sr": sr, "wav": wav,
                                  "tts_s": round(time.time() - t, 2)}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "end", "total_s": round(time.time() - t0, 2)}) + "\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    return app


def warm_up():
    """One throwaway expression at start: the first request after the LLM box comes up took 6.4 s
    (2026-10-16), the next ones 0.65 s. Retried until the LLM answers, so boot order does not matter."""
    for _ in range(60):
        try:
            t = time.time()
            express("Hello", "", "_warmup")
            log.info("llm warm in %.1f s", time.time() - t)
            return
        except Exception as e:  # noqa: BLE001 - the LLM may still be loading
            log.info("llm not ready (%s); retrying", e)
            time.sleep(10)


def main():
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if TTS_ON:
        threading.Thread(target=load_tts, daemon=True).start()
    threading.Thread(target=warm_up, daemon=True).start()
    uvicorn.run(make_app(), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
