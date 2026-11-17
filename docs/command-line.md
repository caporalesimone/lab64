# Command line and services

Copyright © 2026 - Simone Caporale

The `lab64` command, its options, and the compose stack that `lab64 up` starts. The variables that change its behavior are in
[configuration.md](configuration.md).

Two halves: `cli/lab64` on the **host** (sh: Docker commands, services, images) and `containers/common/lab64-worker` in the
**containers**, seen there as `lab64` (Python: init, default build, tests, manual, map). The host half starts the container half for those commands;
project scripts already running in a container call the container half directly. No container gets the Docker socket.

```
<lab64 folder>/cli/lab64 install       # once, with the full path: a symlink lab64 -> cli/lab64 in ~/.local/bin (or the folder given); then just `lab64`
mkdir hello && cd hello && lab64 init  # asks name and title; never overwrites a file
lab64 build          # C64_BUILD of lab64.env, or the default: 64tass src/main.asm -> out/work/main.prg, cc1541 -> disk.d64
lab64 test           # C64_TEST, or the test engine on tests/ ([smoke|sanity|regression|all] [-k ID] [--list]); exit 2 = nothing selected
lab64 manual         # C64_MANUAL (run in lab64-pdf-gen), or the default manual: manual/manual.html -> out/work/manual/*.pdf
lab64 page           # only the portable vc64web page (one HTML file with all ROMs, e.g. for the phone): out/work/vc64web/; the same file the viewer offers as ↓ HTML
lab64 map            # automatic memory and disk map: out/work/memory-map/index.html (one map per program if declared)
lab64 publish        # out/releases/v<version>/ + manifest.json for the viewer (the default build does it by itself)
lab64 clean          # deletes what a build recreates: out/work and out/tmp; --keep-release-only: everything but out/releases (also out/cache);
                     # --dry-run lists without deleting. Host command, needs lab64.env; never touches sources or git
lab64 up [service...] / down [service...] / ps   # the compose stack: tools (always on), vc64web, viewer (+ player)
lab64 view / stop    # viewer on http://localhost:6080         lab64 play <command>   a command on the viewer screen with audio
lab64 screen [on|off|status]   # the remote screen of the viewer: off at start, on only when asked (see viewer.md)
lab64 vice [--size WxH] [--bare|file|version]   # VICE with sound on the viewer screen (turns it on); lab64 vice --help
lab64 run [-i IMAGE] <cmd>   # a command in lab64-tools (or lab64-IMAGE)        lab64 shell
lab64 images [--force] | check-env | version | upgrade | install [DIR]
```

- `lab64 test [--view|--no-view] [--emu]`: `--view` shows the tests on the viewer screen (turns the remote screen on; the default when it is already on),
  `--no-view` never; `--emu` starts vc64web for the run and stops it after, if it was off, and exports `C64_EMU=1` (passed to
  the containers). With a project test command (`C64_TEST`) `--emu` only exports `C64_EMU=1`: the command decides what to do
  with it (e.g. `lab64 up vc64web` first). `lab64 run` uses the viewer with `C64_VIEW=1`. Both reach the vc64web daemon when
  it is up (`EMU_URL`, network `lab64`).
- Test engine arguments: suites, `all`, `-k ID|prefix` (repeatable), `--list`, `--md`. No suite = `smoke`, or **every
  suite** when `-k` is given. Exit codes: 0 = all passed, 1 = a failure or a time cap, **2** = unknown argument or suite,
  duplicate IDs, or **no test selected** (a misspelt ID or an empty suite is not a green run; the reports are left as they are).
  The engine is described in [testing.md](testing.md).
- `lab64 help` prints the usage block at the top of `cli/lab64` (between its `# --- usage` markers). Errors of the host command
  line (`compose`, image builds) go to stderr, also when the progress lines are hidden.
- Nested calls (a `C64_BUILD` script that calls `lab64 run ...`) use the same Lab64 as the outer call.
- `lab64 check-env` reads only: the project's `LAB64_VERSION` (an error when it differs), system and WSL, project location,
  Docker, BuildKit, Compose, `lab64` in the PATH, line endings,
  ROMs, images.

## Services: the compose stack (`docker/compose.yaml`)

`lab64 up` starts, for the project of the current folder: **tools** (`lab64-tools` always on), **vc64web**, **viewer** and **player** (always
started with the viewer: it renders `.sid` files for SID Studio; `C64_VIEW_PLAYER` only enables its VICE commands). `lab64 up vc64web`, `lab64 view` start one service; `lab64 down [service]` stops; `lab64 ps` lists.
While **tools** is up, every tools command (`run`, `test`, `map`, `publish`, the default `build`) runs in it with `docker exec`
instead of a new container; when it is down they run in one-shot containers (`docker run --rm`): same results.
`C64_NO_EXEC=1` forces a new container. Measured on the development machine: 0.48 s against 0.52 s for an empty command (the
gain is small on Linux; on Docker Desktop / WSL2 starting a container costs more, not measured). One project at a time: `lab64
up` for another project asks to `lab64 down` the first. Network `lab64` and volume `lab64-x11` are shared by the stack and the
one-shot containers. The **player** has no network at all (`network_mode: none`): it needs only the Unix sockets in `lab64-x11` (screen, audio, player socket), and so compose creates no `<project>_default` network.

Docker names: compose project and network `lab64` (`lab64 up` creates it), volume `lab64-x11` (shared screen and audio), containers
`lab64-tools`, `lab64-viewer`, `lab64-player`, `lab64-vc64web`.

The viewer served by the stack (control center, live screen, SID Studio, the `/control` and `/render` endpoints) is described in
[viewer.md](viewer.md).
