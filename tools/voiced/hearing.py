# -*- coding: utf-8 -*-
"""voiced, part 1: the duck's ears, offline (P2 of docs/project/duck-life-roadmap-20261014-CN.md).

Always listening, no wake word: silero VAD cuts each utterance out of the mic stream, SenseVoice-Small
(int8, sherpa-onnx, on the OPi's CPU, set to English) transcribes it, and the text goes to lifed as an
event. Its name in the sentence (the persona's name, and what ASR writes for it: whole words, any
case) is a call — the duck turns and answers — and opens a conversation in lifed, inside which what is
said is for the duck without the name (`named` on each `say`; voiced's own 8 s `addressed` window is
kept for older lifeds).

Adapted from WaliRobot's `brain/wali/hearing.py` (same models, same lessons: copy a VAD segment before
popping it, transcribe on its own thread so the mic loop never stalls, restart arecord when it dies,
drop segments too quiet to be speech).

    ~/voiced/.venv/bin/python hearing.py [--mic duck_in] [--models ~/models/asr-sensevoice]
    ~/voiced/.venv/bin/python hearing.py --wav test.wav     # transcribe one 16 kHz wav and exit
"""
import argparse
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time

import numpy as np
import sherpa_onnx

import doa
from stereo import FACTOR, FS_IN, Decimator, Ring

# who the duck is (its name, its character) comes from its persona: tools/persona, ~/persona on the robot
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "persona"))
from persona import load as load_persona  # noqa: E402

PERSONA = load_persona()
NAME = PERSONA.name
# what SenseVoice writes for the name when it mishears it (the persona's list: for "Biscuit", "biscuits" /
# "biskit" / ...)
NAME_ALIASES = PERSONA.name_aliases
# The name and its mishearings, as whole words in any case ("Biscuit," or "BISCUIT" but not "biscuitry");
# a space in an alias matches any run of spaces or punctuation ("bis kit", "bis-kit")
NAME_RE = re.compile(r"(?<![a-z0-9])(?:" + "|".join(
    r"[\s,.!?-]+".join(re.escape(w) for w in n.split())
    for n in sorted({NAME, *NAME_ALIASES}, key=len, reverse=True) if n.split()) + r")(?![a-z0-9])", re.I)
# SenseVoice's language: the duck is spoken to in English
LANGUAGE = "en"
ADDRESSED_S = 8.0          # after a call, speech is for the duck this long
# 0.5 cut the name short to 0.7 s, heard as another word (2026-10-14: servo and fan noise at RMS 0.026,
# a voice at 1 m only ~0.08); 0.35 keeps the whole word. Tuned on the two-syllable Chinese name: check
# it again with the English name (a short or soft name is the easiest to cut).
VAD_THRESHOLD = 0.35
PGA_CAPTURE = -1           # codec capture gain, 0.5 dB steps; -1 leaves it to brain-audio-init
                           # (BRAIN_MIC_GAIN in /etc/default/brain-audio, deploy/brain)
VAD_MIN_SILENCE = 0.35
VAD_MIN_SPEECH = 0.25
VAD_MAX_SPEECH = 12.0
MIN_RMS = 0.01
# VAD opens late on a soft onset: alone, the name was cut to 0.7 s and heard as other words. Each
# segment is re-cut from the raw stream with this much before and after it (tuned on the Chinese name).
PRE_ROLL_S, POST_ROLL_S = 0.25, 0.1
# The VAD listens through a neural denoiser (GTCRN, sherpa-onnx, 0.5 MB): on the robot it took the
# servo / fan floor from RMS 0.027 to 0.0008 while a voice lost only 3 dB. SenseVoice still gets the
# raw audio — denoised, the name came out wrong.
DENOISER = "gtcrn_simple.onnx"
HISTORY_S = 30.0             # quieter segments are noise, not fed to ASR (raise if it hallucinates)
MIN_CHARS = 1
# The VAD's own segment is the denoised audio, where steady noise is all but gone and a voice keeps
# its level: gate on that, not on the raw re-cut. 2026-10-16: for 14 minutes something in the room
# kept the raw level at RMS 0.057 (a voice at 1 m is ~0.08) and the VAD cut a segment every 5 s —
# 181 of them, SenseVoice hearing "Mm.", ".", "Okay.", a Japanese kana — while the quiet room's denoised floor
# is 0.0006-0.0044. Speech the same evening (denoised): 0.020-0.021 at 1 m, 0.016-0.018 at 2-3 m;
# the gate sits at half the far voice and twice the floor's peak.
DN_MIN_RMS = 0.008
# What ASR makes of noise and murmurs: an utterance that is only these words (and punctuation) is
# dropped. Seen on the robot in auto mode: "Okay." and "Mm." out of fan hiss; "you", "the" and "i" are
# what an English model writes for a breath or a click. Check the noise log on the robot and add to it.
FILLERS = {"uh", "um", "umm", "uhm", "hmm", "hm", "mm", "mmm", "mhm", "ah", "oh", "eh", "er", "erm", "huh", "ha",
           "ok", "okay", "yeah", "the", "a", "i", "so", "and", "you", "it", "is"}
# Short words that are real commands or answers, never noise, whatever the list above says: "stop"
# must reach lifed even said once and alone.
KEEP = {"stop", "wait", "go", "sit", "rest", "start", "cancel", "yes", "no", "bye", "hi", "hello", "hey", "louder",
        "quieter", "continue", "halt", "freeze", "sleep"}
WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
STATS_S = 600.0              # how often the drop counts go to the log
TAG_RE = re.compile(r"<\|[^|]*\|>")
LIFED = "/tmp/lifed.sock"
# The direction of what is heard (docs/project/attention-gaze-design-20261018-CN.md §1.1): the two head
# mics come in as 48 kHz stereo; the last STEREO_S of it stays, so each VAD segment's span - and the
# NOISE_S of noise before it, for the fan's bins - can be cut out for doa.py. A direction this unsure
# is sent as unknown (yaw 0, dir_ok false).
STEREO_S = 14.0
NOISE_S = 0.5
DIR_MIN_CONF = 0.35
CHUNK_FRAMES = 1536            # 32 ms of 48 kHz stereo per read


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def make_recognizer(d):
    return sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=f"{d}/model.int8.onnx", tokens=f"{d}/tokens.txt", num_threads=2, use_itn=True, language=LANGUAGE)


def make_vad(d):
    c = sherpa_onnx.VadModelConfig()
    c.silero_vad.model = f"{d}/silero_vad.onnx"
    c.silero_vad.threshold = VAD_THRESHOLD
    c.silero_vad.min_silence_duration = VAD_MIN_SILENCE
    c.silero_vad.min_speech_duration = VAD_MIN_SPEECH
    c.silero_vad.max_speech_duration = VAD_MAX_SPEECH
    c.sample_rate = 16000
    return sherpa_onnx.VoiceActivityDetector(c, buffer_size_in_seconds=30)


def make_denoiser(d):
    path = f"{d}/{DENOISER}"
    if not os.path.exists(path):
        return None
    return sherpa_onnx.OnlineSpeechDenoiser(sherpa_onnx.OnlineSpeechDenoiserConfig(
        model=sherpa_onnx.OfflineSpeechDenoiserModelConfig(
            gtcrn=sherpa_onnx.OfflineSpeechDenoiserGtcrnModelConfig(model=path))))


def transcribe(rec, samples):
    st = rec.create_stream()
    st.accept_waveform(16000, samples)
    rec.decode_stream(st)
    return TAG_RE.sub("", st.result.text).strip()


def noise_text(text):
    """Whether a transcript is what noise sounds like: no English words at all (only punctuation, or
    another script: "う"), or nothing but filler words ("Okay.", "Uh, the."). Short real words stay:
    "Stop!", "Go.", "Sit."."""
    ws = WORD_RE.findall(text.lower().replace("\u2019", "'"))
    if not ws:
        return True
    if any(w in KEEP for w in ws):
        return False
    return all(w in FILLERS for w in ws)


def named_in(text):
    """Whether `text` says the duck's name (or a mishearing of it), and the text without it."""
    if not NAME_RE.search(text):
        return False, text
    rest = re.sub(r"\s+", " ", NAME_RE.sub(" ", text))
    rest = re.sub(r"\s+([,.!?;:])", r"\1", rest)
    rest = re.sub(r"[,;:]+(?=[,.!?;:])", "", rest)              # "Okay, Biscuit." -> "Okay."
    rest = re.sub(r"^[\s,.!?;:~-]+|[\s,;:~-]+$", "", rest)
    return True, rest


def to_lifed(event):
    try:
        s = socket.socket(socket.AF_UNIX)
        s.settimeout(1.0)
        s.connect(LIFED)
        s.sendall((json.dumps({"jsonrpc": "2.0", "method": "life.event", "params": event},
                              ensure_ascii=False) + "\n").encode())
        s.close()
    except OSError as e:
        log(f"lifed unreachable: {e}")


class Recent:
    """The last `cap` samples of the stream, addressable by absolute sample index (VAD's `start`)."""

    def __init__(self, cap):
        self.cap, self.buf, self.total = cap, np.zeros(0, dtype=np.float32), 0

    def add(self, x):
        self.buf = np.concatenate([self.buf, x])[-self.cap:]
        self.total += len(x)

    def cut(self, a, b):
        first = self.total - len(self.buf)
        a, b = max(a, first), min(b, self.total)
        return self.buf[a - first:b - first].copy()


class Ears:
    def __init__(self, a):
        self.a = a
        self.addressed_until = 0.0
        self.stats = {"quiet": 0, "noise_text": 0, "heard": 0}
        self.last_onset = 0.0
        self.stats_at = time.time()

    def count(self, what):
        self.stats[what] += 1
        if time.time() - self.stats_at >= STATS_S:
            log("last %.0f min: %s" % ((time.time() - self.stats_at) / 60, " ".join(f"{k} {v}" for k, v in self.stats.items())))
            self.stats = dict.fromkeys(self.stats, 0)
            self.stats_at = time.time()

    def heard(self, text, d=None):
        """One utterance: a call if it names the duck, then (addressed or not) what was said. `d`: its
        direction (doa.Direction), or None."""
        now = time.time()
        ok = d is not None and d.conf >= DIR_MIN_CONF
        where = {"yaw": round(d.yaw, 3) if ok else 0.0, "yaw_back": round(d.yaw_back, 3) if ok else None,
                 "dir_sigma": round(d.sigma, 3) if d else None, "dir_conf": round(d.conf, 2) if d else 0.0,
                 "dir_ok": ok}
        named, rest = named_in(text)
        if not named:
            rest = text.strip(" ,.!?~")
        elif not re.search(r"[a-z0-9]", rest, re.I):
            rest = ""                                          # the name alone
        if named:
            self.addressed_until = now + ADDRESSED_S
            to_lifed({"type": "call", "text": text, **where})
        addressed = now < self.addressed_until
        if rest:
            to_lifed({"type": "say", "text": rest, "addressed": addressed, "named": named, **where})
            if addressed:
                self.addressed_until = now + ADDRESSED_S     # a conversation keeps the window open
        side = (f"  from {np.degrees(d.yaw):+.0f} deg (or {np.degrees(d.yaw_back):+.0f}), conf {d.conf:.2f}"
                + ("" if ok else " - unsure") if d else "")
        log(f"heard: {text!r}{'  [to me]' if named or addressed else ''}{side}")

    def worker(self, q):
        rec = None
        while rec is None:
            try:
                rec = make_recognizer(self.a.models)
            except Exception as e:  # noqa: BLE001 - retry rather than die
                log(f"SenseVoice failed to load, retrying in 5 s: {e!r}"[:120])
                time.sleep(5)
        log("SenseVoice ready")
        while True:
            samples, dn_rms, st, noise = q.get()
            rms = float(np.sqrt((samples ** 2).mean()))
            if rms < MIN_RMS or dn_rms < DN_MIN_RMS:
                log(f"segment {len(samples) / 16000:.1f} s too quiet (rms {rms:.3f}, denoised {dn_rms:.4f})")
                self.count("quiet")
                continue
            t0 = time.time()
            text = transcribe(rec, samples)
            if len(text) < MIN_CHARS:
                continue
            took = f"{len(samples) / 16000:.1f} s in {time.time() - t0:.2f} s (rms {rms:.3f}, denoised {dn_rms:.4f})"
            if noise_text(text) and not NAME_RE.search(text):
                log(f"noise {text!r}: {took}")
                self.count("noise_text")
                continue
            log(f"asr {took}")
            self.count("heard")
            d = None
            if len(st) >= int(0.1 * FS_IN):
                try:
                    d = doa.direction(st[:, 0], st[:, 1], FS_IN,
                                      noise=(noise[:, 0], noise[:, 1]) if len(noise) >= int(0.1 * FS_IN) else None)
                except Exception as e:  # noqa: BLE001 - a direction is a bonus; the words still count
                    log(f"direction failed: {e!r}")
            self.heard(text, d)

    def keep_clock(self):
        """Hold the shared 48 kHz stream open with silence: the codec's playback and capture share
        one I2S clock, and when the last player closed it the mic read zeros (2026-10-14).
        Needs duck_out / duck_in from /etc/asound.conf (deploy/brain/rootfs/etc/asound.conf)."""
        if not self.a.keep_alive:
            return
        cmd = ["aplay", "-q", "-D", self.a.keep_alive, "-f", "S16_LE", "-r", "48000", "-c", "2", "-t", "raw", "/dev/zero"]
        while True:
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.wait()
            log(f"clock keep-alive exited ({p.returncode}); restarting")
            time.sleep(2.0)

    def run(self):
        threading.Thread(target=self.keep_clock, daemon=True).start()
        time.sleep(0.5)
        vad = make_vad(self.a.models)
        if self.a.pga is not None:
            subprocess.run(["amixer", "-q", "-c", "aic3104", "cset", "name=PGA Capture Volume",
                            f"{self.a.pga},{self.a.pga}"], check=False)
        q = queue.Queue(maxsize=8)
        threading.Thread(target=self.worker, args=(q,), daemon=True).start()
        # 48 kHz stereo straight from the dsnoop: both mics for the direction, mixed and decimated here
        # (stereo.Decimator) for VAD and ASR - no ALSA plug resampling in between
        cmd = ["arecord", "-D", self.a.mic, "-f", "S16_LE", "-r", str(FS_IN), "-c", "2", "-t", "raw", "-B", "800000", "-q"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        denoiser = make_denoiser(self.a.models)
        log(f"listening on {self.a.mic} (VAD{' on denoised audio' if denoiser else ''} + SenseVoice, name {NAME})")
        buf = np.zeros(0, dtype=np.float32)
        hist = Recent(int(HISTORY_S * 16000))
        ring, dec = Ring(int(STEREO_S * FS_IN)), Decimator()
        pending = b""                 # a pipe read may end mid-frame: the rest waits for the next one
        was_speaking = False
        while True:
            data = proc.stdout.read(CHUNK_FRAMES * 4)
            if not data:
                log("arecord stopped; restarting the mic")
                proc.terminate()
                time.sleep(1.0)
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                vad.reset()
                buf = np.zeros(0, dtype=np.float32)
                hist = Recent(int(HISTORY_S * 16000))
                ring, dec = Ring(int(STEREO_S * FS_IN)), Decimator()
                pending = b""
                continue
            data = pending + data
            whole = len(data) - len(data) % 4
            data, pending = data[:whole], data[whole:]
            if not data:
                continue
            st = np.frombuffer(data, dtype=np.int16).reshape(-1, 2).astype(np.float32) / 32768.0
            ring.add(st)
            raw = dec.process(st.mean(axis=1))
            hist.add(raw)                         # raw, for ASR; indices line up with the VAD's
            heard = raw if denoiser is None else np.asarray(denoiser.run(raw, 16000).samples, dtype=np.float32)
            buf = np.concatenate([buf, heard])
            while len(buf) >= 512:
                vad.accept_waveform(buf[:512])
                buf = buf[512:]
            # someone starts talking: tell lifed now, so in a conversation it looks at them while
            # they talk rather than after (lifed knows whether it is in one)
            speaking = vad.is_speech_detected()
            if speaking and not was_speaking and time.time() - self.last_onset > 1.5:
                self.last_onset = time.time()
                threading.Thread(target=to_lifed, args=({"type": "hearing"},), daemon=True).start()
            was_speaking = speaking
            while not vad.empty():
                start, seg = vad.front.start, np.asarray(vad.front.samples, dtype=np.float32)
                vad.pop()
                n = len(seg)
                dn_rms = float(np.sqrt((seg ** 2).mean())) if n else 0.0
                a16, b16 = start - int(PRE_ROLL_S * 16000), start + n + int(POST_ROLL_S * 16000)
                samples = hist.cut(a16, b16)
                if len(samples) / 16000 < 0.3:
                    continue
                st_seg = ring.cut(a16 * FACTOR, b16 * FACTOR)
                noise = ring.cut((a16 - int(NOISE_S * 16000)) * FACTOR, (a16 - int(0.05 * 16000)) * FACTOR)
                try:
                    q.put_nowait((samples, dn_rms, st_seg, noise))
                except queue.Full:
                    pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mic", default="duck_in", help="capture device (/etc/asound.conf's dsnoop)")
    ap.add_argument("--keep-alive", default="duck_out",
                    help="playback device held open with silence to keep the codec clock running ('' = off)")
    ap.add_argument("--models", default=os.path.expanduser("~/models/asr-sensevoice"))
    ap.add_argument("--pga", type=int, default=PGA_CAPTURE, help="codec capture gain (0-119); -1 leaves it")
    ap.add_argument("--wav")
    a = ap.parse_args()
    if a.pga is not None and a.pga < 0:
        a.pga = None
    if a.wav:
        import wave
        with wave.open(a.wav) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        t0 = time.time()
        print(transcribe(make_recognizer(a.models), pcm), f"({time.time() - t0:.2f} s)")
        return
    Ears(a).run()


if __name__ == "__main__":
    main()
