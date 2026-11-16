# VirtualC64 (v10, API 10): what is missing

Copyright © 2026 Simone Caporale

Legend: [V] to be verified (it exists but is not tested), [F] feasible (I know the core offers it), [?] I do not know if it is feasible, [L] core limit (cannot be solved from here).

## 1. To verify on what is already done
- [V] Breakpoints and watchpoints after `loadState`: do they survive? Today they must be checked again by hand.
- [V] `type`/`sendText` in real time: tested (GET, F1, SHIFT+A, W+D, strings of ~130 characters), same result as with the emulator stopped. Not tested: browser in the background (slowed timers), warp, NTSC.
- [V] `{LEFT}` 9 frames after `{UP}` lost in a BASIC program with GET (API 6, with defaults 3/2): not reproduced with the new 3/3 defaults; cause unknown. With a 1-frame release the errors are measured (press 3–4: 1 try in 8 correct), the mechanism is not clear.
- [V] `replay` with the emulator running (real time): not exact by design, not measured.
- [V] `c64d` daemon: long sessions (hours), several clients together, Chromium memory.
- [V] `storeSet/storeGet` across builds with different file names: tested only in Chromium; not in Firefox and Safari.
- [V] NTSC: frames are calibrated on PAL (19656 cycles), no NTSC test.
- [V] Phone: the HTML file was not tested on a real phone with this API (only headless Chromium).
- [V] `type`/`sendText` lose keys when the C64 does not read the keyboard (interrupts disabled, LOAD running): not detectable from outside, the prompt is awaited. (Boot after reset: solved in API 8.)
- [V] Matrix ghosting (3 keys at the corners of a rectangle) and joystick/keyboard interference: I do not know if the core emulates them; not verified. With several simultaneous keys the KERNAL (`GET`) reports only one key.
- [V] Minimum key times (press 1, release 2) measured in BASIC with 8 phase shifts; not on other programs or with keyboards read less than once per frame.

## 2. Functions not done
- [F] Conditional breakpoints on registers (today `when` checks only memory). It needs reading the registers at every stop.
- [F] `step`/`trace` with A/X/Y/P/SP registers per instruction (today only pc/bytes/asm/cycles): the register printed by the shell has swapped nibbles, another way is needed (a 6502 stub that alters the cycles).
- [F] PAL/NTSC switch from the API (probably `wasm_configure`, not tested).
- [F] Export/import of the interface settings (JSON) in the menu; today there is only `store*` through the API.
- [F] Automated API tests in the repository (today the test scripts are in the scratchpad).
- [?] Audio: `wasm_get_sound_buffer_address` / `wasm_copy_into_sound_buffer` exist; I do not know if a WAV can be recorded repeatably (the core produces samples only while running).
- [?] 1541 drive CPU and memory: `? drive8` gives the state; I have not verified whether the debugger reads the drive RAM (it would help to understand Krill).
- [?] Cartridges, REU, tape (`wasm_press_play`...): the core handles them, not touched.
- [?] Memory access map (heatmap) as code coverage: the `HEATMAP` option does not turn on with `wasm_configure`; other ways not searched.
- [?] Real-time recording as an alternative to frame replay.

## 3. Core limits (cannot be solved from here)
- [L] Minimum granularity: 1 frame (19656 cycles); `runCycles` rounds up.
- [L] Warp breaks frame exactness.
- [L] Only the 1541 family (1540/1571/1581 refused as "Unknown ROM").
- [L] `wasm_rewind` rewinds the tape, not the state; the core has no buffer of past instructions beyond the last 8 shown by the shell.
- [L] `wasm_sprite_info` gives only x,y; the rest is read from the registers.
- [L] The shell `f` and `m` commands do not accept the arguments tried; `find` is done in JS.
- [L] After a 15–260 ms pause the core catches up to 3 frames: `runFrames` waits 260 ms (≈0.3 s per call).
- [L] It is not VICE: cycle results must be confirmed in native VICE.

## 4. Ideas (not requested)
- A `c64d` variant with direct CDP, without Playwright (proposed and declined on 12/11).
- (done in API 10: `regressSave/regressCheck`.) To verify: baselines across several sessions/restarted daemon; comparison with tolerance for screens with animated sprites.
- Deterministic video (PNG frame by frame + ffmpeg on the Node side) and audio: not done; `recordVideo` is real time, only Chromium verified.

## Layout (since API 10, build 11)
- `VirtualC64-v11.html` = emulator + interface only, no remote control.
- `c64-headless.html` = minimal page for the daemon (emulator only, no interface); `c64-api.js` is injected by the daemon.
- To verify: manual use of `c64-api.js` pasted into the console of the standalone page (the page no longer has `window.c64`, but injection should work because it uses the same globals; not tested).
- The gain of `c64-headless.html` is mostly at run time (no UI/CSS/layout): the size is almost the same (~4.0 MB, dominated by wasm and ROMs).

## Input scripts (API 11)
- Not done by choice: if/goto/loops/variables/include (for logic: JavaScript with the API).
- To do if needed: export recordings (`recordStop`) as text; verify very long scripts and `wait pc=`.

## Docker
- Dockerfile and docker-compose.yml NOT tested: the development environment had no Docker daemon. Only the daemon with C64_HOST=0.0.0.0 and C64_NO_SANDBOX=1 and the client with --host were tested. (13/11: in Lab64 the image `lab64-vc64web` is built and used by the `EMU-*` tests.)
- To verify: build (playwright@1.63.0 + `playwright install --with-deps chromium` on node:22-bookworm-slim), healthcheck, use with --shm-size=1g.

## After the 12/11 review (todo-emulatore-web.md of a project chat), build 17 / API 14
Done: in-page loop (`runLoop`), exact `runFrames({fast})` with warp, deterministic video with inputs (`c64 video`), label sets, `runUntil({screenMatch})`, `driveTrace`, `recordStop({format:'text'})` (partial), `--quiet`/`--compact`, lowercase program name, `stateHash` without CPU. States to files: already possible (documented).
Not done: audio (video and WAV), several instances in parallel, per-routine profiler (cycles per label), conditional breakpoints on registers / `step` with A/X/Y/P.
To verify:
- `video` on long durations (tens of minutes) and with `every:1`; ffmpeg on the daemon side (installed in the Dockerfile, not tested).
- `runFrames({fast})` on a real disk with Krill (tested only on BASIC/start screen).
- `recordStop({format:'text'})`: state `joy` and `sendJoy` are not exported; time starts from the start of the recording.
- Warp: the first `runFrames` after `warp(false)` advances ~26 frames too many (measured in one case); the cause in the core is unknown.
- `runLoop`: ~25 steps/s at 2 frames (real time); faster only with warp (not exact).

## Scripts and video (build 19, API 15)
- [V] Not tested: very long scripts; `assert` and `wait mem=` in real time with long times; `wait mem=` in warp; `keep` videos of many minutes (queue memory, ffmpeg); a script with an error while a `keep` video is open (it stays open: close it with `videoStop`).
- [V] Docker: Dockerfile/compose updated (volumes `scripts/` and `out/`, scripting.md) but NEVER built nor tested (no Docker daemon available here).
- [L] **Audio in the video**: not done. The core (`wasm_copy_into_sound_buffer[_stereo]`) returns blocks of 1024 samples; in 100 frames ~79k samples instead of 88.2k (44.1 kHz), amplitude ~0.002 with a SID tone on, different behavior after `wasm_open_main_thread_audio`. Cause not investigated. Alternative not tested: synthesize the SID offline from the registers (`sidTrace`) with a JS SID model (big work, result different from reSID).
- [F] `call` with parameters on the stack or with a different scratch area; `assert pc=`; compound `wait` (text OR mem): not done.

## grabBrowserVideoAndAudio (build 22, API 16)
- [V] Not tested: long recordings (block memory in the browser), audio/video drift, panel with the page virtual keyboard/joysticks, audio disabled by the page, all the `keyboard`/`joy1`/`joy2` combinations (tested: all below, all overlay, only joy2 overlay, kb below+joy1 overlay, joy1+joy2 overlay, kb+joy2 overlay, joy1 below+joy2 overlay).
- [F] Not done: panel with CRSR up/left (it shows SHIFT + CRSR down/right), per-port FIRE/joystick key with several directions, automatic conversion to mp4 on the daemon side.

## ROMs and layout (build 23, API 17)
- [V] `third-party/*/README.md`: licenses of vc64web and redistribution rights of the Commodore ROMs NOT verified (written in the READMEs).
- [V] Drive ROMs: only 1541 and 1541-II tested; 1540/1551/2031 stuck in LOADING (test interrupted); 1570/1571/1581 refused by the core.
- [?] JiffyDOS / SpeedDOS / Dolphin DOS and cartridges (Final Cartridge, Action Replay, Epyx FastLoad): not provided (proprietary); not verified whether the core accepts them. Dolphin/SpeedDOS need the parallel cable (user port), which the core does not emulate (general knowledge, not verified).
- [V] Docker with the new layout (`COPY headless/ docs/ roms/`): never built. (13/11: built in the game project.)

## Repo and build (build 24)
- [V] `build.py` with Docker: never run here (no Docker daemon); only the generation of `out/` and the daemon were tested.
- [V] `game NAME` for `.crt`/`.t64`/`.prg` uses `loadFile` (documented as supported by the API): not tested with real cartridges; `.d64` yes (attach).
- [V] Minimum Node version not verified (tested with 22).
- [?] The headless page could read the emulator directly from `third-party/vc64web` without a generated page: not done (the page in `out/` embeds wasm and ROMs).
