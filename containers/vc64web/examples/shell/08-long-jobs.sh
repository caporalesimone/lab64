#!/bin/sh
# status and abort: check and interrupt a long job without pkill.
set -e; . "$(dirname "$0")/common.sh"
fresh
$C64 --compact runFrames 200000 &        # long job (≈ 66 minutes of real time)
sleep 3
$C64 --compact status                    # busy, method, progress
$C64 --compact abort                     # interrupts the running job
wait || true                             # the job client got ERROR ABORTED
$C64 --compact status                    # free again
