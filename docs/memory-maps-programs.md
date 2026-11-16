# Memory map of several programs (`lab64 map`)

Copyright © 2026 - Simone Caporale

For a disk that holds several programs. The annotations and the basics of the map are in [memory-maps.md](memory-maps.md).

A disk often holds programs that **replace each other** in memory: a loader with a menu, an intro, the game with its overlays and
data, a jukebox. One picture of all of them adds up memory that is never used at the same time:
its free RAM is meaningless. A project with such a disk declares its **programs**; each program gets its own map.

## Design

Model: program > scenario > module.
- A **program** = the disk files that can be in memory at the same time: the **main file** (the one that runs) and the files it
  loads (overlays, data, saves). Programs never share the machine; each has its own map and its own free RAM. A **scenario**
  (`;@scenario`, `C64_MAP_SCENARIOS`) is a set of modules in memory together *inside* a program. A **module** is
  a 64tass listing linked to a disk file.
- What a program contains is declared, once, in `lab64.env`. It is a statement about the disk (which files go together), not about
  one source: files with no listing (data, saves, a program built without `-L`) have no source to annotate, so there is no
  `;@program` annotation and no second way to say it. Grouping is not guessed: the file names a loader passes are loader-specific
  and often built at run time (`"GFX" + digit`), and "has a listing" or "loads at $0801" says nothing about which files go
  together. One explicit line per program is shorter than any heuristic and never wrong in silence.
- Found **automatically**, at no cost: the modules (listing <-> disk file), the load range of every disk file, which
  module belongs to which program (through its disk files), and **which program a VICE session of the probe ended in**: the dump
  holds the whole RAM, so the program whose main file is found in it (at least 60% of the bytes of one of its modules, as
  listed, or of the file at its load address when it has no listing) gets the dump. Measured on a real project: 97-100% for the
  right program, at most 37% for the others.
- **No "shared resident" concept**: a file that two programs load is simply listed in both (shown as "also in other programs");
  memory that one program leaves to the next with no file of its own (a resident loader, a trampoline) is a `;@map` annotation
  with `$hex` addresses in a source of the program that relies on it.
- **No declaration**: one map of every module and file, `index.html` + `memmap.json` (`schema` 1).
  With a declaration, every disk file must be in some program: those that are not are listed on the index ("Files in no
  program") and printed as a warning, never silently mapped.

## What a project writes

`lab64.env`, one line per program, the order is the order of the index:
```
C64_MAP_PROGRAM_LOADER="loader"                       # name = what follows C64_MAP_PROGRAM_ (lowercase in the pages)
C64_MAP_PROGRAM_INTRO="intro introdata title"
C64_MAP_PROGRAM_GAME="game level? gfx* music* save-*" # the first name is the main file: a plain name
C64_MAP_PROGRAM_JUKEBOX="jukebox music*"              # music* is in two programs: allowed
```
Names are disk file names (case-insensitive; without a disk, listing names), with sh wildcards `*` `?` `[..]`. The main file must
be a plain name that exists (else the map stops with an error); another name that matches nothing is a warning. A module is in a
program when one of its disk files is (a listing whose output became `menu1..3` is in the program that lists `menu1`).
A scenario is shown in every program that has one of its modules (its other modules are reported there as not in the program);
annotations belong to the module whose source holds them.

## What it gets

In `out/work/memory-map/`:
- `index.html`: one row per program (main file and where it sits, files, modules, free RAM static / after start-up / never
  written in VICE, scenarios), all the programs side by side on one 64 KB axis, "To check" (warnings, files in no program, probe
  sessions in no program), the declaration, the disk, other listings and other pages of the folder.
- `program-<name>.html`: the page of a single program: its modules and files, annotations, scenarios, the probe dumps
  that ended in it; a link back to the index. Pages of programs no longer declared are deleted.
- `memmap.json` `schema` 2: `programs` (per program: `name`, `main`, `files`, `page` and the fields of schema 1: `free_bytes`,
  `free_by_bank`, `free_ranges`, `never_used_bytes`, `modules`, `areas`, `scenarios`, `label_pairs`, `low_pages`, `free_after_start_bytes`,
  `probe`), `unassigned_files`, `warnings`, `other_listings`, `probe` (`dumps`, `ignored`, `not_assigned`), `disk`, `metrics`.
- Metrics (manifest of the viewer, through `lab64 publish`): `ram_free_static_<name>`, and when they exist
  `ram_free_after_start_<name>`, `ram_never_written_<name>`, one set per program (only the programs of `C64_MAP_METRICS`, if set).

Limits: a VICE session that goes through several programs (loader -> game) counts all the writes of the session in the program
it ended in (pessimistic for that one), unless the test calls `Vice.probe_checkpoint()` before each switch (see
[memory-maps.md](memory-maps.md)); sessions that end in no declared program (in BASIC) are listed, not counted. The static
limits of the map hold for every program (buffers behind pointers, data unpacked elsewhere: `;@map` annotations).
