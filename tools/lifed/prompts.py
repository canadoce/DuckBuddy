# -*- coding: utf-8 -*-
"""What the duck says in a person's words, where duck-speak would leave you guessing.

Everyday talk stays duck-speak. A few moments need instructions a person can follow, like
connecting it to a phone's hotspot outdoors: for those it plays a clip in a human voice
(edge-tts, an English voice: render_prompts.py). The clips are recorded ahead of time with
`render_prompts.py` and kept on the robot (~/lifed/voice/<key>.wav), so they work with no
network. A missing clip falls back to the duck-speak line.

Pure data: core.py estimates from the text how long the duck is deaf to itself.
"""

PROMPTS = {
    # QR Wi-Fi provisioning (tools/visiond)
    "scan_start": "Please hold the QR code of your Wi-Fi or phone hotspot twenty to thirty centimeters in front "
                  "of my face, and keep it still for a second or two. If you change your mind, say cancel.",
    "joining": "I can see the QR code. Connecting now, please wait.",
    "joined": "I'm on the network now. Thank you!",
    "already": "I'm already on this network.",
    "timeout": "I didn't see a QR code, so I stopped looking. To try again, ask me to connect to Wi-Fi.",
    "not_wifi": "This QR code is not for a network, so I stopped looking. Please show me the share code of a "
                "Wi-Fi network or a phone hotspot, then ask me to connect to Wi-Fi again.",
    "not_found": "I can't find this hotspot, so I stopped. On an iPhone, turn on Maximize Compatibility and stay "
                 "on the Personal Hotspot page. Ask me to connect to Wi-Fi, wait a few seconds, then switch to "
                 "the QR code and show it to me.",
    "failed": "I could not connect, so I stopped. The password may be wrong. Check it, then ask me to connect to "
              "Wi-Fi again.",
    "cancelled": "Okay, I won't connect.",
    # its phone page's address, read out (on a phone's hotspot you cannot know it): the intro, the
    # address digit by digit (DIGITS), the port
    "addr_intro": "My page address is:",
    "addr_port": "colon, eight zero eight eight. Open it in your phone's browser.",
    "addr_none": "I'm not connected to a network yet.",
    # look: what it sees is told by the brain on the V100; offline it cannot
    "look_offline": "I'm offline right now, so I can't tell what this is.",
    "look_failed": "My eyes are not working right now. Try again in a moment.",
    # missions (mission.py): a spoken route, read back, done step by step
    "mission_ready": "I'm ready. Say start, and I will set off.",
    "mission_ready_dry": "I'm ready. This is a dry run, so I won't really move. Say start, and I will set off.",
    "mission_done": "All done!",
    "mission_failed": "I could not do this step, so I stopped.",
    "mission_paused": "Okay, I stopped. Say continue, and I will keep going.",
    "mission_obstacle": "There is something in front of me, so I stopped.",
    "mission_cancelled": "Okay, I won't go.",
    "ask_turn_or_side": "Should I turn first and then walk, or walk sideways?",
    "ask_how_far": "How far should I walk?",
    "no_sidestep": "I can't walk sideways yet.",
    "too_far": "That is too far. I can walk three meters at most.",
    "too_far_back": "I can't see behind me, so I can back up thirty centimeters at most.",
    "mission_need_stand": "I need to stand up before I can set off.",
}

# one clip per character of an address, put together by lifed
DIGITS = {f"d{i}": w for i, w in enumerate(("zero", "one", "two", "three", "four", "five", "six", "seven",
                                            "eight", "nine"))} | {"dot": "dot"}
# About how long each clip lasts, with its gap, and a whole address read out. English estimates
# (the Chinese clips measured 0.42 s a digit and 12.9 s for a whole address): measure them again on
# the rendered clips (lifed passes the real lengths of the recorded ones; these are the fallback).
DIGIT_S = 0.5
ADDRESS_S = 13.5
# Never its name in a clip (2026-10-17: a clip that said its name came back through its microphone,
# the name cut the clip short as a call, and the command word in it started another scan, again and
# again). The command words are in some (they say what to do); core.py drops what it hears of its
# own clip.

# An estimate for an English voice at the default rate (about 160 words a minute); not measured on
# these clips yet
WORDS_PER_S = 2.7


def seconds(key: str) -> float:
    """About how long a clip lasts (lifed passes the real lengths of the recorded clips)."""
    if key == "address":
        return ADDRESS_S
    return len(PROMPTS.get(key, "").split()) / WORDS_PER_S
