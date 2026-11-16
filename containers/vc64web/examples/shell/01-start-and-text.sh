#!/bin/sh
# Starts the emulator, types a BASIC command and reads the screen.
set -e; . "$(dirname "$0")/common.sh"
fresh
$C64 sendText 'print 6*7\n'          # types into the keyboard matrix ("\n" = RETURN)
$C64 runFrames 30                    # lets 30 frames run, then the core stops
$C64 screenText                      # the 25 text rows
$C64 --compact state                 # state: cycles, frozen, disk...
$C64 --out "$OUT/screen.png" screenshot
