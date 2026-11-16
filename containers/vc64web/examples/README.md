# Examples

Copyright © 2026 Simone Caporale. Runnable examples, tested on build 26 (API 19). Full command reference: `docs/c64-cli.md`; script syntax: `docs/scripting.md`.

## Before you start
```sh
python3 build.py --no-docker                  # once: generates out/c64-headless.html
cd headless && npm install && npx playwright install chromium
export NODE_PATH=$(npm root -g)               # only if playwright is global
node c64d.js &                                # daemon on port 7064
node c64 start                                # starts the emulator
```
`ffmpeg` is needed only for the deterministic videos (`06`, scripts `04`/`05`) and to convert the `.webm` (`07`). The files produced by the shell scripts end up in `$TMPDIR/c64-examples-output` (usually `/tmp/c64-examples-output`; change it with `OUT=/path`), outside the package.

## Input scripts — `scripts/` (run with `c64 --outdir output script FILE`)
| File | What it shows | Notes |
|---|---|---|
| `01-hello.txt` | `wait`, `text`, `assert screen`, `screenshot` | |
| `02-memory.txt` | `poke`, `assert mem=`, `wait mem=` | |
| `03-joystick.txt` | joystick port 2 (`JOY2-UP`, `JOY2-UP&JOY2-FIRE`) and reading `$DC00` | |
| `04-video.txt` | `video start` / `video stop` (guaranteed close) | core stopped (`c64 pause`), ffmpeg |
| `05-video-keep.txt` | `video start … keep`, closed with `c64 --out long.mp4 videoStop` | core stopped, ffmpeg |
| `06-rec.txt` | `rec start` / `rec stop`: generates `session.txt` | |
| `07-regression.txt` | `saveState`/`loadState`, `regress save`/`check` with `ignore=` | |
| `08-text-and-call.txt` | `wait text` (screen code), `call` of a KERNAL routine, `call … nowait` | |

Recommended start for the scripts: `c64 reset '{"hard":true}'`, `c64 resume`, `c64 ready`, `c64 pause` (known state, core stopped).

## Control loops — `loops/` (`c64 runLoop "$(cat FILE)" '{"frames":300,"every":2}'` or `c64 video FILE`)
| File | What it shows |
|---|---|
| `bot-joy.js` | `joy(port,state,frames)` inside `runLoop` (presses and releases without advancing time), persistent `state` |
| `bot-input.js` | bot with all the input kinds (held and timed joystick, held and timed keys) and variable CPU load: used by `shell/11-determinism.sh` |
| `count-memory.js` | `peek`/`poke` at every step and exit with `return false` |

## Shell commands — `shell/` (`sh examples/shell/NN-….sh`; they use `common.sh`)
| File | What it shows |
|---|---|
| `01-start-and-text.sh` | `start`, `sendText`, `runFrames`, `screenText`, `state`, `screenshot` |
| `02-memory-and-screen.sh` | `pokeRange`, `peek`, `peekWord`, `dump`, `find`, `findText`, `cursor`, `screenSave`, `screenDiff` |
| `03-debug.sh` | `regs`, `disasm`, `step`, `trace` (with `max`), `ramSnap`/`ramDiff`, `call`, `breakpoint` |
| `04-states-and-regression.sh` | `saveState`/`loadState` (also from a file), `regress save`/`check` (exit code) |
| `05-disk.sh` | creates a test D64 (`tools/mk_d64.py`), `attach` with the core running, `LOAD`/`RUN`, `driveState` |
| `06-deterministic-video.sh` | `c64 video` from a script, from a JS loop and from N frames |
| `07-browser-video-and-audio.sh` | `grabBrowserVideoAndAudio` (timed, and separate start/stop), `audioGain`, conversion to mp4 |
| `08-long-jobs.sh` | `status` and `abort` of a long job |
| `09-rom.sh` | `roms`, `rom kernal …`, active user ROMs, `clearRoms` |
| `10-in-page-loop.sh` | `runLoop` with the `loops/` files |
| `11-determinism.sh [N] [STEPS]` | determinism regression test (API 24): a target that reads joystick and keyboard ($DC00 + KERNAL buffer), N runs + 2 with forced repeats, identical hashes; exit 1 if different |

## Tools — `tools/`
- `mk_d64.py [output.d64]`: creates a formatted D64 disk with a BASIC program `HELLO` (`10 PRINT"HELLO FROM D64"`). Tested: `LOAD"HELLO",8` + `RUN` prints `HELLO FROM D64`.

## What is not verified
- The examples were run one at a time on a development daemon (headless Chromium, no sound card). Not tested: Docker, Windows, macOS.
- 14/11: files renamed and texts translated into English; the examples were not run again after the translation.
- `07` records a SID tone generated with `poke`: the audio level depends on the core (very low, see `audioGain`).
- No example uses a real game: your own files in `games/` are needed.
