# Getting started with Lab64

Copyright © 2026 - Simone Caporale

Lab64 builds, tests, emulates and analyzes Commodore 64 programs. Everything runs in Docker containers: on your computer you need
only `sh`, Docker (with BuildKit and Compose v2), `git` and `curl`. Linux, or Windows **inside WSL2** (keep the projects in the WSL filesystem, not
under `/mnt/c`). This page goes from zero to a working project; the [README](../README.md) indexes the reference documents.

## 1. Install

```sh
git clone <Lab64 repository> ~/lab64        # any folder
~/lab64/cli/lab64 install                   # a link in ~/.local/bin; add that folder to the PATH if it says so
lab64 check-env                                # checks the computer: Docker, WSL, line endings, ROMs, images
# BEFORE lab64 images: copy the Commodore ROMs (not in the repository) into roms/vice-roms/{C64,DRIVES} (the only place; read only while the images are built),
# file names and SHA-256 in roms/roms.md; the image build stops until they are right (build-scripts/check_roms.sh)
lab64 images                                # builds the images (once, ~20-30 min: the tools are compiled from source)
```

`lab64 images` can be skipped: every command builds the image it needs the first time. Behind a TLS-intercepting proxy, set
`C64_CA_BUNDLE=<CA file>` before building.

### Install the command

`install` is a subcommand of `cli/lab64` and is run **once**, with the full path, because the command is not in the PATH yet.
From any folder (example with Lab64 in `~/repos/lab64`):

```sh
~/repos/lab64/cli/lab64 install       # or: .../cli/lab64 install /another/folder
lab64 version                                   # prints: Lab64 1.14 (<lab64 folder>)
```

What it does, and nothing else: creates the folder if missing (default `~/.local/bin`), creates or replaces there a symbolic link
`lab64` -> `<lab64 folder>/cli/lab64`, and tells you if that folder is not in the PATH. It copies no file, installs no package and
does not touch Docker, the images or your shell configuration.

- `lab64: command not found` after the install: `~/.local/bin` is not in the PATH. Add `export PATH="$HOME/.local/bin:$PATH"` to
  `~/.profile` (or `~/.bashrc`) and open a new terminal (or `source ~/.profile`).
- The link points into the repository: if you move the Lab64 folder, run `install` again. To uninstall: `rm ~/.local/bin/lab64`.
- From then on the command is just `lab64`, from any folder; the project commands (`init`, `build`, `test`, ...) work in the **project
  folder** (the one with `lab64.env`, or `C64_PROJECT`).

## 2. A new project

```sh
mkdir ~/dev/space-demo && cd ~/dev/space-demo
lab64 init                                  # asks the program name and the title; never overwrites a file
git init && git add -A && git commit -m "Start"
```

What you get:

```
lab64.env              settings of the project for Lab64 (read it: every line is commented)
src/main.asm           the program: BASIC SYS line, colours, clear screen, a message
src/lib/screen.asm     routines included by main.asm
data/                  graphics, music, tables (.binary)
tests/smoke/hello/     a test that runs the program in VICE and checks the screen
tests/sanity/, tests/regression/
manual/manual.html     the instruction manual (one div.page per A5 page)
manual/theme.css       the theme of the manual, on top of the Lab64 base theme
README.md, .gitignore, .gitattributes
```

## 3. Every day

```sh
lab64 build            # out/work/main.prg, out/work/disk.d64 (64tass + cc1541), published in out/releases/v<version>/
lab64 test             # smoke tests in VICE; lab64 test all --list shows all; lab64 test -k HELLO (every suite)
lab64 view             # http://localhost:6080: disks, live screen with audio, memory map, SID Studio (jsSID live, or reSID rendered by sidplayfp)
lab64 play x64sc -autostart out/work/disk.d64     # VICE with sound on the viewer screen
lab64 map              # memory and disk map: out/work/memory-map/index.html
lab64 manual           # the manuals: out/work/manual/*.pdf
lab64 publish          # the release folder again, now with test report, map and manuals (cards in the viewer)
lab64 up               # optional: the whole stack always on (tools, vc64web, viewer); commands start faster. lab64 ps
lab64 run <command>    # any command in the tools container (64tass, cc1541, c1541, x64sc, python3, ...)
lab64 shell            # a shell there
lab64 stop / down      # stop the viewer / the whole stack
```

Everything generated goes into `out/` (not in git). The project files are yours: Lab64 never writes outside `out/`, except
`lab64 init`, which only creates missing files.

## 4. Writing tests

A test is a Python function in a `cases.py`, one folder per feature, in one of three suites:

| Suite | What |
|---|---|
| `tests/smoke/` | few fast tests on the happy path; they run at every build |
| `tests/sanity/` | the tests of the feature in development; then they move to smoke or regression |
| `tests/regression/` | all the corner cases, slow ones too |

```python
from c64test import test, check
from vicemon import Vice, labels, OUT

@test("SCORE-01", "the score starts at zero")
def score_zero(ctx):
    v = Vice()
    try:
        v.load(OUT + "/main.prg")
        v.call(labels("main")["start"])
        check(v.mem(0x0400, 1) == [0x30], "score: %s" % v.mem(0x0400, 1))
    finally:
        v.close()
```

`Vice` starts x64sc with factory settings and the Lab64 ROMs, waits for the C64 without fixed delays and talks to its monitor:
`load`, `call`, `mem`, `poke`, `brk`, `go`, `screenshot`. Labels come from the build (`out/work/<name>.lbl`). Optional duration
caps: `C64_TEST_CAPS` in `lab64.env`.

`lab64 test` exits 0 when everything passed, 1 on a failure or a time cap, and 2 when the arguments are wrong or **no test is
selected** (an empty suite, an ID that matches nothing): a typo never looks like a green run.

## 5. The manual

Edit `manual/manual.html`: each `<div class="page">` is a page, `<kbd>F1</kbd>` becomes a key cap, `<span class="cmd">` is what the
player types. Change colours and type in `manual/theme.css` (variables such as `--accent`, `--paper`, `--cover-bg`); add your own
rules there; or set `C64_MANUAL_BASE="none"` to write the whole style yourself. `lab64 manual` warns when a page overflows
(`--strict` makes it an error).

More manuals: one HTML source each (`manual/manual_it.html`, `manual/quick.html`, ...) and `C64_MANUAL_SRC="manual/*.html"`:
they are all built in the same run. A source chooses its own page format, base theme, theme and PDF name in its head:
`<meta name="lab64:format" content="A4">`, `<meta name="lab64:base" content="plain">` (black on white, for printing),
`<meta name="lab64:theme" content="quick.css">`, `<meta name="lab64:pdf" content="Quick_guide.pdf">`. The format reaches the
PDF as CSS (`@page` size and page box); the text is not reflowed between formats: an A4 manual is its own source.

## 6. The memory map

`lab64 map` needs nothing: from the listings, labels and disk it knows every byte of code, data and variables and where every
file is loaded. Comments in the sources add what it cannot know (no space after `;`; all the forms in [memory-maps.md](memory-maps.md)). The skeleton of `lab64 init` has two of them in `src/main.asm`. Typical ones:

```
;@map $0400..$07e8 "text screen"                                                 ; written by pointers: counts as used
;@map sprites "sprite shapes, copied to $3000 at start-up" free-after=start      ; label pair sprites / sprites_end
;@free code_end..$8000 "room for more code" use=code                              ; free memory and what it can hold: checked
;@free $e000+$800 "under the KERNAL: data only" use=data
;@scenario title: main titlepic                                                  ; in memory together: modules and disk files
;@scenario play: main level?                                                     ; level? = one level at a time
;@map hero..hero_end "the saved hero" layout                                      ; table of its fields (labels + comments)
```

Try it on the skeleton: `lab64 build && lab64 map`, open `out/work/memory-map/index.html`: the screen is an annotated area, the
4 KB at `$C000` are "free for code" in "Free memory, by use". Move the `;@free` over the code (`$0801`) and run
`lab64 map --strict`: it stops with "not free". In a project build use `--strict`, so the annotations follow the code.

Memory really written while the tests run: `C64_MEMPROBE=1 lab64 test all`, then `lab64 map`; a second run with
`C64_MEMPROBE=2` (another fill pattern) removes the bytes that only looked untouched.

Since 1.6 every page also has a "Pages 0-3" section (zero page, stack, pages 2-3: the labels the code uses there, with source
lines), `;@free` notes in `$0000-$03FF` are checked, and two `;@map` areas of the same `scenario=` that overlap are an error with
`--strict`. A test that goes through several programs (loader -> game) calls `v.probe_checkpoint()` just before the switch, so each
program gets its own writes.

**Several programs on one disk** (a loader, an intro, the game, a jukebox: programs that replace each other in memory): one
picture of all of them adds up memory never used together. Declare each program in `lab64.env`, main file first, then the files
it loads (disk file names, wildcards allowed; a file may be in two programs):

```
C64_MAP_PROGRAM_INTRO="intro title"
C64_MAP_PROGRAM_GAME="game level? music*"
```

`lab64 map` then writes an index (`index.html`: one row per program with its free RAM, all of them side by side, files that are
in no program) and one map per program (`program-intro.html`, `program-game.html`). See [memory-maps-programs.md](memory-maps-programs.md).

## 7. When the project grows

- Own build: write `build.sh` (it can call `lab64 run`, `lab64 map`, `lab64 manual`, ...) and set `C64_BUILD="./build.sh"`.
- Own manual generator (tables from your data, screenshots): a script that calls `c64manual.build(...)`, run by `C64_MANUAL`.
- Host variables for your scripts in the containers: `C64_PASS_ENV="MYFLAG OTHER"`.
- Own test command: `C64_TEST="./tests.sh"`; `lab64 test --emu` gives it `C64_EMU=1` (start vc64web yourself with
  `lab64 up vc64web` if it needs the in-browser emulator).
- Viewer on another port, with a password: `VIEW_PORT="6081"`, `VIEW_PASSWORD="..."` in `lab64.env` (also `VIEW_HOSTS`,
  `VIEW_SIZE`); they apply the next time the viewer starts (`lab64 stop && lab64 view`).
- The remote screen of the viewer (live window, VICE live) is **off** at start because it is heavy: turn it on from the page, with `lab64 screen on`, or
  always with `VIEW_SCREEN="on"` ([viewer.md](viewer.md)).
- Own release content and measures: a script that calls `c64publish.publish(...)` (see [publishing.md](publishing.md)).
- The program version: `C64_VERSION` in `lab64.env` (or computed by your build and passed to `lab64 publish --version`).
- A fixed Lab64 version: `LAB64_VERSION` in `lab64.env` (the commands stop on another version; `lab64 check-env` reports it).
- `lab64.env` is a sh file: plain values, quoted or not, with an optional `# comment`; no `$VAR` or `$( )` (the Python tools do
  not expand them).

## 8. Inside the containers

Project at `/work`, Lab64 at `/lab64` (read-only). The `lab64` command (container side: `init`, `build`, `publish`, `test`, `manual`, `map`)
and the Python library (`vicemon`, `c64test`, `c64manual`, `c64publish`, `psid`, `sidrender`) are available there: never write a path to Lab64 in a project.
