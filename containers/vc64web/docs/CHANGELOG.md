# Changelog

Format: **Add** (new) · **Fix** (corrected) · **Change** (behavior changed).
"Build" = number in `VirtualC64-vNN.html` and in the zip name. "API" = version of `c64-api.js` (`c64.apiVersion`).
Newest entries at the top. For builds up to 10 the build↔API link is not recorded: they are listed by API.

## After build 32 (not numbered yet, 13/11 - 14/11)
- Change (16/11): the Docker image holds the **portable page** too (`/app/out/VirtualC64-vNN.html`); `c64d` serves it at `GET /pages/` (only that file name),
  the Lab64 viewer proxies it and offers it as a download. `build.py --portable-only` builds only that page (nothing else in the output folder is touched).
- Add (16/11): portable page, **drive indicator** in a strip **below the emulator window** (portrait: between screen and controls; landscape: bottom
  strip, the screen is shortened): green LED (on = drive LED on) + a bar as wide as the window minus the LED, tracks 1-35 coloured by
  **hardware speed zone** (T1-17 = Zone 3, T18-24 = Zone 2, T25-30 = Zone 1, T31-35 = Zone 0; zone numbers from the 1541 specification, not measured
  in the core), tracks in use brighter (BAM of a standard d64, read when the disk is loaded), track 18 highlighted, white head marker and a label
  `T18 · Zone 2` under the bar following the head (rounded to the whole track).
  Fed by the core messages `MSG_DRIVE_LED`, `MSG_DRIVE_MOTOR`, `MSG_DRIVE_STEP` (hook on `message_handler` of the inner page, no polling).
  Measured: `MSG_DRIVE_STEP` data2 = half-track (directory = 35 -> track 18); drive index in data1 (0 = drive 8). Not available: sector, read/write
  (no `MSG_DRIVE_READ/WRITE` seen; `driveState().readMode` sampled at frame boundaries stayed true during a SAVE): the LED is green only.
  Tested in headless Chromium (portrait and landscape) on the real page with the game disk; not tested on a phone.
- Add: portable page with **`?disk=URL[&program=NAME]`**: downloads the disk and starts it (with "Autoload + RUN" if on). `fetch` with
  `cache:'no-cache'` (downloaded again only if changed on the server). Without the parameter the page makes no network requests, as
  before. Only from a web server (from `file://` the browser blocks `fetch`). Tested with the game viewer (viewer Node server, 14/11; websockify before).
- Change (14/11): the whole package in English (comments, messages, page texts, documentation, examples; example files renamed:
  `01-hello.txt`, `02-memory.txt`, `07-regression.txt`, `08-text-and-call.txt`, `count-memory.js`, `01-start-and-text.sh` ...
  `11-determinism.sh`). The client error prefix is now `ERROR CODE: message` (was `ERRORE`). The key test program shows
  `KEY AND JOYSTICK TEST` and `runKeyTest()` waits for that text. The API is otherwise unchanged (API 25).

## Build 32 (API 25) — from a project report on v31
- Check on the game (report v31): R12–R16 solved; full boss bot with identical hash with 0, 1 real, forced at every step, 2 every 3, `exact:false`; `c64-batch -j 3` 9/9 identical.
- Fix R17: `retries` truncated at 200 entries without warning → `retriesTotal`, `retriesTruncated`; `c64-batch` uses the total; `11-determinism.sh` prints the total.
- Doc: `_forceRetry`/`_forceEvery` as test options to verify a bot; measure of the exact-step cost (44 ms → 82 ms per 2-frame step, due to the core after the restore; internal cause not verified).

## Build 31 (API 24) — from a project report on v30
- **Fix R12 (blocking)**: the restore of the exact steps lost held joysticks and keys. Measured causes: (1) joystick ports and keyboard matrix are not in the core snapshot; (2) the restore is not transparent even without input (a repeated step changed the CIA state); (3) scheduled keyboard events stay in the core queue across the restore and `loadState` (and passed from one run to the next: the first run of a new daemon differed from the others). Fixes: input model reapplied at every restore (releases everything, presses again, reschedules the consumed ones); every step starts from a freshly restored state; `type()` in `runLoop` with release handled by the loop; `saveState`/`loadState` with the inputs.
- **R13**: `11-determinism.sh` with a target that reads `$DC00` + KERNAL buffer, `loops/bot-input.js` (replaces `bot-chiuso.js`), forced repeats. Result: same hash with 0, 1 per step, 2 every 3 repeats; 6/6 equal on 3 instances.
- **R14** `.cdef` with symbols and `.enc`; **R15** `assert text`; **R16** `retriesCount` in `c64-batch`.
- Cost: one more restore per step (~6 ms) besides the snapshot (~5 ms); with one instance the speed stays real time (not measured again in detail on the game).
- Not verified: the game's real `gfx_consts.inc` (a file with the same structure was tested); long `sendText` across a restore (it uses windows of scheduled events: it should be covered by the rescheduling, not tested); joystick/keyboard with `--headed` and the user's hands on the window.

## Build 30 (API 23) — from a project report on v29
- **Determinism fix** (R4/R5/R6): exact `runFrames`/`runLoop` with snapshot+check+restore; `runLoop` returns `framesActual`, `exact`, `retries`. Reproduced without the game (1 step in 1000 at +1 frame with variable CPU load) and fixed: 3/3 identical hashes over 1000 steps; test `examples/shell/11-determinism.sh` + `examples/loops/bot-chiuso.js`.
- Add (R1): `loadEncoding` (object or 64tass `.cdef` lines), `encodings`, `enc` option in `findText`/`runUntil`/`wait text`.
- Add (R2): `findText {len}` linear search in a buffer, returns `{offset,addr}`.
- R3: labels in `addr` already worked; documented.
- Add (R9): `headless/c64-batch` (several runs on several daemons, `RUN` in the loop code, JSON result collection).
- Fix: error message for `JOY2-UP&FIRE` in scripts; `findText` with `map`: upper/lower case equivalent.
- Not done, with the measured reason: R7 (no synchronous wasm call; `SPEED_BOOST` 500% with no effect), R8 (useless: the pace is real time, not the drawing cost), R10 profiler (no per-instruction hook in the core), fast `whenRegs` (the RetroShell does not read the CPU registers).
- Not verified: `loadEncoding` with the game's real `.cdef`; 64tass `.cdef` syntax rebuilt (range `"AZ"` and `"A","Z"`), not from its documentation; snapshot restore with disk loads running (only typed text tested).

## Build 29 (API 22)
- Add: `measure(from,to,{n})` with min/max/mean.
- Change: the shell examples write into `$TMPDIR/c64-examples-output` (no longer `output/` in the package).
- Doc: `whenRegs` documented as slow (≈0.2 s per stop, measured by the other chat); `getting-started.md` §7 on how to find the cause of different results from the same state.
- Not done: faster `whenRegs` (the cost is in the 3 halt/run per stop and in the wait that avoids the frame catch-up; removing it would advance the emulation non-exactly: not verified whether and how to remove it); HUD letter map (it needs the game code, which I do not have). Bot determinism in the game: not reproducible here; without the game the loop is exact (3/3 equal).

## Build 28 (API 21)
- Add: `findText(...,{map})` (own encoding), `measure(from,to)` (cycles between two PCs), `runUntil({pc,whenRegs})`.
- Fix: `c64 games` did not find `games/` when run from `headless/` (now it also looks in `<repo>/games`).
- Doc: `docs/getting-started.md` (first things to try), several instances in parallel (tested: two), warp measure (jumps of ~26 frames).
- Not done: `runLoop` in warp (not exact because of the measured granularity), per-routine profiler, 1541 drive RAM/CPU state, deterministic video faster than real time. `change_level` (12 s): not reproduced without the game; hypothesis, not verified: the routine really returns after ~600 frames (level generation), i.e. close to the `call` timeout (600).

## Build 27 (API 20)
- Add: daemon option `--headed` / `C64_HEADED=1`: Chromium with a visible window, driven by the CLI as in headless. A display is needed; closing the window ends the daemon. Tested only under Xvfb (start + commands); the window look on a real desktop was not seen.
- Add: `screenCodes({addr})` and `findText(text,{addr})` read the screen RAM from a chosen address instead of the VIC one (games with the text screen elsewhere or double buffer). Not verified on a real game (a null `findText` reported in the boss room: cause not established).
- Doc: Mermaid diagrams (architecture, job/status/abort flow, recording choice, build pipeline, release procedure).

## Build 26 (API 19)
- Fix: `reset({hard:true})` did not work (`wasm_hard_reset is not a function`).
- Fix: the daemon crashed with results containing BigInt (e.g. `c64 wasm wasm_get_cpu_cycles`).
- Fix: `roms()` overestimated by 1 byte; Change: `c64 rom` with no arguments = active user ROMs; `c64 rom KIND NAME` passes the file name.
- Doc: new `docs/c64-cli.md` (every client and API command with real output and what is not verified) and `examples/` folder (8 scripts, 2 loops, 10 shell scripts, test D64 generator), all tested.

## Build 25 (API 18)
Fixes from field tests (a game project); details in `docs/C64-API.md` (API 18).
- Fix: `runLoop` with `joy(port,state,frames)` never returned (two concurrent `runFrames` stopped each other). Now runs are serialized and inside `runLoop` `joy(...,frames)` presses/releases without advancing time. It was also the cause of the «9 minutes» of `c64 video` with a bot.
- Add: `STALL` watchdog (core stopped for 5 s during a run).
- Add: `abort()` / `c64 abort` (interrupts the running job); a closed or killed client interrupts its job; `c64 status` / `progress()` (running job and progress).
- Fix: `call` that never returns → clear `CALL_TIMEOUT` error (restores PC and work area); Add: `call(...,{noWait})` and `call ADDR nowait` in scripts.
- Add: `findText`, `screenCodes`, `runUntil({text})`, `wait text "..."` (search as screen code, also with custom charsets).
- Add: `grabBrowserVideoAndAudio({audioGain})` to raise the level of the recorded audio (very low).
- Doc: `timeoutFrames` 3000 is the default, not a limit; the deterministic video runs at real time; a `POKE` before `loadFile` with autoload is lost (reset).

## Build 24 (API 17)
- Change: `build.py` no longer increments `BUILD` by default; incrementing needs `--bump-version` (replaces `--no-bump`).
- Add: `build.py` checks ffmpeg (PATH + libx264 encoder) at the end of the build; if missing it prints a WARNING without blocking. The README explains how to install it.
- Change: the Docker image contains only what the headless run needs (page already built, `headless/`, API and scripting docs, ROMs): allowlist in `.dockerignore`.
- Change: repo with `build.py` that generates everything in `out/` (portable HTML with ROMs and emulator embedded, headless page, Docker image if Docker is there). `portable/` and `headless/` contain only sources; `out/` is not in the repo. The ROMs are in the repo (`third-party/`).
- Add: portable page with a menu to choose the Kernal (7 variants), chargen (2) and drive (1541-II/1541); the standard ones by default. Headless: only the standard ones embedded (others with `c64 rom`).
- Change: removed the non-compatible drive ROMs (1540, 1551, 2031, 1570/71/81, 1001, 2040…9000).
- Add: client `c64 games` / `c64 game NAME` (`games/` folder, `$C64_GAMES`); `$C64_ROMS` accepts several folders separated by `:`.
- Change: Docker embeds the whole repo (incl. `out/`), volumes `/games`, `/roms`, `/scripts`, `/output`.
- Change: the API version is in the `headless/APIVER` file (read by the daemon); `headless/package.json` declares the only dependency, `playwright`.

## Build 23 (API 17)
- Change: new zip layout: `README.md` and `CHANGELOG.md` in the root, `Dockerfile` in the root, `docs/`, `headless/` (formerly `src`), `portable/` (standalone HTML), `third-party/` (emulator and ROMs, one README per component with origin and license).
- Add: `loadRom`, `clearRoms`, `roms`, `start({roms})` and client `c64 roms` / `c64 rom KIND NAME`: alternative ROMs (Kernal, Basic, chargen, 1541 drive) from the `third-party` folder. All the VICE Kernals boot; of the drives only the 1541 family.
- Change: `c64 docs` also looks for `C64-API.md` in `docs/` and `../docs/`; Docker: copies `headless/`, `docs/` and the VICE ROMs (`C64_ROMS=/app/roms`).

## Build 22 (API 16)
- Add: `grabBrowserVideoAndAudio` — records browser video and audio (webm VP9+Opus) in real time, in a separate recorder, with no synchronization with the emulator. Control panel with independent choice `keyboard`/`joy1`/`joy2` = `none|below|overlay` (FIRE on the left, stick on the right; in overlay a two-circle stick), `scale`.
- Note: `c64 video` and `video start` in scripts stay deterministic and silent.

## Build 19 (API 15)
- Add: script commands: `poke`, `assert mem=`/`assert screen`, `wait mem=` (also `!=`, mask), `saveState`/`loadState`, `screenshot`, `regress save|check`, `call`. Errors with line number and codes `ASSERT`/`REGRESS`/`TIMEOUT` (exit 1 from the shell).
- Add: `video start|stop` and `rec start|stop` in scripts; without `keep` closing is guaranteed at the end of the script (also on error), with `keep` they go on after the script and are closed by hand (`c64 videoStop`, `recordStop`).
- Add: `scripting.md` (full guide with examples) in the package; client `--outdir`; Docker: folders `scripts/` and `out/` mounted.
- Change: `runScript` errors carry `outputs` and `log` (the client saves the produced files anyway).
- Note: audio in the video not done (core samples not deterministic, see C64-API.md).

## Build 17 (API 14)
- Add: `runLoop` (control loop inside the page, ~8x faster than steps over HTTP).
- Add: `c64 video` (deterministic mp4 with inputs, ffmpeg on the daemon side; `capStart/capRun/capTake/capStop`).
- Add: `runFrames(n,{fast:true})` exact also with warp (500 frames: 0.64 s instead of 10 s).
- Add: label sets (`loadLabels({set})`, `useLabels`, `set:name`), `runUntil({screenMatch})`, `driveTrace`, `recordStop({format:'text'})`.
- Add: client `--quiet` and `--compact`; Dockerfile with ffmpeg.
- Fix: `stateHash` unstable at the first call (the CPU component depends on the debugger): excluded from the overall hash (`includeCpu`).
- Fix: `loadFile`/`start` with an uppercase `program` did not find the file (now lowercase).
- Change: documented that the first `runFrames` after `warp(false)` advances ~26 frames too many.

## Build 16 (API 13)
- Change: `recordVideo({scale})` maximum 4 (1536×1080, about full HD); 8 before.

## Build 15 (API 12)
- Add: `recordVideo({scale})`, integer scaling with sharp pixels (e.g. 3 → 1152×810).

## Build 14 (API 11)
- Fix: `c64 sendText 'text\n'` from the shell typed a literal `\n`; now it presses RETURN.

## Build 13 (API 11)
- Add: `Dockerfile` and `docker-compose.yml` (not tested). Daemon: variables `C64_HOST`, `C64_NO_SANDBOX`; client: `--host`.

## Build 12 (API 11)
- Add: `runScript` / `scriptCheck` and `c64 script file.txt` (lines `<frame> <input> [duration]` and `wait`).
- Change: the zip has the version number in its name.

## Build 11 (API 10)
- Change: the standalone HTML no longer contains remote control nor documentation. The API is in the `c64-api.js` file, injected by the daemon.
- Change: the daemon opens `c64-headless.html` (emulator only, no interface). HTML name without `-apiN`.
- Change: the documentation is `C64-API.md` (also `c64 docs [word]`); the `docs()` method no longer exists.
- Add: `C64-TODO.md` and this changelog in the zip.

## API 10
- Add: `regressSave` / `regressCheck` / `regressList` and `c64 regress` (comparison of a recorded state vs a new one: hash, RAM, screen).
- Add: `recordVideo` (WebM, real time, not deterministic).
- Fix: the CPU hash is excluded from the comparison (unstable), unless `includeCpu`.

## API 9
- Change: `type` = one key or several simultaneous keys; `sendText` = strings. `key()` and the old `type(string)` removed (no backward compatibility).
- Change: minimum times press 1 / release 2 frames (default 3 / 3).
- Add: `framesPerKey` and `releaseFrames` in `sendText`.

## API 8
- Fix: `type` and `sendText` lost characters after a reset (the KERNAL reads the keyboard after ~140 frames): now they wait for the boot (`noWait` to disable it).

## API 7
- Add: `sprites`, `stateHash`, `disasm`, `find`, `ramSnap` / `ramDiff`, `recordStart` / `recordStop` / `replay`, `sendJoy`, `store*`.
- Add: Node daemon `c64d` and command-line client `c64`.

## API 6
- Add: `sendText`, watchpoints, `saveState` / `loadState`, `step` / `trace`, `inspect` / `sid` / `sidTrace`, `screenDiff` / `recordGif`, `runUntil` with `pcIn` / `mem` / `watch` / `when` / `all`, errors with a code.
- Change: `frames()` returns an integer (the fractional one is `framesExact()`).
- Fix: `loadFile` with autoload returned before the end of the sequence (now it waits; `wait:false` for the old behavior).
- Fix: `setRegs` with a label in `pc` set 0.

## API 5
- Change: «Autoload + RUN» on by default (also for `start({disk})` and `loadFile` of a d64; `autoload:false` to disable it).
- Change: the key test shows up in ~4 s instead of ~20 s.

## API 4
- Change: key test rewritten in machine language (1-frame latency; F2/F4/F6/F8, RESTORE).

## API 3
- Add: deterministic control (`runFrames`, `runUntil`, `regs`, `call`, breakpoints, `diskImage`, `driveState`, labels, `joy(port,state,frames)`, `peek(a,n,opt)`, `start({driveRom})`).
- Change: `screenText` reads from the VIC.

## API 2
- Add: `runKeyTest`.

## API 1
- Add: basic control (start, keys, joystick, peek/poke, `screenText`).
