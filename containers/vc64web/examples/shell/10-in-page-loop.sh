#!/bin/sh
# runLoop: logic inside the page, no HTTP call per step (≈ real time).
set -e; . "$(dirname "$0")/common.sh"
fresh
$C64 --compact runLoop "$(cat "$ROOT/examples/loops/count-memory.js")" '{"frames":200}'
$C64 --compact runLoop "$(cat "$ROOT/examples/loops/bot-joy.js")" '{"frames":300,"every":2}'
