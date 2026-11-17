# Project configuration

Copyright © 2026 - Simone Caporale

What `lab64 init` creates and every setting of `lab64.env`, the file in the root of a project that configures Lab64.

## `lab64 init`: the project skeleton

| File | What |
|---|---|
| `lab64.env` | settings: Lab64 version, program name and version, viewer title, test caps, manual source / theme / PDF name, commented hooks (`C64_BUILD`, `C64_TEST`, `C64_MANUAL`). The title is written without `"` `$` `\` backticks and line breaks (lab64.env is a sh file, sourced by every command) |
| `src/main.asm`, `src/lib/screen.asm` | a program that builds as is: BASIC `SYS` line, border and background, clear screen, a message (64tass, include path `src/`) |
| `data/` | for `.binary` data |
| `tests/smoke/hello/cases.py` | a smoke test that runs the program in VICE and checks the screen; `tests/sanity/`, `tests/regression/` ready |
| `manual/manual.html`, `manual/theme.css` | a two-page manual (cover, loading, controls with key caps) and a theme override |
| `README.md`, `.gitignore`, `.gitattributes` | commands and layout; `out/` ignored; LF line endings |

`lab64 build && lab64 test && lab64 manual && lab64 map && lab64 publish` work on the fresh skeleton: it is the minimal example
of a project.

## `lab64.env`

| Variable | Use |
|---|---|
| `LAB64_VERSION` | Lab64 version required by the project (must equal `VERSION`) |
| `C64_BUILD`, `C64_TEST` | own build / test command run by `lab64 build` / `lab64 test` on the host (e.g. `./build.sh`) |
| `C64_MANUAL` | own manual command, run by `lab64 manual` in `lab64-pdf-gen` (e.g. `python3 tools/manual.py`) |
| `C64_MANUAL_SRC`, `C64_MANUAL_THEME`, `C64_MANUAL_BASE`, `C64_MANUAL_FORMAT`, `C64_MANUAL_PDF` | manual sources (one or more, patterns allowed), project theme, base theme (`c64`, `plain`, `none`), page format (A5), PDF name (one source); see [manuals.md](manuals.md) |
| `C64_NAME` | disk and file name of the default build |
| `C64_VERSION`, `C64_KEEP_VERSIONS` | version published by `lab64 publish` (`out/releases/v<version>/`), versions kept (5); see [publishing.md](publishing.md) |
| `C64_PUBLISH_SID_RENDER` | `1` = `lab64 publish` also writes a 192 kbit/s MP3 of every subtune next to each `.sid` published with kind `sid` (sidplayfp, default parameters, 3:00). Default off: it takes about 15 s of emulation per 3 minutes of audio (see [sid-rendering.md](sid-rendering.md)) |
| `C64_MAP_PAIRS`, `C64_MAP_SCENARIOS` | memory map: suffixes of the label pairs (default `_end`); scenarios `name=mod,mod name2=...` |
| `C64_MAP_PROGRAM_<NAME>` | memory map: one per program of the disk, `"main file, then the files it loads"` (disk file names, wildcards): one map per program and an index. See [memory-maps-programs.md](memory-maps-programs.md) |
| `C64_MAP_METRICS` | memory map with several programs: the programs that publish metrics (`ram_free_static_<name>`, ...), e.g. `"game start"` (names as in `C64_MAP_PROGRAM_<NAME>`, lowercase or not); empty or unset = every program. A name that is no declared program is a warning. Without declared programs it has no effect |
| `C64_TEST_CAPS` | duration caps of the test engine, e.g. `test=10 smoke=20 smoke+sanity=35` (seconds) |
| `C64_PASS_ENV` | host variables passed to the containers by `run.sh` (besides `EMU_URL`, `C64_VIEW`, `DISPLAY`, `PULSE_SERVER`, `C64_MEMPROBE`, `C64_HOST_DIR`, `C64_EMU`); passed by name, so values with spaces are safe |
| `C64_TEST_REASON_WORDS` | extra words that pick the failure reason of a `script()` test from its output (default FAIL, error, ERROR), e.g. `"ATTENZIONE"` for a program that reports in Italian |
| `VIEW_SCREEN` | `off` (default) or `on`: the remote screen of the viewer (live window, VICE live) starts only on request, or with the viewer. See [viewer.md](viewer.md) |
| `VIEW_PORT`, `VIEW_PASSWORD`, `VIEW_HOSTS`, `VIEW_SIZE` | viewer: port on localhost (6080), password of the whole viewer (none by default), host names allowed besides localhost (the server refuses the others against DNS rebinding), screen size (1280x1000). Read from `lab64.env` or the environment when the viewer starts (`lab64 up`, `lab64 view`) |
| `C64_EXTRA_IMAGES` | project images checked by `lab64 check-env` |
| `C64_VIEW_DISK` | disk proposed first in the viewer page (pattern with `*`, the highest version wins) |
| `C64_VIEW_TITLE` | project name in the header of the viewer page |
| `C64_VIEW_PLAYER` | command that opens a file (`.d64 .g64 .prg .t64 .crt`, path relative to the project; `--bare` = no disk) on the viewer screen; `lab64 vice` is the one Lab64 provides (`C64_VIEW_PLAYER="lab64 vice"`, optionally `--size WxH`, `--config FILE`); without it the VICE buttons of the page are off (SID Studio's rendering does not depend on it) |

Other variables: `C64_PROJECT` (project folder, default the current one), `C64_CA_BUNDLE` (CA of a TLS-intercepting proxy, a
secret for npm/pip in the builds), `C64_DOCKER_ARGS` (extra `docker run` options, split on spaces), `C64_HOST_DIR` (set by the
command line: the project folder on the host), `C64_EMU` (1 with `lab64 test --emu`). The `VIEW_*` variables above can also be
set in the environment.

`lab64.env` values: plain values, quoted (`"..."` or `'...'`) or not; a `# comment` may follow. The shell sources the file, the
Python tools read it with `containers/common/py/lab64env.py` (no expansion: do not use `$VAR` or `$( )` in values). A project folder may contain
spaces (checked: init, build, test, manual, map, publish), but better avoid them.
