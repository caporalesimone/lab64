# Test engine and Python library

Copyright © 2026 - Simone Caporale

`lab64 test` and the Python modules that project scripts and tests import inside the containers. The command options are in
[command-line.md](command-line.md); the settings (`C64_TEST_CAPS`, `C64_TEST_REASON_WORDS`) in [configuration.md](configuration.md).

| File | What it is |
|---|---|
| `containers/tools/test/run.py` | test engine: suites `smoke`, `sanity`, `regression` in the project `tests/` (one folder per feature with a `cases.py`), `-k ID` or prefix (no suite: all suites), `--list`, `--md`; exit 2 on bad arguments or when nothing is selected; module `setup` / `teardown`, `CHAIN`; a setup that raises `Skip` skips its tests; duration caps from `C64_TEST_CAPS` (they do not depend on the order of the suites on the command line; suites always run in the order smoke, sanity, regression); report in `out/work/test_report.txt` / `.json`; live status in `out/tmp/tests.json` (viewer; `aborted` after Ctrl-C, exit 130, or an engine error); one run at a time (lock) |
| `containers/tools/py/c64test.py` | test registry: `@test(ID, description)`, `check(cond, reason)`, `Skip`, `script(ID, description, argv)` (failure reason: output lines with FAIL / error / ERROR or a word of `C64_TEST_REASON_WORDS`) |
| `containers/tools/py/vicemon.py` | VICE library: `ROMS_C64` / `ROMS` (ROM folders for project tools), `Vice` (x64sc with factory settings and all the ROMs of `roms/`, warp, remote monitor without fixed delays, `wait_boot` = waits for READY., then `Vice()` hands over the machine stopped in the monitor with commands and answers in step, memory, `call`, breakpoints, screenshots, run-time memory probe with `C64_MEMPROBE=1`, `probe_checkpoint()` between programs, `resume()` / `running`), `labels()` / `listing()` of the 64tass build, `ROM_ARGS`, `XRUN` |
| `containers/tools/vice/vice_env.sh` | the same VICE options for bash scripts (`VROM`, `XRUN`): a project script loads it with `eval "$(lab64 vice-env)"` |
| `containers/tools/vice/live.vicerc` | VICE settings of `lab64 vice` (joystick 1 on F13-F17, the keys of the overlay) |
| `containers/common/py/psid.py` | writes `.sid` files (PSID v2): a C64 program with init / play addresses and title, author, released; `info(bytes)` reads the header of a PSID / RSID (name, author, subtunes, clock and SID model flags) |
| `containers/tools/py/sidrender.py` | renders a `.sid` to WAV with sidplayfp (and to MP3 with ffmpeg): validated parameters, fixed power-on delay, cache. See [sid-rendering.md](sid-rendering.md) |
| `containers/pdf-gen/c64manual.py`, `containers/tools/py/c64publish.py` | the manual generator and the release publishing: [manuals.md](manuals.md), [publishing.md](publishing.md) |
| `containers/common/py/lab64env.py` | the one reader of `lab64.env` for Python: `setting(name, default)` (environment if set and not empty, then the file), `values()`. Reads `NAME="v"`, `NAME='v'`, `NAME=v`, `export NAME=...`, trailing `# comments`; expands nothing |
| `containers/common/py/d64.py` | the one `.d64` reader: `read(path)` (directory, chains, file contents, BAM), `summary(disk)` (`stats.disk` of the manifest) |
| `containers/tools/py/viewer_player.py` | viewer player (container `lab64-player`, always running with the viewer): `play` / `basic` run `C64_VIEW_PLAYER <file>` on the live screen when the page asks (`POST /control`; they need `C64_VIEW_PLAYER`), `render` renders a `.sid` with `containers/tools/py/sidrender.py` for SID Studio (`POST /render`); through a Unix socket in the `lab64-x11` volume; the viewer has no Docker socket. See [viewer.md](viewer.md#render-endpoint) |

The library is importable in the Lab64 images (`PYTHONPATH=/lab64/py`); the engine also puts the project `tests/` on `sys.path`: a
project keeps its own helpers in `tests/lib/`.

## `Vice` and a running machine

`Vice()` hands over the C64 stopped in the monitor. `go()` lets it run and waits for the
next stop (a breakpoint). `resume()` (or a bare `cmd("x")`, `"exit"`, `"g [addr]"`) lets it run and returns at once; the flag
`running` is then set. VICE answers the first command sent to a running machine with one extra prompt (the monitor entry) before
the answer; `cmd()` knows it, waits for the real answer and strips the entry prompt, so `resume(); cmd("m 0400 0400")` returns the
memory line, not an empty prompt. If the machine stopped by itself meanwhile (a breakpoint), there is no extra prompt and the
flag is cleared. `go()`, `load()` and any command leave the flag cleared.
