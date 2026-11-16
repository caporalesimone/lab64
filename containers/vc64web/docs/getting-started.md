# Getting started

Copyright © 2026 Simone Caporale. Valid for build 32 / API 25. Full references: [`c64-cli.md`](c64-cli.md) (every command), [`C64-API.md`](C64-API.md) (API), [`scripting.md`](scripting.md) (text scripts), [`../examples/`](../examples/README.md) (runnable examples).

This guide lists **the first things to try**, in order, and the most common errors. All the commands below were run on a real daemon.

## 0. Two ways to use the package
- **`out/VirtualC64-vNN.html`**: the emulator in one file, to open in the browser (also from a phone). No remote control.
- **Daemon + CLI (`headless/`)**: an emulator driven from the command line, for automation, tests, scripts, videos. The rest of the guide is about this.

## 1. Installation and build (once)
```sh
python3 build.py --no-docker                 # do NOT use --bump-version: it is for releases only
cd headless && npm install && npx playwright install chromium
```
`ffmpeg` (with `libx264`) is needed only for the deterministic videos: without it the rest works. Details: README, Build section.

## 2. Starting the daemon
```sh
cd headless
export NODE_PATH=$(npm root -g)              # only if playwright is installed globally
node c64d.js &                               # port 7064; --port N for another one; --headed for a visible window (a display is needed)
```
Stop it with `node c64 quit`. Several emulators together = several daemons on different ports (`--port`, and `node c64 --port N …`).

## 3. First commands
```sh
node c64 start                               # powers on the C64 (BASIC)
node c64 pause                               # stops the core: from here on it advances only when you say so
node c64 sendText 'print"hello"\n'           # types (does not wait)
node c64 runFrames 100                       # advances exactly 100 frames (2 emulated seconds), then stops
node c64 screenText                          # the screen as text
node c64 --out shot.png screenshot           # PNG screenshot
node c64 --compact peek 0x0400 8             # 8 bytes of memory
node c64 poke 0xC000 '[1,2,3]'               # writes: arrays must be valid JSON
```
Understanding the **time model** is the only non-obvious thing: after the deterministic commands (`runFrames`, `runUntil`, …) the emulator is **stopped** between one call and the next; `resume` makes it run in real time. One PAL frame = 19656 cycles.

## 4. Command arguments
Every argument is: `@@file` = the file text; `@file` = binary content (base64); otherwise valid JSON, otherwise a string. Objects and arrays must be **valid JSON** (no `0x…` inside `[ ]` or `{ }`; use decimal numbers or `"0x…"` strings). `--compact` prints the JSON on one line. `--quiet` **does not print the result**: do not use it if you need the output.

## 5. Useful things to try, in order
1. **Wait for an event** instead of counting frames: `c64 runUntil '{"text":"READY."}'` (text as screen code), `c64 runUntil '{"pc":"0xC002"}'`.
2. **Save and restore a state**: `c64 saveState base` … `c64 loadState base` (in the daemon memory); to a file: `c64 --out base.bin saveState base '{"export":true}'` and `c64 loadState @base.bin`. For repeatable experiments.
3. **Text scripts** (timed input, `wait`, `assert`, screenshots, video): `c64 --outdir out script examples/scripts/01-hello.txt`.
4. **In-page control loop** (bots, measures; fast because there is no HTTP per step): `c64 runLoop 'c64.joy(2,{right:true},2);' '{"frames":200}'`. Examples in `examples/loops/`.
5. **Record**: silent deterministic video (`c64 --out v.mp4 video script.txt`), or real-time video+audio (`grabBrowserVideoAndAudio`). How to choose: README, Recordings section.
6. **Regression**: `c64 regress save base` and then `c64 regress check base` (comparison of CPU/RAM/screen with the baseline in the daemon memory).
7. **Find a game variable**: `c64 ramSnap a`, make something happen, `c64 ramDiff a null` → changed addresses.
8. **Exact cycles of a routine**: `c64 measure START_LABEL END_LABEL` (use `loadLabels @@game.lbl` for the names).
9. **Game text**: `findText` (named encodings: `loadEncoding`). If it returns `null` on a game with its own screen and charset, read `c64 screenInfo`: the HUD may be in another area (`{"addr":N}`) and have its own encoding (`{"map":{"0-9":45,"/":55}}`).

## 6. Common errors
| Symptom | Cause and fix |
|---|---|
| The daemon looks stuck | `c64 status` (not queued) shows the job; `c64 abort` interrupts it (the emulator stays stopped). A killed client interrupts its own job: no `pkill -9` needed. |
| `ERROR STALL` | the core has not advanced for 5 s during a run: `c64 abort`, then `c64 status`. |
| A `poke` before `loadFile` disappears | autoload does a reset: poke after `loadFile` returns, or `{"autoload":false}`. |
| A disk does not look attached | attach it with the core running (`resume`), not stopped. |
| Browser recording = still image | `grabBrowserVideoAndAudio` records in real time: the core must run (`resume`, or a running `runLoop`). |
| `call` on a routine that never returns | `CALL_TIMEOUT` after `timeoutFrames` (default 600); for level changes and similar: `{"noWait":true,"frames":N}`. |
| `c64 games` finds nothing | it looks in `$C64_GAMES`, then `./games`, then `<repo>/games`, then `/games`. |
| `trace`/`poke` with `0x…` values in an array give errors or run forever | invalid JSON passed as a string: use decimal numbers. |
| Warp and single-stepping | after `warp(true)` the core advances in jumps of ~26 frames (measured): no `runLoop` in warp if precision matters; to skip frames exactly `runFrames N '{"fast":true}'`. |

## 7. Different results from the same state?
Since API 24 (API 23 had a defect with held inputs) `runFrames` and `runLoop` are exact even when the browser is late: same state + same bot code = same result (even if the game uses "random" numbers: the game generator reads timers and raster, which are part of the state). Check: the `runLoop` result has `exact:true` and `framesActual` equal to `frames`; `retriesTotal` counts the repeats (`retries` lists at most 200). To verify a bot: same `stateHash` with and without `{"_forceRetry":1}` (`c64-cli.md` §14). Test: `examples/shell/11-determinism.sh`.
If there are still differences:
1. Do the two runs start from an identical `loadState` **with the core stopped**? No `type`/`sendText` still running at the moment of `saveState`/`loadState` (the core keyboard queue is not emptied: `loadState` warns). No `grabBrowserVideoAndAudio`, `resume`, `sleep` or `waitFor` in between (real time = not repeatable), no `{"exact":false}`.
2. Does the bot use something outside the emulator (`Math.random()`, `Date.now()`, host timings)? Then it is not repeatable by design.
3. `ramSnap`/`ramDiff` every M frames to find the first frame where they diverge.
To explore many variants: `c64-batch` (several instances in parallel, the bot varies the parameters with `RUN`).

## 8. What is not verified
Docker (build and run), `--headed` on a real desktop (tested only under Xvfb), `game` with `.prg/.t64/.crt` other than disks, JiffyDOS, minimum Node version, Windows/macOS, timings on very long videos. The core emulates the 1541 family: the drive internal state (1541 RAM/CPU) is not exposed. Cycle measures must be confirmed with VICE for timing decisions.
