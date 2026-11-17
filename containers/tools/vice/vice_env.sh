# Shell environment for VICE in Lab64 (13/11, moved from the game on 14/11). Copyright (c) 2026 - Simone Caporale
# The same options as containers/tools/py/vicemon.py (keep them equal). Use in a bash script run in lab64-tools:  eval "$(lab64 vice-env)"   (or . /lab64/containers/tools/vice/vice_env.sh)
#   R, RD  ROM folders: $C64_ROMS/vice-roms/C64 and .../DRIVES ($C64_ROMS=/opt/roms in the image)
#   VROM   x64sc options: factory settings (-default: no user configuration) and ALL the ROMs of Lab64 roms/
#          (Kernal, Basic, chargen and the drives): VICE reads nothing from its data folder or from /usr/share
#   XRUN   a virtual display per VICE (xvfb-run), or the shared viewer screen with C64_VIEW=1 and DISPLAY
LAB64="${LAB64:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
R="${C64_ROMS:-/opt/roms}/vice-roms/C64"; RD="${C64_ROMS:-/opt/roms}/vice-roms/DRIVES"      # the copy inside the image
VROM="-default -kernal $R/kernal-901227-03.bin -basic $R/basic-901226-01.bin -chargen $R/chargen-901225-01.bin -dos1541 $RD/dos1541-325302-01+901229-05.bin -dos1541II $RD/dos1541ii-251968-03.bin -dos1570 $RD/dos1570-315090-01.bin -dos1571 $RD/dos1571-310654-05.bin"
if [ "${C64_VIEW:-0}" = 1 ] && [ -n "${DISPLAY:-}" ]; then XRUN=""; else XRUN="xvfb-run -a"; fi
