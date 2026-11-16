#!/bin/sh
# Debug: registers, disassembly, single instruction, call, breakpoint, trace, RAM snapshot.
set -e; . "$(dirname "$0")/common.sh"
fresh
$C64 --compact regs
$C64 --compact disasm 0xFFFC 3       # the core disassembler
$C64 --compact step 3                # 3 instructions
$C64 --compact trace '{"max":5,"last":3}'    # ALWAYS set max (default 20000 instructions = minutes)
$C64 ramSnap before
$C64 poke 0xC000 7
$C64 --compact ramDiff before null   # -> one changed address
$C64 --compact call 0xFFD2 '{"a":65}'        # JSR CHROUT with A=65: prints 'A'
$C64 breakpoint 0xFFD2; $C64 breakpoints; $C64 clearBreakpoints
