#!/bin/bash
# Set up the brain: an Orange Pi Zero 3W (Allwinner A733) with the Robot HAT E1,
# the head board of the DuckBuddy. Run on the board, from this folder:
#
#   sudo ./install.sh
#
#   ROBOT_USER=name   the login user that runs the DuckBuddy services (default: $SUDO_USER)
#   --no-apt          do not install missing Debian packages
#
# What it sets up (see README.md): the device tree overlay (codec, ToF bus, servo
# UART), the TLV320AIC3104 kernel driver built for the running kernel, the mixer
# setup, /etc/asound.conf, the battery guard, the camera program, the reboot fix,
# U-Boot's key wait (off), device names and groups, the Python packages the DuckBuddy
# services use and the NetworkManager permission for visiond. It also removes the earlier
# opi-robot-hat setup (robot-hat-* services, /opt/robot-hat, the Cone Radio web app).
#
# Safe to run again. Reboot afterwards: the overlay and the driver load at boot.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APT=1
while [ $# -gt 0 ]; do
	case "$1" in
		--no-apt) APT=0; shift ;;
		-h|--help) sed -n '2,16p' "$0"; exit 0 ;;
		*) echo "unknown option: $1" >&2; exit 2 ;;
	esac
done

say() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run with sudo"
USER_NAME="${ROBOT_USER:-${SUDO_USER:-}}"
[ -n "$USER_NAME" ] && [ "$USER_NAME" != root ] || die "set ROBOT_USER=<name> (the normal login user)"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
[ -n "$USER_HOME" ] || die "no such user: $USER_NAME"

grep -q 'BOARDFAMILY=sun60iw2' /etc/orangepi-release 2>/dev/null || die "this is not an Orange Pi A733 (sun60iw2) image"
KV="$(uname -r)"
[ "$KV" = 6.6.98-sun60iw2 ] || die "made for kernel 6.6.98-sun60iw2, this is $KV"

# ---- packages --------------------------------------------------------------
PKGS="python3 python3-libgpiod i2c-tools device-tree-compiler gcc make flex bison bc libssl-dev libelf-dev alsa-utils v4l-utils curl
	python3-numpy python3-opencv python3-serial python3-venv python3-pip polkitd rsync
	python3-fastapi python3-uvicorn python3-soundfile"
missing=""
for p in $PKGS; do
	dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'ok installed' || missing="$missing $p"
done
if [ -n "$missing" ]; then
	[ "$APT" -eq 1 ] || die "missing packages:$missing"
	say "installing:$missing"
	apt-get update && apt-get install -y $missing
fi
for f in libAWIspApi.so libisp.so libisp_ini.so libvencoder.so libMemAdapter.so libVE.so libcdc_base.so; do
	[ -e "/usr/lib/aarch64-linux-gnu/$f" ] || die "missing /usr/lib/aarch64-linux-gnu/$f (Orange Pi camera/Cedar packages)"
done

# ---- earlier setup (opi-robot-hat) -----------------------------------------
say "removing the earlier opi-robot-hat setup"
for u in board-demos-web robot-hat-audio robot-hat-volume robot-hat-battery-guard; do
	if [ -e "/etc/systemd/system/$u.service" ]; then
		systemctl disable --now "$u.service" 2>/dev/null || true
		rm -f "/etc/systemd/system/$u.service"
		echo "removed $u.service"
	fi
done
rm -rf /opt/robot-hat
rm -f /etc/udev/rules.d/99-robot-hat.rules /etc/modules-load.d/robot-hat-camera.conf
if [ -d "$USER_HOME/development/board_demos" ] || [ -d "$USER_HOME/.local/share/board-demos" ]; then
	backup="$USER_HOME/board-demos-backup-$(date +%Y%m%d-%H%M%S).tgz"
	tar -C "$USER_HOME" -czf "$backup" --ignore-failed-read \
		development/board_demos .local/share/board-demos 2>/dev/null || true
	chown "$USER_NAME:$USER_NAME" "$backup"
	rm -rf "$USER_HOME/development/board_demos" "$USER_HOME/.local/share/board-demos"
	echo "Cone Radio removed (copy in $backup)"
fi

# ---- codec kernel driver ---------------------------------------------------
# The image's kernel has CONFIG_SND_SOC_TLV320AIC3X off, so the codec modules
# are built here from the matching kernel source. No modversions or module
# signing in this kernel: the vermagic must match, nothing else.
MOD_DIR="/lib/modules/$KV/extra"
SRC=/usr/src/linux-sun60iw2-6.6.98
KERNEL_COMMIT=e3ee05f508bd6db1026cf1e7012c2eeb128da410   # scallopmuscle/linux-kernel, kernel-sun60iw2-6.6
if [ ! -f "$MOD_DIR/snd-soc-tlv320aic3x.ko" ] || [ ! -f "$MOD_DIR/snd-soc-tlv320aic3x-i2c.ko" ]; then
	if [ ! -f "$SRC/Makefile" ]; then
		say "kernel source (about 340 MB)"
		tmp="$(mktemp -d)"
		curl -fL --retry 3 -o "$tmp/linux.tar.gz" \
			"https://codeload.github.com/scallopmuscle/linux-kernel/tar.gz/$KERNEL_COMMIT"
		tar -xzf "$tmp/linux.tar.gz" -C "$tmp"
		rm -rf "$SRC"
		mv "$tmp/linux-kernel-$KERNEL_COMMIT" "$SRC"
		rm -rf "$tmp"
	fi
	say "building the TLV320AIC3X codec modules"
	cp "/boot/config-$KV" "$SRC/.config"
	(
		cd "$SRC"
		scripts/config --set-str LOCALVERSION "-sun60iw2" --disable LOCALVERSION_AUTO \
			--module SND_SOC_TLV320AIC3X_I2C
		make -s olddefconfig
		make -s modules_prepare
		[ "$(make -s kernelrelease)" = "$KV" ] || die "kernel source release is not $KV"
		make -s -j"$(nproc)" KBUILD_MODPOST_WARN=1 M=sound/soc/codecs modules
	)
	install -d "$MOD_DIR"
	install -m 0644 "$SRC/sound/soc/codecs/snd-soc-tlv320aic3x.ko" \
		"$SRC/sound/soc/codecs/snd-soc-tlv320aic3x-i2c.ko" "$MOD_DIR/"
	/sbin/depmod -a "$KV"
fi

# ---- device tree overlay ---------------------------------------------------
say "device tree overlay brain"
install -d /boot/overlay-user
install -m 0644 "$HERE/overlay/brain.dts" /boot/overlay-user/brain.dts
dtc -q -@ -I dts -O dtb -o /boot/overlay-user/brain.dtbo "$HERE/overlay/brain.dts"
rm -f /boot/overlay-user/robot-hat.dtbo /boot/overlay-user/robot-hat.dts
ENV=/boot/orangepiEnv.txt
[ -e "$ENV.before-brain" ] || cp -a "$ENV" "$ENV.before-brain"
if grep -q '^user_overlays=' "$ENV"; then
	others=$(sed -n 's/^user_overlays=//p' "$ENV" | tr ' ' '\n' | { grep -v -x -e robot-hat -e brain -e '' || true; } | tr '\n' ' ')
	sed -i "s/^user_overlays=.*/user_overlays=${others}brain/" "$ENV"
else
	echo 'user_overlays=brain' >> "$ENV"
fi
# UART0 is the servo bus, not a console.
if grep -q '^console=' "$ENV"; then
	sed -i 's/^console=.*/console=display/' "$ENV"
else
	echo 'console=display' >> "$ENV"
fi
systemctl mask serial-getty@ttyS0.service >/dev/null
grep -E '^(user_overlays|console)=' "$ENV"

# ---- files -----------------------------------------------------------------
say "files"
R="$HERE/rootfs"
install -d /opt/brain/camera /usr/lib/systemd/system-shutdown
install -m 0644 "$R/opt/brain/battery_guard.py" "$R/opt/brain/i2crdwr.py" /opt/brain/
install -m 0644 "$R/opt/brain/camera/camgrab.c" "$R/opt/brain/camera/imx219_tuning.bin" /opt/brain/camera/
install -m 0755 "$R/usr/local/bin/brain-audio-init" /usr/local/bin/brain-audio-init
install -m 0755 "$R/usr/lib/systemd/system-shutdown/sd-card-power-cycle" /usr/lib/systemd/system-shutdown/
install -m 0644 "$R/etc/asound.conf" /etc/asound.conf
install -m 0644 "$R/etc/udev/rules.d/99-brain.rules" /etc/udev/rules.d/
install -m 0644 "$R/etc/modules-load.d/brain-camera.conf" /etc/modules-load.d/
install -d /etc/polkit-1/rules.d
install -m 0644 "$R/etc/polkit-1/rules.d/50-brain-nm.rules" /etc/polkit-1/rules.d/
UNITS="brain-audio.service brain-battery-guard.service"
for u in $UNITS; do
	install -m 0644 "$R/etc/systemd/system/$u" /etc/systemd/system/
done

say "building camgrab"
gcc -O2 -Wall -o /opt/brain/camera/camgrab.new /opt/brain/camera/camgrab.c \
	-lAWIspApi -lisp -lisp_ini -lvencoder -lMemAdapter -lVE -lcdc_base -lpthread
chmod 0755 /opt/brain/camera/camgrab.new
mv -f /opt/brain/camera/camgrab.new /opt/brain/camera/camgrab
ln -sfn /opt/brain/camera/camgrab /usr/local/bin/camgrab

# ---- boot program ----------------------------------------------------------
# U-Boot waits 1 s for a key on UART0, which is the servo bus: a servo holding the data line low
# reads as a key press and stops the boot at U-Boot's prompt. Make it start Linux without waiting.
# uboot_nowait.py saves the card's boot area in /var/backups/brain-uboot before it writes.
say "boot program"
python3 "$HERE/uboot_nowait.py" --backup-dir /var/backups/brain-uboot \
	|| echo "warning: the boot program was not changed (the reason is above); the rest of the setup goes on"

# ---- groups and services ---------------------------------------------------
say "groups for $USER_NAME"
for g in i2c gpio netdev robot; do getent group "$g" >/dev/null || groupadd --system "$g"; done
usermod -aG dialout,i2c,gpio,audio,video,netdev,robot "$USER_NAME"
# The DuckBuddy services are user units (deploy/brain/units): start them at boot.
loginctl enable-linger "$USER_NAME"

say "services"
udevadm control --reload
udevadm trigger --subsystem-match=tty --subsystem-match=i2c-dev --subsystem-match=gpio || true
systemctl daemon-reload
systemctl try-restart polkit.service 2>/dev/null || true
systemctl enable $UNITS
say "done; reboot to load the overlay and the codec driver:  sudo reboot"
