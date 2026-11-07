# persona — who the duck is

The framework (life layer, voice, vision, brain service) is kept apart from "who this duck is". The name, character, way of speaking and voice all live in one JSON persona file, which each service reads at start-up.

| File | Content |
|---|---|
| `persona.py` | the loader; the field descriptions are here too |
| `example.json` | the example duck, "Biscuit". The open-source repo ships only this one |
| `duckspeak.py` | turns English text into duck-speak syllables for robotd (used by lifed and duckbrain) |
| `test_persona.py`, `test_duckspeak.py` | tests |

**Where the persona is used**:

| Service | What it uses |
|---|---|
| voiced | its name, and the words that speech recognition often hears by mistake in place of the name (`name_aliases`) |
| lifed | name, how lively it is, how talkative it is; the lines in the offline small brain where it says its name (`name_syllables`) |
| duckweb | the name shown on the web page |
| duckbrain | "who you are, what your character is, how you talk" in the duck-speak reply prompt, and the speech synthesis style and reference voice |
| duckbrain/judge.py | "what this duck is", given to Jev, and the name in each question |

The reply format (JSON fields, list of actions) and rules such as "if you don't know, say you don't know" belong to the framework, not to the persona.

## How the persona file is found

It looks in this order and uses the first one that exists:
1. the file named by the environment variable `$DUCK_PERSONA`;
2. `~/.config/duck/persona.json`;
3. `example.json` in this directory.

The file it finds is laid on top of `example.json`, so you only need to write the fields that differ from the example. A wrong field name gives an error right away; it does not quietly fall back to the example.

Text fields can be written as a list of strings. On loading they are joined directly, with no separator; write `\n` yourself where you need a line break. `name_aliases` is the exception: it is a list of separate names.

## The name

- `name`: what you call the duck. Pick a word that is not common in everyday talk, with two syllables if you can: a very short or soft name is easy for the voice detector to cut and for speech recognition to miss.
- `name_aliases`: what speech recognition writes when it mishears the name, in lowercase (for "Biscuit": "biscuits", "biskit", ...). voiced matches the name and these as whole words, in any case: "BISCUIT," counts, "biscuitry" does not. Look at voiced's log (`heard: ...`) after calling the duck a few times and add what it wrote.
- `name_syllables`: how the duck says its own name in duck-speak, as robotd syllables with tone digits ("bis1 kit5"). Leave it empty and it is made from the name.

## Language

The duck is spoken to in English:

- voiced transcribes with Moonshine v2 (English only). It drops a transcript as noise only when it has no English words, or only filler words ("Okay.", "Mm.", "Uh, the."). Short commands such as "Stop.", "Go." or "Sit." always pass.
- lifed matches its command words as whole words ("hi" is not found in "this"), and not right after a negation ("don't sit down"). The words that stop something ("stop", "wait", "cancel") always count.
- The duck answers in duck-speak: robotd makes one quack per syllable. `duckspeak.py` turns the English words of an answer into robotd's syllables: one per English syllable, the vowel kept, the stressed syllable high, the last one falling (or rising for a question), and the punctuation as pauses.
- The few spoken instructions (Wi-Fi by QR code, its page address, missions) are recorded clips in an English voice. After changing `tools/lifed/prompts.py`, render them again and copy them to the robot:

```bash
uv run --no-project --with edge-tts --with numpy --with scipy --with soundfile \
    python tools/lifed/render_prompts.py /tmp/voice
scp /tmp/voice/*.wav <robot>:lifed/voice/
```

Then restart lifed.

## Deployment

Each service imports `persona.py` from the `persona/` directory **next to** its own directory:
- in the repo it is `tools/persona`;
- on the robot it is `~/persona`;
- on the brain server it is the directory next to the brain directory.

**Robot (Orange Pi)**:

```bash
ssh <robot> 'mkdir -p ~/persona ~/.config/duck'
scp tools/persona/persona.py tools/persona/duckspeak.py tools/persona/example.json <robot>:persona/
scp my-duck.json <robot>:.config/duck/persona.json
```

Then restart lifed, voiced and duckweb.

**Brain server**: put `persona.py`, `duckspeak.py` and `example.json` in `persona/`, the directory next to `duckbrain/`. Put the persona in `~/.config/duck/persona.json` of the user that runs the brain service, then restart duckbrain and duckjev.

⚠ The new versions of duckbrain and lifed do not start at all if the `persona/` directory or `duckspeak.py` in it is missing. **Deploy the persona first, then update the services.** A persona file written for the Chinese version has a `name_pinyin` field: it is refused now. Rename it to `name_syllables` (or remove it), and write the other text fields in English.

At start-up lifed prints `persona: <name> (<file>)` in its log, so you can check which persona it uses.
