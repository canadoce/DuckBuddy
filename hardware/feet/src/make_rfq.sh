#!/bin/sh
# Build the RFQ package for the feet: requirement PDFs and the CAD zip, then print SHA-256 of each file.
# Run after feet_parts.py and drawing.py, from anywhere.
set -eu
FEET="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$FEET/rfq"
mkdir -p "$OUT"

typst compile --root "$FEET" "$FEET/src/material-requirements.typ" "$OUT/duckbuddy-feet-material-requirements.pdf"
typst compile --root "$FEET" "$FEET/src/quality-requirements.typ" "$OUT/duckbuddy-feet-quality-requirements.pdf"

# CAD zip: the STEP files only, as the form asks (.stp/.step, several files in one .zip).
# The drawing is uploaded in its own field; STL copies are in STL/ if the bureau asks for them.
# Fixed file times so the zip is the same bytes when the parts do not change.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/duckbuddy-feet"
cp "$FEET"/STEP/*.step "$TMP/duckbuddy-feet/"
find "$TMP/duckbuddy-feet" -exec touch -t 202611070000 {} +
rm -f "$OUT/duckbuddy-feet-cad.zip"
(cd "$TMP" && zip -q -X -9 -r "$OUT/duckbuddy-feet-cad.zip" duckbuddy-feet)

cd "$OUT"
ls -l duckbuddy-feet-*
shasum -a 256 duckbuddy-feet-*
