#!/bin/sh
# Determinism regression test (API 24). A target that READS the inputs: a program at $C000 that samples $DC00
# (joystick 2 + keyboard columns) into a histogram at $C100-$C2FF, with the KERNAL active (keyboard buffer at $0277).
# Bot: examples/loops/bot-input.js (held and timed joystick, held and timed key, variable CPU load).
# Runs N times normally + 2 times with forced repeats (_forceRetry, internal test option): all the hashes must match,
# and the histogram must show that the inputs arrived. Usage: 11-determinism.sh [N=5] [STEPS=300]. Exit 1 on failure.
set -e; . "$(dirname "$0")/common.sh"
N=${1:-5}; STEPS=${2:-300}; FR=$((STEPS*2))
fresh
$C64 --quiet poke 0xC000 '[173,0,220,41,31,168,185,0,193,24,105,1,153,0,193,208,239,185,0,194,24,105,1,153,0,194,76,0,192]'
$C64 --quiet setRegs '{"pc":"0xC000"}'; $C64 --quiet runFrames 2; $C64 --quiet saveState det0
BOT=$(cat "$ROOT/examples/loops/bot-input.js")
first=""; fail=0
one() {   # $1 = label, $2 = runLoop options
  $C64 --quiet loadState det0
  r=$($C64 --compact runLoop "$BOT" "$2")
  ex=$(echo "$r" | sed -n 's/.*"exact":\([a-z]*\).*/\1/p'); nr=$(echo "$r" | sed -n 's/.*"retriesTotal":\([0-9]*\).*/\1/p')
  h=$($C64 --compact stateHash | sed -n 's/^{"hash":"\([0-9a-f]*\)".*/\1/p')
  echo "$1: hash=$h exact=$ex repeats=$nr"
  [ -z "$first" ] && first=$h
  [ "$h" = "$first" ] && [ "$ex" = "true" ] || fail=1
}
i=1; while [ $i -le $N ]; do one "run $i" "{\"frames\":$FR,\"every\":2}"; i=$((i+1)); done
one "forced repeat at every step" "{\"frames\":$FR,\"every\":2,\"_forceRetry\":1}"
one "2 repeats every 3 steps" "{\"frames\":$FR,\"every\":2,\"_forceRetry\":2,\"_forceEvery\":3}"
vals=$($C64 --compact peek 0xC100 32 | tr -d '[]' | tr ',' '\n' | grep -vc '^0$' || true)
echo "different \$DC00 values seen: $vals (expected > 2: the inputs reach the target)"
[ "$vals" -gt 2 ] || fail=1
[ $fail -eq 0 ] && echo "OK: identical runs" || { echo "ERROR: different runs or inputs not arrived"; exit 1; }
