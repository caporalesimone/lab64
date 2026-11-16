#!/bin/sh
# State snapshot and regression. regress check exits with 0 (PASS) or 1 (FAIL).
set -e; . "$(dirname "$0")/common.sh"
fresh
$C64 --compact saveState start
$C64 sendText 'print 1\n'; $C64 runFrames 60
$C64 --compact regress save after    # baseline: component hashes + RAM + screen + cycles
$C64 --compact loadState start       # back exactly to the saved state
$C64 sendText 'print 1\n'; $C64 runFrames 60
$C64 regress check after '{"ignore":["0x0400-0x07E7","0xD800-0xDBE7"]}' && echo "same" || echo "different"
$C64 --out "$OUT/state.bin" saveState file '{"export":true}'   # state to a file
$C64 loadState @"$OUT/state.bin"                               # reloaded from the file
