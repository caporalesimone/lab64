# Common variables of the examples (included with:  . "$(dirname "$0")/common.sh").
# The daemon must be running first:   cd headless && node c64d.js &        (port 7064)
# NODE_PATH: if playwright is installed globally:  export NODE_PATH=$(npm root -g)
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
C64="node $ROOT/headless/c64"
OUT=${OUT:-${TMPDIR:-/tmp}/c64-examples-output}   # outside the package
mkdir -p "$OUT"
# restarts from a C64 just powered on, paused (known state)
fresh() { $C64 --quiet start; $C64 --quiet reset '{"hard":true}'; $C64 --quiet resume; $C64 --quiet ready >/dev/null; $C64 --quiet pause; }
