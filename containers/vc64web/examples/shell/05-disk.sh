#!/bin/sh
# Test D64 disk: creates it, attaches it (core RUNNING), loads and runs the program.
set -e; . "$(dirname "$0")/common.sh"
python3 "$ROOT/examples/tools/mk_d64.py" "$OUT/test.d64"
$C64 --quiet start; $C64 --quiet resume
$C64 --quiet attach 8 @"$OUT/test.d64" test.d64   # the drive sees the disk only with the core running
$C64 --quiet sleep 1500                            # real time: the drive must read the disk
$C64 --quiet pause
$C64 --compact driveState
$C64 sendText 'load"hello",8\n'; $C64 runFrames 300
$C64 sendText 'run\n';           $C64 runFrames 100
$C64 screenText | head -14
# or from the games folder:  cp "$OUT/test.d64" ../games/ ; C64_GAMES=../games c64 game test.d64
