#!/bin/sh
# Checks that the Commodore ROM files listed in roms/roms.md are present with the right SHA-256 (16/11, owner's rule).
# Copyright (c) 2026 - Simone Caporale
#   check_roms.sh            exit 0 if all is right, 1 (with the list of what is wrong) otherwise
# The ROMs are NOT in the repository (.gitignore): the user copies them into roms/vice-roms/{C64,DRIVES}, the ONLY place, BEFORE
# building the images. That folder is read only while an image is built (docker build context "roms"); the images contain the
# ROMs and are for the user's own use, never to be distributed. Called by build-images.sh (the build stops) and by check_env.sh.
TC=$(cd "$(dirname "$0")/.." && pwd)
command -v sha256sum >/dev/null || { echo "sha256sum not found: cannot check the ROMs" >&2; exit 1; }
BAD=0; N=0
for line in $(sed -n 's/^| `\(vice-roms\/[^`]*\)` | [0-9]* | `\([0-9a-f]\{64\}\)` .*/\1:\2/p' "$TC/roms/roms.md"); do
    f=${line%%:*}; s=${line#*:}; N=$((N + 1))
    for d in "$TC/roms"; do
        if [ ! -f "$d/$f" ]; then echo "  missing:      $d/$f" >&2; BAD=1
        elif [ "$(sha256sum "$d/$f" | cut -c1-64)" != "$s" ]; then echo "  wrong SHA-256: $d/$f (expected $s)" >&2; BAD=1; fi
    done
done
if [ $BAD = 1 ]; then
    echo "The Commodore ROMs are not in the repository. Copy the $N files listed in roms/roms.md (exact names, SHA-256 in the table)" >&2
    echo "into roms/vice-roms/C64 and roms/vice-roms/DRIVES (the only place), then run again." >&2
    exit 1
fi
echo "$N Commodore ROMs present in roms/, SHA-256 as in roms/roms.md"
