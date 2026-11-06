#!/bin/sh
# Install the TLV320AIC3104 codec modules, the head HAT's DT overlay and the
# mixer service on an Orange Pi Zero 3W (A733).
#
#   sudo sh install-aic3104-a733.sh [--hat robothat-e1|r3e] linux-sun60iw2-6.6.98.tar.gz
#
#   --hat robothat-e1  Robot HAT E1 (default): codec on TWI0, servo bus on UART0 (/dev/ttyS0);
#                      also moves the serial console off UART0
#   --hat r3e          the upstream HAT: codec on TWI2, servo bus on UART7
set -eu

KERNEL_VERSION="$(uname -r)"
EXPECTED_KERNEL="6.6.98-sun60iw2"
SOURCE_DIR="/usr/src/linux-sun60iw2-6.6.98"
OVERLAY_NAME="microduck-aic3104"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

die() {
	echo "error: $*" >&2
	exit 1
}

[ "$(id -u)" -eq 0 ] || die "run this installer with sudo"
[ -r /etc/orangepi-release ] || die "/etc/orangepi-release not found"
grep -qx 'BOARD=orangepizero3w' /etc/orangepi-release || \
	die "this installer only supports Orange Pi Zero 3W"
grep -qx 'BOARDFAMILY=sun60iw2' /etc/orangepi-release || \
	die "this installer only supports the A733/sun60iw2 board family"
[ "$KERNEL_VERSION" = "$EXPECTED_KERNEL" ] || \
	die "expected $EXPECTED_KERNEL, running $KERNEL_VERSION"
HAT=robothat-e1
if [ "${1:-}" = --hat ]; then
	[ "$#" -ge 2 ] || die "--hat needs a value: robothat-e1 or r3e"
	HAT=$2
	shift 2
fi
case "$HAT" in
	r3e)
		OVERLAY_SOURCE=aic3104-a733.dts
		SERVICE_SOURCE=aic3104-a733.service
		;;
	robothat-e1)
		OVERLAY_SOURCE=aic3104-a733-robothat.dts
		SERVICE_SOURCE=aic3104-a733-robothat.service
		;;
	*) die "unknown HAT: $HAT (robothat-e1 or r3e)" ;;
esac
[ "$#" -eq 1 ] || die "usage: sudo $0 [--hat robothat-e1|r3e] /path/to/linux-sun60iw2-6.6.98.tar.gz"

SOURCE_ARCHIVE=$1
[ -f "$SOURCE_ARCHIVE" ] || die "kernel source archive not found: $SOURCE_ARCHIVE"

for command in tar make gcc dtc depmod modprobe systemctl; do
	command -v "$command" >/dev/null 2>&1 || die "missing command: $command"
done

if [ ! -f "$SOURCE_DIR/Makefile" ]; then
	echo "Extracting the local kernel snapshot to $SOURCE_DIR"
	tar -xzf "$SOURCE_ARCHIVE" -C /usr/src
fi
[ -f "$SOURCE_DIR/Makefile" ] || die "archive did not create $SOURCE_DIR"

echo "Preparing the A733 kernel tree"
cp "/boot/config-$KERNEL_VERSION" "$SOURCE_DIR/.config"
cd "$SOURCE_DIR"
scripts/config --set-str LOCALVERSION "-sun60iw2"
scripts/config --disable LOCALVERSION_AUTO
scripts/config --module SND_SOC_TLV320AIC3X_I2C
make olddefconfig
make modules_prepare

BUILT_RELEASE=$(make -s kernelrelease)
[ "$BUILT_RELEASE" = "$KERNEL_VERSION" ] || \
	die "prepared tree has release $BUILT_RELEASE, expected $KERNEL_VERSION"

echo "Building the TLV320AIC3X core and I2C modules"
make -j"$(getconf _NPROCESSORS_ONLN)" \
	KBUILD_MODPOST_WARN=1 M=sound/soc/codecs modules

CORE_MODULE="sound/soc/codecs/snd-soc-tlv320aic3x.ko"
I2C_MODULE="sound/soc/codecs/snd-soc-tlv320aic3x-i2c.ko"
[ -f "$CORE_MODULE" ] || die "codec core module was not built"
[ -f "$I2C_MODULE" ] || die "codec I2C module was not built"

MODULE_DIR="/lib/modules/$KERNEL_VERSION/extra"
install -d -m 0755 "$MODULE_DIR"
install -m 0644 "$CORE_MODULE" "$MODULE_DIR/"
install -m 0644 "$I2C_MODULE" "$MODULE_DIR/"
depmod -a "$KERNEL_VERSION"

OVERLAY_DIR="/boot/dtb-$KERNEL_VERSION/allwinner/overlay"
[ -d "$OVERLAY_DIR" ] || die "overlay directory not found: $OVERLAY_DIR"
DTBO=$(mktemp)
trap 'rm -f "$DTBO"' EXIT HUP INT TERM
dtc -@ -I dts -O dtb -o "$DTBO" "$SCRIPT_DIR/$OVERLAY_SOURCE"
install -m 0644 "$DTBO" "$OVERLAY_DIR/sun60i-a733-$OVERLAY_NAME.dtbo"

ENV_FILE=/boot/orangepiEnv.txt
[ -f "$ENV_FILE" ] || die "$ENV_FILE not found"
cp -a "$ENV_FILE" "$ENV_FILE.pre-aic3104-$(date +%Y%m%d-%H%M%S)"

if grep -q '^overlays=' "$ENV_FILE"; then
	OVERLAYS=$(sed -n 's/^overlays=//p' "$ENV_FILE" | tail -n 1)
	case " $OVERLAYS " in
		*" $OVERLAY_NAME "*) ;;
		*) sed -i "s/^overlays=.*/overlays=$OVERLAYS $OVERLAY_NAME/" "$ENV_FILE" ;;
	esac
else
	printf '\noverlays=%s\n' "$OVERLAY_NAME" >> "$ENV_FILE"
fi

install -m 0755 "$SCRIPT_DIR/aic3104-init.sh" /usr/local/bin/aic3104-init.sh
# A checkout prepared on Windows may carry CRLF even though the target is
# Linux. Strip the carriage return so the shebang remains executable.
sed -i 's/\r$//' /usr/local/bin/aic3104-init.sh
install -m 0644 "$SCRIPT_DIR/$SERVICE_SOURCE" \
	/etc/systemd/system/aic3104-a733.service
systemctl daemon-reload
systemctl enable aic3104-a733.service

if [ "$HAT" = robothat-e1 ]; then
	# The Robot HAT E1 has the servo bus on header pins 8/10, which are UART0,
	# the board's debug console. Take the kernel console and the login getty
	# off it, so neither writes to the servos. U-Boot still prints its boot
	# messages there at 115200 baud before Linux starts.
	if grep -q '^console=' "$ENV_FILE"; then
		sed -i 's/^console=.*/console=display/' "$ENV_FILE"
	else
		printf 'console=display\n' >> "$ENV_FILE"
	fi
	systemctl mask serial-getty@ttyS0.service
	echo "Serial console moved off UART0 (console=display, serial-getty@ttyS0 masked)."
fi

# Loading the modules is safe without the HAT. The codec will only bind after
# the overlay exists and an AIC3104 acknowledges address 0x18.
modprobe snd-soc-tlv320aic3x
modprobe snd-soc-tlv320aic3x-i2c

echo "Installed AIC3104 modules and the $OVERLAY_NAME overlay for the $HAT HAT."
if [ "$HAT" = robothat-e1 ]; then
	echo "Reboot, then check: aplay -l; ls /sys/bus/i2c/devices/*-0018; dmesg | grep -Ei 'aic3|sound-mach'"
	echo "Set [bus] port = \"/dev/ttyS0\" in /etc/robot/robotd.toml."
else
	echo "Reboot, then check: aplay -l; i2cdetect -y 2; dmesg | grep -Ei 'aic3|sound-mach'"
fi
