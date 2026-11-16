#!/bin/sh
# Alternative ROMs: list, load (effective from the next start), back to the defaults.
set -e; . "$(dirname "$0")/common.sh"
$C64 roms kernal                         # list of the ROM files found
$C64 --quiet stop
$C64 rom kernal 251104-04                # SX-64 Kernal
$C64 --compact rom                       # active user ROMs
$C64 --quiet start; $C64 --quiet pause
$C64 --compact info
$C64 --quiet clearRoms; $C64 --quiet stop; $C64 --quiet start   # the defaults again
