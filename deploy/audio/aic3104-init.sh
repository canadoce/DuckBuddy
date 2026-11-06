#!/bin/bash
# TLV320AIC3104 mixer setup. The kernel codec driver handles PLL / DAC / line
# output configuration via the devicetree overlay; this script only applies the
# default mixer levels and microphone routing on top.
#
# Environment (set by the systemd unit):
#   AIC3104_I2C_BUS    I2C bus number of the codec for the presence check, or
#                      "auto" to take it from the bound codec device in sysfs.
#   AIC3104_MIC_ROUTE  line1-diff  HAT R3E: J7/J8 electret mics, differential on LINE1L/LINE1R
#                      line1-se    Robot HAT E1: J2/J9 electret mics, single-ended on LINE1L/LINE1R
#                      mic2r-both  Robot HAT E1: the onboard MEMS mic (MIC2R) on both channels
#                      (unset)     the onboard MEMS mic on the right channel only (Radxa setup)
#   AIC3104_LOP_GAIN   line output stage gain in dB, 0..9 (default 9)

sleep 2

if [ "${AIC3104_I2C_BUS:-}" = auto ]; then
    AIC3104_I2C_BUS=
    for dev in /sys/bus/i2c/devices/[0-9]*-0018; do
        [ -e "$dev/driver" ] || continue
        case "$(basename "$(readlink -f "$dev/driver")")" in
            tlv320aic3x*) AIC3104_I2C_BUS=$(basename "$dev" | cut -d- -f1); break ;;
        esac
    done
    if [ -z "$AIC3104_I2C_BUS" ]; then
        echo "TLV320AIC3104: no codec device bound at 0x18; skipping the presence check"
    fi
fi
lop_gain=${AIC3104_LOP_GAIN:-9}

# The A733 overlay owns AMP_SD through gpio-leds. Keep the analog amplifier
# muted until both the physical codec and its mixer path have been verified.
amp_enable=/sys/class/leds/microduck-amp-enable/brightness
if [ -w "$amp_enable" ]; then
    printf '0\n' > "$amp_enable"
fi

# The ALSA card may not be registered immediately after boot — retry a few
# times if amixer can't find it yet. The window is generous because on the
# Radxa the card probe is deferred until the DKMS codec module autoloads.
for i in $(seq 1 15); do
    if amixer -c aic3104 info >/dev/null 2>&1; then
        # ASoC can register a logical card even when an unidentifiable codec is
        # absent from the physical I2C bus. On A733, make one harmless read of
        # the page-select register before enabling the amplifier. -f is needed
        # because the DT-created client is already owned by the codec driver.
        # While the card is idle (bias Off) the driver holds the codec in
        # reset (HAT R3E: via PB0), so it NACKs every read; hold a short silent
        # capture stream open so the codec is powered and out of reset during
        # the read.
        if [ -n "${AIC3104_I2C_BUS:-}" ] && command -v i2ctransfer >/dev/null 2>&1; then
            rec_pid=
            if command -v arecord >/dev/null 2>&1; then
                arecord -q -D hw:aic3104,0 -f S16_LE -r 48000 -c 2 -d 3 /dev/null >/dev/null 2>&1 &
                rec_pid=$!
            fi
            detected=
            for _ in $(seq 1 15); do
                sleep 0.2
                if i2ctransfer -f -y "$AIC3104_I2C_BUS" \
                    w1@0x18 0x00 r1 >/dev/null 2>&1; then
                    detected=1
                    break
                fi
            done
            if [ -n "$rec_pid" ]; then
                kill "$rec_pid" 2>/dev/null
                wait "$rec_pid" 2>/dev/null
            fi
            if [ -z "$detected" ]; then
                echo "TLV320AIC3104 not detected on I2C${AIC3104_I2C_BUS}; amplifier kept off"
                exit 0
            fi
        fi
        # Speaker path: the speaker amp hangs off the codec's line outputs
        # (LEFT_LOP/RIGHT_LOP). 'Line Playback Switch' is the LOP output-stage
        # MUTE (not a line-in bypass — this script used to set it off, which
        # silences the robot; the Pi only worked because alsa-restore happened
        # to re-apply an old saved state with it on). 'Line Playback Volume'
        # is the LOP stage gain, 0..9 dB (AIC3104_LOP_GAIN). The Robot HAT E1's
        # PAM8406 clips at +9 dB with a full-scale signal, so its unit sets 0.
        amixer -c aic3104 cset name='PCM Playback Volume'      127,127 >/dev/null
        amixer -c aic3104 cset name='Line DAC Playback Volume' 118,118 >/dev/null
        amixer -c aic3104 cset name='Line Playback Switch'     on,on   >/dev/null
        amixer -c aic3104 cset name='Line Playback Volume'     "$lop_gain,$lop_gain" >/dev/null

        simple_controls=$(amixer -c aic3104 scontrols)
        if [ "${AIC3104_MIC_ROUTE:-}" = line1-se ]; then
            # Robot HAT E1: J2 → LINE1LP (pin 10) and J9 → LINE1RP (pin 12),
            # single-ended, biased on the HAT through R42 and R22/R23.
            # Left channel = J2, right = J9.
            amixer -c aic3104 cset name='Left Line1L Mux'  single-ended >/dev/null
            amixer -c aic3104 cset name='Right Line1R Mux' single-ended >/dev/null
            amixer -c aic3104 sset 'Left PGA Mixer Line1L'  on  >/dev/null
            amixer -c aic3104 sset 'Right PGA Mixer Line1R' on  >/dev/null
            amixer -c aic3104 sset 'Left PGA Mixer Line1R'  off >/dev/null
            amixer -c aic3104 sset 'Right PGA Mixer Line1L' off >/dev/null
            for input in Mic2L Mic2R; do
                amixer -c aic3104 sset "Left PGA Mixer $input"  off >/dev/null
                amixer -c aic3104 sset "Right PGA Mixer $input" off >/dev/null
            done
        elif [ "${AIC3104_MIC_ROUTE:-}" = mic2r-both ]; then
            # Robot HAT E1: the onboard MEMS mic (MK1) is on MIC2R (pin 16);
            # MIC2L is tied to ground. Send MIC2R to both PGAs so a mono
            # capture (which averages left and right) gets the full level.
            amixer -c aic3104 sset 'Left PGA Mixer Mic2R'  on  >/dev/null
            amixer -c aic3104 sset 'Right PGA Mixer Mic2R' on  >/dev/null
            amixer -c aic3104 sset 'Left PGA Mixer Mic2L'  off >/dev/null
            amixer -c aic3104 sset 'Right PGA Mixer Mic2L' off >/dev/null
            for input in Line1L Line1R; do
                amixer -c aic3104 sset "Left PGA Mixer $input"  off >/dev/null
                amixer -c aic3104 sset "Right PGA Mixer $input" off >/dev/null
            done
        elif [ "${AIC3104_MIC_ROUTE:-}" = line1-diff ]; then
            # HAT R3E on the A733: J7 → LINE1L (pins 10/11) and J8 → LINE1R
            # (pins 12/13), each wired as a differential pair, biased from
            # MICBIAS through R13/R19. Left channel = J7, right = J8.
            amixer -c aic3104 cset name='Left Line1L Mux'  differential >/dev/null
            amixer -c aic3104 cset name='Right Line1R Mux' differential >/dev/null
            amixer -c aic3104 sset 'Left PGA Mixer Line1L'  on  >/dev/null
            amixer -c aic3104 sset 'Right PGA Mixer Line1R' on  >/dev/null
            amixer -c aic3104 sset 'Left PGA Mixer Line1R'  off >/dev/null
            amixer -c aic3104 sset 'Right PGA Mixer Line1L' off >/dev/null
            for input in Mic2L Mic2R; do
                amixer -c aic3104 sset "Left PGA Mixer $input"  off >/dev/null
                amixer -c aic3104 sset "Right PGA Mixer $input" off >/dev/null
            done
        else
            # Onboard microphone: route Mic3R → Right PGA only
            # The model-specific compatible exposes Mic2L/R on an AIC3104. Older
            # Radxa overlays used the generic AIC3X model and exposed Mic3L/R, so
            # retain that spelling as a compatibility fallback.
            if printf '%s
' "$simple_controls" | grep -Fq "'Right PGA Mixer Mic2R'"; then
                mic_pair=Mic2
            else
                mic_pair=Mic3
            fi

            amixer -c aic3104 sset "Right PGA Mixer ${mic_pair}R" on  >/dev/null
            amixer -c aic3104 sset "Left PGA Mixer ${mic_pair}R"  off >/dev/null
            amixer -c aic3104 sset "Left PGA Mixer ${mic_pair}L"  off >/dev/null
            amixer -c aic3104 sset "Right PGA Mixer ${mic_pair}L" off >/dev/null
            amixer -c aic3104 sset 'Right PGA Mixer Line1R' off >/dev/null
            amixer -c aic3104 sset 'Right PGA Mixer Line1L' off >/dev/null
            amixer -c aic3104 sset 'Left PGA Mixer Line1R'  off >/dev/null
            amixer -c aic3104 sset 'Left PGA Mixer Line1L'  off >/dev/null
        fi
        # LINE2 is absent on the AIC3104 but exists on the generic AIC3X model.
        if printf '%s
' "$simple_controls" | grep -Fq "'Right PGA Mixer Line2R'"; then
            amixer -c aic3104 sset 'Right PGA Mixer Line2R' off >/dev/null
        fi
        # Capture path: enable PGA capture switch and set gain (0-119)
        amixer -c aic3104 cset name='PGA Capture Switch' on,on >/dev/null
        amixer -c aic3104 cset name='PGA Capture Volume' 60,60 >/dev/null

        # HAT R3E: PB3 is represented by the A733 overlay as a gpio-led so the
        # kernel keeps ownership after this oneshot exits. Enable the analog amp
        # only after the codec output path has been configured. The Robot HAT
        # E1's amp is always on and has no such LED.
        if [ -w "$amp_enable" ]; then
            printf '1\n' > "$amp_enable"
        fi

        echo "TLV320AIC3104 mixer levels and amplifier set"
        break
    fi
    sleep 1
done
