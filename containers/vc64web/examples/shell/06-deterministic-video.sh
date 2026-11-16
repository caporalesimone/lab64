#!/bin/sh
# Deterministic video (silent, frame by frame, ffmpeg in the PATH). It runs at real time.
set -e; . "$(dirname "$0")/common.sh"
fresh
$C64 --out "$OUT/from-script.mp4" video "$ROOT/examples/scripts/01-hello.txt" '{"every":2,"scale":2}'   # from a script file
$C64 --out "$OUT/from-loop.mp4" video "$ROOT/examples/loops/bot-joy.js"   '{"every":2,"scale":1}'   # from a JS loop
$C64 --out "$OUT/100-frame.mp4" video 100 '{"every":4,"scale":1}'                                  # N frames
