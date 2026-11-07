#!/bin/bash
# Put the DuckBuddy software on the brain, from the Mac. Run from anywhere in the repo:
#
#   deploy/brain/deploy.sh <user@host> [--install] [--no-build] [--no-start]
#
#   --install    also run the board setup (deploy/brain/install.sh, with sudo) first.
#                Needed once on a fresh board, and again when deploy/brain/rootfs or the overlay
#                changed. A changed overlay needs a reboot afterwards (the script says so).
#   --no-build   copy the binaries built last time instead of building them
#   --no-start   copy everything, do not (re)start the services
#
#   BRAIN_SSH_OPTS   extra ssh options, e.g. "-o IdentitiesOnly=yes -i ~/.ssh/id_ed25519.pub"
#   ROBOT_CONFIG     the robot config ~/robot/active.toml points at, from deploy/robots
#                    (default opi-hl2915-robothat-e1.toml; only set on the first deploy)
#
# What goes where on the brain (the login user's home):
#   ~/robot      robotd, tofd, robotctl, sounds, the robot configs, robotd.env, onnxruntime, recs/ (logs)
#   ~/lifed ~/voiced ~/visiond ~/duckweb ~/persona   the Python services (tools/), ~/lifed/voice the clips
#   ~/models/asr-sensevoice                          SenseVoice-Small int8, silero VAD, gtcrn denoiser
#   ~/.config/systemd/user                           the user units (deploy/brain/units)
#   /var/lib/robot/sounds                            robotd's sound bank (sounds ensure-bank)
#
# robotd runs with ROBOTD_ARGS="--fake --no-policy" from ~/robot/robotd.env until the legs are
# built and calibrated: no servo bus, nothing moves; the voice, the sounds, the camera, the ToF and
# the phone page all work. Edit robotd.env on the brain to change it (deploy never overwrites it).
set -euo pipefail

usage() { sed -n '2,27p' "$0"; exit "${1:-0}"; }

HOST=""
INSTALL=0
BUILD=1
START=1
while [ $# -gt 0 ]; do
	case "$1" in
		--install) INSTALL=1 ;;
		--no-build) BUILD=0 ;;
		--no-start) START=0 ;;
		-h|--help) usage 0 ;;
		-*) echo "unknown option: $1" >&2; usage 2 ;;
		*) [ -z "$HOST" ] || usage 2; HOST="$1" ;;
	esac
	shift
done
[ -n "$HOST" ] || usage 2

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="${ROBOT_CONFIG:-opi-hl2915-robothat-e1.toml}"
VOICE="en-US-JennyNeural"
VOICE_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/duckbuddy/voice-$VOICE"
BIN="$REPO/target/aarch64-unknown-linux-gnu/release"
# shellcheck disable=SC2206
SSH=(ssh ${BRAIN_SSH_OPTS:-})
RSYNC=(rsync -rlptz --delete -e "${SSH[*]}")
TOOL_EXCLUDES=(--exclude '__pycache__' --exclude 'test_*.py' --exclude '.venv')

say() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ -f "$REPO/deploy/robots/$CONFIG" ] || die "no deploy/robots/$CONFIG"

# ---- on the Mac --------------------------------------------------------------
if [ "$BUILD" -eq 1 ]; then
	say "building robotd, tofd, robotctl, sounds for the board"
	(cd "$REPO" && cargo board -p robotd -p tof -p robotctl -p sounds --bins)
fi
for b in robotd tofd robotctl sounds; do
	[ -x "$BIN/$b" ] || die "no $BIN/$b (build first, or drop --no-build)"
done

# The person's-voice clips lifed plays (tools/lifed/prompts.py), rendered once with edge-tts and
# again whenever prompts.py changes.
PROMPTS="$REPO/tools/lifed/prompts.py"
if [ ! -f "$VOICE_CACHE/.done" ] || [ "$PROMPTS" -nt "$VOICE_CACHE/.done" ]; then
	say "rendering the voice clips ($VOICE)"
	command -v ffmpeg >/dev/null || die "ffmpeg is needed to render the voice clips (brew install ffmpeg)"
	rm -rf "$VOICE_CACHE"
	mkdir -p "$VOICE_CACHE"
	uv run --no-project --with 'edge-tts>=7.2.8' --with numpy --with scipy --with soundfile \
		python "$REPO/tools/lifed/render_prompts.py" "$VOICE_CACHE" --voice "$VOICE"
	touch "$VOICE_CACHE/.done"
fi

# ---- copy ----------------------------------------------------------------------
say "copying to $HOST"
"${SSH[@]}" "$HOST" 'mkdir -p ~/robot/recs ~/lifed ~/voiced ~/visiond ~/duckweb ~/persona ~/.config/systemd/user ~/duckbuddy-brain'

if [ "$INSTALL" -eq 1 ]; then
	"${RSYNC[@]}" "$REPO/deploy/brain/install.sh" "$REPO/deploy/brain/overlay" "$REPO/deploy/brain/rootfs" "$HOST:duckbuddy-brain/"
	say "board setup (install.sh)"
	"${SSH[@]}" -t "$HOST" 'cd ~/duckbuddy-brain && sudo ./install.sh'
fi

rsync -tz -e "${SSH[*]}" "$BIN/robotd" "$BIN/tofd" "$BIN/robotctl" "$BIN/sounds" "$HOST:robot/"
rsync -tz -e "${SSH[*]}" "$REPO"/deploy/robots/*.toml "$HOST:robot/"
for t in lifed voiced visiond duckweb persona; do
	"${RSYNC[@]}" "${TOOL_EXCLUDES[@]}" --exclude 'voice/' --exclude 'state.json' --exclude 'duckcam' \
		"$REPO/tools/$t/" "$HOST:$t/"
done
"${RSYNC[@]}" "$VOICE_CACHE/" --exclude '.done' "$HOST:lifed/voice/"
rsync -tz -e "${SSH[*]}" "$REPO"/deploy/brain/units/*.service "$HOST:.config/systemd/user/"

# ---- on the brain ----------------------------------------------------------------
say "setting up on the brain"
"${SSH[@]}" "$HOST" CONFIG="$CONFIG" START="$START" bash -s <<'REMOTE'
set -euo pipefail
say() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }
cd ~/robot

[ -e active.toml ] || ln -sfn "$CONFIG" active.toml
echo "config: $(readlink active.toml)"
if [ ! -e robotd.env ]; then
	cat > robotd.env <<'EOF'
# Extra robotd arguments (deploy/brain/units/robotd-dev.service). --fake --no-policy: no servo bus,
# nothing moves, while the legs are not built and calibrated. Empty it for the real robot.
ROBOTD_ARGS="--fake --no-policy"
EOF
fi
grep '^ROBOTD_ARGS' robotd.env

ORT=onnxruntime-linux-aarch64-1.28.3
if [ ! -e "$ORT/lib/libonnxruntime.so" ]; then
	say "onnxruntime 1.28.3 (robotd's policy runtime)"
	curl -fL --retry 3 "https://github.com/microsoft/onnxruntime/releases/download/v1.28.3/$ORT.tgz" | tar -xz
fi

say "sound bank"
rm -rf ~/robot/sounds.new
[ -w /var/lib/robot/sounds ] || sudo install -d -o "$(id -un)" -g "$(id -gn)" /var/lib/robot/sounds
./sounds ensure-bank

say "duckcam (visiond's camera program)"
gcc -O2 -Wall -o ~/visiond/duckcam.new ~/visiond/duckcam.c -lAWIspApi -lisp -lisp_ini -lpthread -ldl -lm
mv -f ~/visiond/duckcam.new ~/visiond/duckcam

say "voiced's Python (sherpa-onnx)"
if ! ~/voiced/.venv/bin/python -c 'import sherpa_onnx, numpy' 2>/dev/null; then
	python3 -m venv --system-site-packages ~/voiced/.venv
	~/voiced/.venv/bin/pip install --quiet --upgrade pip
	~/voiced/.venv/bin/pip install --quiet sherpa-onnx
fi
~/voiced/.venv/bin/python -c 'import sherpa_onnx; print("sherpa-onnx", sherpa_onnx.__version__)'
python3 -c 'import cv2, numpy; print("opencv", cv2.__version__, "numpy", numpy.__version__)' \
	|| die "python3-opencv / python3-numpy missing: run deploy.sh with --install"

M=~/models/asr-sensevoice
REL=https://github.com/k2-fsa/sherpa-onnx/releases/download
mkdir -p "$M"
if [ ! -f "$M/model.int8.onnx" ] || [ ! -f "$M/tokens.txt" ]; then
	say "SenseVoice-Small int8 (about 160 MB)"
	tmp="$(mktemp -d)"
	curl -fL --retry 3 "$REL/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2" | tar -xj -C "$tmp"
	mv "$tmp"/sherpa-onnx-sense-voice-*/model.int8.onnx "$tmp"/sherpa-onnx-sense-voice-*/tokens.txt "$M/"
	rm -rf "$tmp"
fi
[ -f "$M/silero_vad.onnx" ] || curl -fL --retry 3 -o "$M/silero_vad.onnx" "$REL/asr-models/silero_vad.onnx"
[ -f "$M/gtcrn_simple.onnx" ] || curl -fL --retry 3 -o "$M/gtcrn_simple.onnx" "$REL/speech-enhancement-models/gtcrn_simple.onnx"
ls -l "$M"

say "services"
[ "$(loginctl show-user "$(id -un)" -p Linger --value)" = yes ] \
	|| echo "note: lingering is off, the services start only while you are logged in (install.sh turns it on)"
UNITS="robotd-dev tofd-dev lifed-dev voiced-dev visiond-dev duckweb-dev"
systemctl --user daemon-reload
systemctl --user enable $UNITS 2>&1 | grep -v '^Created symlink' || true
if [ "$START" = 1 ]; then
	systemctl --user restart robotd-dev tofd-dev visiond-dev duckweb-dev
	systemctl --user restart lifed-dev voiced-dev
	sleep 5
	for u in $UNITS; do printf '%-14s %s\n' "$u" "$(systemctl --user is-active "$u" || true)"; done
	echo "logs: ~/robot/recs/<name>-service.log"
fi
REMOTE
say "done"
