# Memory maps: how to (`lab64 map`)

Copyright © 2026 - Simone Caporale

The automatic memory and disk map and the comments in the sources that complete it. Disks with several programs that replace each
other in memory are in [memory-maps-programs.md](memory-maps-programs.md); the `memmap.json` metrics feed the viewer
([viewer.md](viewer.md), [manifest.md](manifest.md)).

`lab64 map` reads the 64tass listings (`-L`) and labels (`-l`) of `out/work/`, the PRGs and the `.d64`, and writes
`out/work/memory-map/index.html` (+ `memmap.json`). With nothing else it already knows every byte of code and data, the variables
of `.virtual` blocks, the addresses used by the instructions, where every disk file is loaded. What it cannot know, the project
says with **comments in the sources** (no space after `;`, anywhere in a source file of the module, best next to the constant that
defines the area). Five steps, each optional; a worked example for a small game with a loader, an intro and the game follows.

**Addresses in the comments**: a label or `$hex`; `START..END` = from START to END excluded; `START` alone = up to its pair
`START_end` (suffixes `C64_MAP_PAIRS`); `START+N` = N bytes (decimal or `$hex`); in `START..END` both ends may be `LABEL+N` or
`LABEL-N`.

## 1. Memory the static analysis cannot see: `;@map`

A buffer written through a pointer, data copied there at start-up, a screen, sprites: the area counts as used.
```
SCREEN  = $0400
BUFFER  = $c000
;@map SCREEN..$07e8 "text screen"
;@map BUFFER+1024 "decompression buffer of the levels"
sprites_src .binary "sprites.bin"              ; in the PRG, copied to $2000 at start-up
sprites_src_end
;@map sprites_src "sprite shapes in the PRG, copied to $2000 by init" free-after=start
;@map $2000..$2400 "sprite shapes (copied by init)"
```
`free-after=start` = the area is needed only until then: the page adds "free after start-up" (metric `ram_free_after_start_<program>`).

## 2. Where new code and data can go: `;@free`

What each free area can hold: `use=code` (any code and data), `use=code-io-off`
(code that runs with the I/O switched off, `$01=$34`: the RAM under `$D000-$DFFF`; or data), `use=data` (data only: a VIC bank hole,
RAM under a ROM, sprite slots). The map **checks** them: an area that is not free (any more) is a warning, an error with
`lab64 map --strict` (use it in the build: the annotation follows the code).
```
code_end
;@free code_end..$9000 "room for more code (guard: .cerror code_end > $9000)" use=code
;@free gen_end..$e000 "under the I/O after the generator" use=code-io-off
;@free $3e00..$4000 "sprite slots 248-255, unused" use=data
```
The page lists them ("Free memory, by use") with the total per use; `memmap.json`: `free_notes`, `free_by_use`. Notes in `$0000-$03FF` are checked too (step 5).
A note of the main module of another program is shown only in that program.

## 3. What is in memory together: `;@scenario` (modules and disk files)

Overlays and data files replace each other at the same
addresses; a scenario lists what is there at one time, so the page can draw it (one 64 KB strip per scenario: who is where, what is
free) and find conflicts. Items: listing names (modules) and disk file names with sh wildcards; **the files of one pattern are
alternatives** (`level?` = one level at a time); `a|b*` makes one group of two patterns (alternatives too). Without file names a
scenario has every data file of the program. An area that exists only in some scenarios: `scenario=` on its `;@map`.
```
;@scenario title: game titlepic music1                ; the title screen
;@scenario play: game hud level? music2|music3         ; a level, one of two tunes
;@scenario save: game savecode save-??                ; saving: the save image over the level cache
;@map $c000..$c400 "unpacked level map" scenario=play,save
```
Conflict = two items of a scenario at the same addresses (two modules, two patterns, a file over a module's code or variables).
**Areas of one scenario are checked against each other**: two `;@map` areas that carry `scenario=` and share a scenario name
must not overlap; if they do, `lab64 map` prints `WARNING ...: area overlap in scenario play: $c000 "buf A" and $c080 "buf B"`
and `--strict` exits 1. Areas without `scenario=` are not compared (they belong to every scenario, or to none).
```
;@map $c000..$c100 "unpacked level map" scenario=play
;@map $c080..$c200 "save buffer" scenario=play         ; WARNING: overlaps the level map in scenario play
;@map $c080..$c200 "save buffer" scenario=save         ; fine: another scenario
```

## 4. Record layouts: `layout`

On a `;@map` of a block of variables (a saved hero, a level state), `layout` adds a table of its
fields: every label inside the area, its offset and size (up to the next label) and the comment of the line that defines it.
Comment the fields once: the table follows the code.
```
;@map hero..hero_end "the hero, saved as is in the file SAVE" layout
        .virtual $9500
hero
h_level .byte ?          ; level 1..99
h_gold  .word ?          ; gold (16 bit)
h_name  .fill 12         ; name, screen codes
hero_end
        .endv
```

## 5. Pages 0-3, `$0000-$03FF`

Every map page has a section "Pages 0-3": a compact table of the merged ranges of zero page,
stack and pages 2-3 that the sources show: for each range what it is (variable, bytes placed there, address used by the code with
its `r w x` flags, `;@map` area), the labels that point there with the source `file:line`, the module, and, with probe dumps, whether
it was written in VICE. Fixed facts: `$00-$01` (6510 port) and the stack page `$0100-$01FF`. Nothing else is invented: KERNAL and
BASIC work areas appear only if the program's code uses them, so an unlisted byte is *unknown*, not free. The probe covers only
`$033C-$03FB` (the rest is in use by BASIC and the KERNAL at READY.). `;@free` notes in this range are **checked** like the
ones above `$0400`: a label of the program's code, a variable, an annotated area, `$00-$01` or a probe write there makes the note
"not free" (warning, error with `--strict`); the stack page is not checked. `memmap.json`: `low_pages`.
```
;@free $0334..$033c "free: the tape buffer start, never used by this program" use=data   ; OK
;@free $02..$08 "free zero page"            ; WARNING if a label or instruction of the code uses $02-$07
```
A name is listed only with evidence that it is an address: defined on a line of the listing at that address (`.virtual`, `.byte ?`, `.fill`, data placed with `*=` / `.logical`), or the base symbol of the operand of an instruction that is not immediate (`lda sym`, `sta (sym),y`, `inc sym+K`), or in `.word` / `.addr`. Constants used only in immediates (`lda #SYM`), tables of bytes, `.cerror` or arithmetic are not listed; a constant used as a real operand that is not an address would be (rare).

## Several programs and the run-time probe

**Several programs on one disk**: `C64_MAP_PROGRAM_<NAME>` in `lab64.env`, see [memory-maps-programs.md](memory-maps-programs.md); `C64_MAP_METRICS="game start"` publishes
the metrics (`ram_free_static_<name>`, `ram_free_after_start_<name>`, `ram_never_written_<name>`) of those programs only (empty or
unset = all of them; with many programs the viewer would show many cards). **Memory really written** while the tests
run: `C64_MEMPROBE=1 lab64 test all`, then `lab64 map` (section "Measured in VICE"); every program needs some test session that
ends while it is in memory, or its map has no probe data.

**A probe session through several programs.** A session that goes loader -> game would count all its writes in the program it
ends in. Call `v.probe_checkpoint()` (no-op when the probe is off) **just before the C64 switches program** (before the key that
makes a loader start the game, before the LOAD of the next file): it saves a RAM dump in the middle of the session (same name and
meta as the dump of `close()`, plus the session id and a sequence number). `lab64 map` attributes each dump to the program that is
in RAM at that moment and, within a session, counts as *written* in each later dump only the bytes that
**differ from the previous dump of the session** (this includes the bytes that were still the fill pattern before and are not
now). Limit: a byte rewritten with the **same value** as in the previous dump is missed. Sessions without checkpoints: their one dump
is compared with the fill pattern. The machine is left as it was (stopped, or running after a `resume()`);
the monitor writes of the test count as written.
```
v = Vice(DISK)
run_loader_menu(v)               # test code: the loader is in RAM
v.probe_checkpoint()                # just before the switch: this dump is the loader's
press_key_to_start_the_game(v)      # the game loads and starts; the test runs
v.close()                           # last dump: the game's, only what changed since the checkpoint
```

## Worked example

A loader, an intro, the game with levels, music and saves:
```
# lab64.env
C64_MAP_PROGRAM_LOADER="loader"
C64_MAP_PROGRAM_INTRO="intro introdata"
C64_MAP_PROGRAM_GAME="game level? music* savecode save-??"
```
```
; src/game.asm (module "game")
;@map $0400..$07e8 "screen"
;@map $c000..$c900 "level map, unpacked from the file LEVELn" scenario=play
;@free code_end..$8000 "free for code" use=code
;@free $e000+$400 "under the KERNAL: data only" use=data
;@scenario play: game level? music?
;@scenario save: game savecode save-??
;@map hero..hero_end "hero record (file SAVE-nn)" layout
```
`lab64 map --strict` -> `index.html` (the three programs side by side), `program-game.html` (annotated areas, free memory by use,
the fields of `hero`, the strips of `play` and `save`).
