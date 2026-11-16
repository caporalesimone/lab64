# External control API — `window.c64`

Version: `c64.apiVersion` / `c64.info()` (API number in `headless/APIVER`, build in `BUILD`)

Copyright © 2026 Simone Caporale

## Repository layout
- `build.py` generates in `out/`: `VirtualC64-vNN.html` (portable page, no control API) and `c64-headless.html` (emulator only, opened by the daemon).
- `headless/c64-api.js`: the `window.c64` API, **injected** into the page after loading (the daemon does it by itself; by hand, paste it into the console). The API version is in `headless/APIVER`, put in place of the placeholder at injection.
- `headless/c64d.js`: Node daemon (headless Chromium via Playwright, used only internally) that opens the page, injects `c64-api.js` and exposes `window.c64` over HTTP on 127.0.0.1.
- `headless/c64`: command-line client. `c64 docs [word]` prints this documentation (or the sections whose title contains the word).
- `docs/`, `README.md`, `docs/CHANGELOG.md`, `third-party/` (emulator and components, one README per component), `roms/`, `Dockerfile`.

The API does not use the interface: no clicks on buttons, no coordinates. In the methods below the form is JavaScript `c64.method(args)`; from the shell it is
`c64 method arg1 arg2…` (each argument is JSON, `@file` = file in base64, `@@file` = text file, `--out file` saves PNG/GIF/video/disk).

```sh
NODE_PATH=$(npm root -g) node c64d.js &   # once, from headless/ (uses ../out/c64-headless.html and c64-api.js next to c64d.js; --page/--api for other paths)
c64 start
c64 sendText 'print"hello"\n'
c64 waitFor HELLO
c64 screenText                    # screen as text, without vision
c64 quit
```

Many methods are asynchronous. Errors have a code (`e.code`; from the shell `ERROR CODE: message`, exit 1),
e.g. `NOT_STARTED: emulator not started: call c64.start()`.
New codes in API 18: `ABORTED` (job interrupted by `abort()`/client closed), `STALL` (the core has not advanced for 5 s during a run), `CALL_TIMEOUT` (`call`: the routine did not return), `CLIENT_GONE` (the client disconnected before the job started; daemon only).

## Life cycle
| Method | Description |
|---|---|
| `start({disk:{name,data}, autoload=true, program, port, driveRom, timeout})` | Starts the emulator. `data` = base64, array or `Uint8Array`. Returns `state()` when the boot is over. |
| `ready(timeout=30000)` | Waits for the emulator to be started and at the BASIC prompt (>3M cycles). |
| `stop()` | Powers off (removes the iframe). |
| `reset()` | C64 reset. |
| `pause()` / `resume()` | Pause / resume. |
| `warp(on)` | Warp on/off. |
| `state()` | `{started, running, frozen, warp, cycles, disk8, disk, port, kbd, roms}`. |
| `runKeyTest()` | Restarts and loads the key/joystick test (like the 🧪 button): scans the keyboard matrix and the joysticks via IRQ (6502 routine at `$C000–$C60F`, hook on IRQ/NMI) and reverses the pressed key within 1 frame. Shows left/right SHIFT, F1–F8, RESTORE, ports 1 and 2. The screen title is `KEY AND JOYSTICK TEST`. |

## Input
| Method | Description |
|---|---|
| `type(key|[keys], {frames:3, releaseFrames:3, shift, ctrl, cbm, noWait})` | **A single key** (character or name: `'w'`, `'RETURN'`, `'F1'`, `'RUN/STOP'`, `'SHIFT+A'`, `'CTRL+3'`) or a **list of simultaneous keys** (`['w','d']`). C64 matrix, `frames` of press (min 1) + `releaseFrames` (min 2). A long string → `BAD_ARG`: use `sendText`. Returns `{keys,frames}`. |
| `keyDown(key|[keys])` / `keyUp(...)` | Holds one or more keys; effective from the next emulated frame. |
| `sendText(text, {framesPerKey:3, releaseFrames:3, keepCase, noWait})` | For strings: see "API 6 changes" and "API 9 changes". |
| `joy(dir, on, port?)` | `dir` = `up|down|left|right|fire`, `on` = 1/0. Default port: the chosen one (J2). |
| `joyPulse(dir, ms=150)` / `fire(ms=120)` | Short press. |

Key names (case insensitive): `RETURN` (`ENTER`,`CR`), `RUN/STOP` (`RUNSTOP`,`STOP`), `F1`…`F8` (F2/F4/F6/F8 = SHIFT+F1/F3/F5/F7), `SPACE`, `HOME`, `CLR`, `DEL`, `INST`, `UP` `DOWN` `LEFT` `RIGHT` (also `CRSR_*`), `RESTORE`, `CTRL`, `CBM` (`C=`), `SHIFT`, `RSHIFT`, `POUND`, `ARROW_UP`, `ARROW_LEFT`; combinations with `+` (`'SHIFT+A'`, `'C=+Q'`). `keyNames()` lists them.
Warning: with Fire pressed, port 2 disturbs the keyboard (as on a real C64).

## Files
| Method | Description |
|---|---|
| `loadFile(name, data, {autoload, program})` | Attaches `.d64/.g64/.prg/.t64/.crt`. For `.prg/.t64`: reset + automatic `RUN`. For `.d64` (autoload on by default, `autoload:false` to disable it): `LOAD"program*",8,1` + `RUN`. |
| `eject()` | Ejects the disk from drive 8. |

## Memory
CPU view, I/O included (applies to RAM, ROM and registers). `a` = address 0–65535.

| Method | Description |
|---|---|
| `peek(a)` / `peekWord(a)` | One byte / a little-endian word. |
| `peekRange(a, n)` | Array of `n` bytes. |
| `dump(a, n)` | Text hex dump, 16 bytes per line. |
| `poke(a, v)` / `pokeRange(a, bytes)` | Write. |

Note (not verified): reading some I/O registers (e.g. CIA `$DC00-$DD0F`, VIC `$D000-$D3FF`) might have side effects. For large dumps avoid `$D000–$DFFF` if not needed.

## Screen
| Method | Description |
|---|---|
| `screenText()` | 25 lines × 40 columns from the KERNAL screen page (`$0288`). Graphic characters appear as `▒`. |
| `cursor()` | `{col,row}` from locations `$D3` / `$D6`. |
| `waitFor(text, timeout=15000)` | Waits for the text to appear on screen (case ignored). `true`/`false`. |
| `screenshot()` | `data:image/png;base64,...` of the canvas. |

`screenText()` reads the KERNAL screen RAM: in games using another VIC bank or bitmap mode it is not meaningful.

## Deterministic control (API v2)
Model: after `runFrames`, `runCycles`, `runUntil` and `call` the emulator stays **stopped**; `peek`/`poke` happen on a frozen state; `resume()` puts it back to real time. 1 PAL frame = 19656 cycles.

| Method | Description |
|---|---|
| `cycles()` / `frames()` | Total cycles / frames (cycles ÷ 19656). |
| `runFrames(n)` | Exactly `n` frames, then stops. Returns `{reason, cycles, frames}`. |
| `runCycles(n)` | As above, rounding up to whole frames. |
| `runUntil(cond, {timeoutFrames=3000})` | `cond`: `{pc}` (number, `'$0840'`, label or array), `{addr, value, mask?, not?}`, `{screenText:'text'}`, `{screenRegex:'^READY'}`, `{text:'text'|[codes]}` (API 18: search in screen code, see `findText`), `{cycles}`; the first one verified wins. Timeout → exception `timeout: pc $0840 not reached in 600 frames`. `pc` stops on the exact instruction. |
| `pause()` / `resume()` | Stops / restarts in real time. |
| `regs({full:true})` | `{pc, line, cycle, cycles, a, x, y, p, sp}`. A/X/Y/P/SP via a 6502 stub at `$0334–$0367` (restored, ~40 cycles). `{full:false}` reads only PC/raster. |
| `setRegs({pc,a,x,y,p})` | SP cannot be changed. |
| `call(addr, {a,x,y}, {timeoutFrames=600, scratch=0x0334, noWait, frames})` | `JSR addr` and return with registers/PC restored; returns `{a,x,y,p}`. If it does not return: error `CALL_TIMEOUT`. `noWait:true` (API 18): `JMP` to the routine, lets it run `frames` frames (default 2), returns `{started,pc,frames}`; see "API 18 changes". |
| `abort()` / `progress()` | API 18. `abort()`: interrupts the running job (error `ABORTED` to that job, core stopped). `progress()`: `{frozen,cycles,run,loop}` of the running job. From the shell: `c64 abort`, `c64 status` (they bypass the queue). |
| `findText(text\|codes, {raw,all,exact})` / `screenCodes()` | API 18. Text search in the screen RAM as screen code: `{row,col,addr}` or `null` (`all:true` → list). `screenCodes()`: the 1000 raw screen codes. |
| `breakpoint(a)` / `breakpoints()` / `clearBreakpoints()` | Core breakpoints. |
| `peek(a, n?, {ram?})` | Byte or array of `n`. `ram:true` = pure RAM (temporarily sets `$01`). `a` = number, `'$C000'` or label. |
| `poke(a, v \| bytes, {ram?})` | Writes a byte or an array. |
| `loadLabels(text)` / `label(name)` | VICE `.lbl` labels (`al C:0840 .name`) or `name = $0840`. |
| `attach(8, data, name)` / `detach()` | Attaches / ejects a disk (drive 8 only). |
| `diskImage(8, {bytes?})` | Current d64 (base64, or `Uint8Array`). |
| `driveState(8)` | `{type, hasDisk, motor, powerSave, syncMark, readMode, halftrack, track, headOffset}`; LED not exposed; `track=(halftrack+1)/2` not verified. |
| `joy(port, {up,down,left,right,fire}, frames)` | Full state; with `frames` it releases afterwards; `joy(2,{})` releases. The release is visible at the next `runFrames`. |
| `screenInfo()` | `{bank, screen, charset, charsetRom, lowercase, bitmap, ecm, multicolor, textMode}`. |
| `screenText()` | Now uses the screen chosen by the VIC (`$D018`/`$DD00`). |
| `border()` / `background()` | `$D020` / `$D021`. |

**Measured** (headless Chromium, `file://`): `runFrames(7)` = exactly 7 frames with pauses of 0–350 ms between calls; same hash of RAM `$0000–$07FF` after `reset()` + 300 frames in two sessions; `regs`/`setRegs` (a=0x12,x=0x34,y=0x56 read back identical); `call(0xFFD2,{a:0x58})` writes "X"; SAVE from BASIC and name found again in `diskImage`; breakpoint on `$EA31` stops on the instruction.

**Limits / not verified**
- With `warp(true)` `runFrames` is not exact (measured 26 instead of 10): use warp only with `runUntil`.
- After a 15–260 ms pause the core catches up to 3 lost frames: `runFrames` waits up to 260 ms to avoid it (cost up to ~0.3 s of clock per call).
- `runCycles` does not go below the frame. NTSC not tested.
- Watchpoints and SP changes are not exposed by the core. IRQ/NMI can fire during stubs and `call`.
- The window must stay in the foreground: slowed timers in a background tab might alter the wait times (not verified).

## Menu: manual POKE / PEEK
The ☰ menu has a panel with address and value (decimal, `$HEX`, `0x..`, `%bin`, or a loaded label) with the POKE and PEEK buttons and the "Pure RAM" option. It works at any time.

## Versions
Build = progressive number of the page (`VirtualC64-vNN.html`); the API has its own version, inside `c64-api.js`. The API has **a single integer** that grows by 1 at every API change. **1** basic control; **2** `runKeyTest`; **3** deterministic control (`runFrames`/`runUntil`/`regs`/`call`/breakpoints/`diskImage`/`driveState`/labels, `joy(port,state,frames)`, `peek(a,n,opt)`, `screenText` from the VIC, `start({driveRom})`); **4** key test in machine language (1-frame latency, F2/F4/F6/F8, RESTORE); **5** "Autoload + RUN" on by default (also for `start({disk})` and `loadFile` of a d64: pass `autoload:false` to disable it); the key test appears in ~4 s instead of ~20 s. **6** `sendText`, watchpoints, `saveState`/`loadState`, `step`/`trace`, `inspect`/`sid`/`sidTrace`, `screenDiff`/`recordGif`, `runUntil` with `pcIn`/`mem`/`watch`/`when`/`all`, errors with code, integer `frames()` (before fractional: now `framesExact()`). **7** `sprites`, `stateHash`, `disasm`, `find`, `ramSnap`/`ramDiff`, `recordStart`/`recordStop`/`replay`, `sendJoy`, `store*`. **8** `type` and `sendText` wait for the end of the boot after a reset (`{noWait:true}` to disable). **9** keyboard: `type` = one key or several simultaneous keys, `sendText` = strings, `key()` removed, minimum times 1/2 (default 3/3). **10** regression (`regressSave`/`regressCheck`/`regressList`) and `recordVideo`. **11** `runScript`/`scriptCheck` (input scripts from text files); the API is now a separate file (`c64-api.js`), injected into the page. **12** `recordVideo({scale})` (integer zoom 1-4 with sharp pixels; 13: maximum raised to 4). **14** `runLoop`, deterministic video with inputs (`c64 video`), exact `runFrames({fast})` with warp, label sets, `runUntil({screenMatch})`, `driveTrace`, `recordStop({format:'text'})`, `stateHash` without CPU, lowercase program name. From 15 on: see the "API N changes" sections below.

## Limits found (read before writing tests)

**Time and determinism**
- `runFrames(n)` is exact only without warp: with `warp(true)` measured 26 frames instead of 10. With warp use `runUntil`.
- After a 15–260 ms pause the core "catches up" to 3 lost frames (measured +3 with a 100 ms pause; no catch-up with pauses ≤20 ms or ≥200 ms). `runFrames` waits up to 260 ms before restarting: each call can cost ~0.3 s of clock.
- Minimum granularity: 1 frame (19656 cycles, PAL). `runCycles` rounds up. `step(n)` (API 6) runs single instructions but costs ~20 ms of clock each. NTSC not tested.
- The core runs in real time (≈985 000 cycles/s): 1000 frames ≈ 20 s of clock without warp.
- Determinism verified only as the hash of RAM `$0000–$07FF` after `reset()` + 300 frames (two identical sessions). The absolute number of cycles after `start()` is NOT reproducible (`start()` waits for the boot by the clock): use `pause()` + `reset()` + `runFrames` to start from a known state.
- Background tab: browser timers can slow down and stretch the wait times (not verified).

**CPU and debugger**
- Full `regs()`, `setRegs` and `call` run a 6502 stub in RAM (`$0334–$0367`, restored): ~40 cycles, they shift the emulated time. Change `scratch` if the program uses the cassette buffer. IRQ/NMI can fire during the stub (effect not measured).
- The core does not allow changing SP, nor A/X/Y/P directly (only PC and raster position from the debugger prompt). Since API 6 there are watchpoints (`watch`); the register printed by the shell `s` command has swapped nibbles (X=1 appears as "10") and is not used.
- `setRegs` and `call` must be used with the emulator stopped.
- The debugger stays active after the first use of `regs/breakpoint/runUntil({pc})/driveState`: performance impact not verified.

**Memory and I/O**
- `peek`/`poke` use the CPU view (honors `$01`). `{ram:true}` temporarily sets `$01` and restores it.
- Reading I/O registers (CIA `$DC00–$DD0F`, VIC) might have side effects (not verified); `$DC00`, `$D018`, `$DD00` were read without problems.
- I/O registers with unused bits read as 1 (`POKE $D020,2` reads back `$F2`).

**Input**
- With Fire or a direction on port 2 the keyboard receives ghost keys (shared lines, as on a real C64). Physical keyboard→joystick is disabled by default.
- Up/down and left/right share the axis: `joy(port,{...})` sends the releases first, then the presses.
- The key/joystick release is visible only at the next `runFrames` (emulator stopped).
- Letters in `type`/`sendText` are always without SHIFT: for graphics `type('a',{shift:true})` or `'SHIFT+A'`.
- Key times (BASIC, 8 phase shifts): press 1–4 frames with release ≥2 = all correct; release 1 = errors. Minimums: press 1, release 2; defaults 3 and 3.
- Autoload of a d64 after a BASIC line typed halfway (e.g. `"A"` without RETURN) can fail; the page clears `$D4/$D8` to mitigate, the residual case is not excluded.

**Screen, disk, ROMs**
- `screenText()` reads the VIC screen RAM: in bitmap mode or with a charset in RAM it is not meaningful (`screenInfo()`). Graphics appear as `▒`; reverse text is not distinguished.
- `driveState()`: LED not available; `track=(halftrack+1)/2` not verified. Drive 8 only.
- Drive: the core emulates only the 1541 family. Embedded: 1541-II (default) and original 1541 (`start({driveRom:'1541'})` or menu). Tested and NOT working: 1540 (stays at "SEARCHING"), 1570/1571 and 1581 (`?DEVICE NOT PRESENT`): 1571/1581, double side and MFM not available.
- The embedded VICE ROMs are used by default (user ROMs replace them).
- The `wasm_*` functions live in the emulator iframe, not in the page: use `c64.eval()` or the API. `wasm_get_cpu_cycles()` returns a BigInt: `cycles()` converts it to Number.
- No network requests (verified). Not tested on phone/iOS, nor the audio.

## API 6 changes
- `sendText(text,{framesPerKey:3,releaseFrames:3,keepCase,noWait})`: keys in the MATRIX (not `$0277`), queue in emulated time, with the emulator stopped it advances by itself. `\n`=RETURN, letters without SHIFT unless `keepCase`. Tokens: `{RUN/STOP} {F1}..{F8} {HOME} {CLR} {DEL} {INST} {UP} {DOWN} {LEFT} {RIGHT} {RESTORE} {SHIFT+A} {CTRL+3} {C=+Q} {WAIT:30} {{}`. Verified F1…F8 = 133,137,134,138,135,139,136,140, CTRL+3=28. Observed: `{LEFT}` 9 frames after `{UP}` lost in a BASIC program with GET (11 not), cause not verified: for slow programs `framesPerKey` 4–6 or `{WAIT:n}`. `keyNames()`.
- `saveState(name)`/`loadState(name|data)`/`states()`/`dropState(name)`: full snapshot (~790 KB) in JS memory; `{export:true}` → base64. Verified: identical cycles and screen after the restore. Not verified: survival of breakpoints/watchpoints.
- `watch(a)`/`watchpoints()`/`clearWatchpoints()`/`runUntil({watch})`: stop AFTER the accessing instruction (write and read verified), `reason:'watch'`, max 16.
- `runUntil`: `{pcIn:[a,b]}` (max 64), `{mem:[a,v,mask]}`, `{watch}`, `{pc, when:{addr,value}}`, options `{timeoutFrames, all:true}`.
- `step(n)`, `trace({until,max,last})`: single instructions `{pc,bytes,asm,cycles}`, ~20 ms each; post-mortem = `loadState` + `trace`. The register printed by the shell for `s` has swapped nibbles: not used (for registers `regs()`).
- `inspect(name)` (`vic cia1 cia2 cpu mem sid c64 drive8`) → `{config,state,raw}`; `sid()` registers + decoded voices; `sidTrace(frames,{every})`. No audio recording.
- `screenshot({rect,raw})`, `screenSave(name)`, `screenDiff(a,b,{tolerance,rect,image})`, `recordGif({frames,every,rect})`.
- `loadFile(...,{wait})`: with autoload it waits for the end of the reset+LOAD+RUN sequence (before it returned after 0.6 s and the autoload could reset the machine in the middle of a test); `{wait:false}` = old behavior; with the emulator stopped it does not wait.
- `reset({hard})`, `wasm(name,...args)`, `methods()`, `framesExact()`; `frames()` now integer. Errors with `e.code` (NOT_STARTED, NOT_READY, TIMEOUT, BAD_ARG, UNKNOWN_LABEL, NO_STATE, NO_SHOT, CORE; API 18: ABORTED, STALL, CALL_TIMEOUT, CLIENT_GONE); in postMessage also `code` and `method`.
- Already present before: `peekRange/pokeRange`, `cycles()`, `driveState`, `joy(port,state,frames)`, `warp`, `info`. Not done: drive CPU/memory, WAV audio, buffer of past instructions.
- Command line (optional, Node; `c64d` uses Playwright only internally for headless Chromium): `c64d.js --page FILE.html` + `c64 method args…`.

## API 7 changes
- `recordStart()`/`recordStop()`/`replay(rec,{toEnd})`: records the input calls (`keyDown keyUp joy sendText type sendJoy fire joyPulse poke pokeRange`) with the relative frame and repeats them. `recordStop()` → `{startCycles,frames,events:[{f,m,a}]}`. Exact replay with the emulator stopped and starting from the same state (`loadState`/reset). Verified: same state hash and same screen. Not verified in real time.
- `stateHash({only,exclude})`: hash per component from the core `checksums` command (Memory, CPU, CIA1/2, VIC, SID, Drive8…) + overall hash.
- `sprites()`: 8 sprites (enabled, x with bit 8, y, color, multicolor, expansions, priority, pointer, data address) + multicolor 1/2.
- `disasm(a,n)`, `find(bytes[]|text,{from,to,ram,screen,max})`, `ramSnap(name,{from,to})`, `ramDiff(a,b|null)`.
- `sendJoy("R10 UF8 W5",{port})`: directions U D L R + F for N frames (default 4), `Wn` wait.
- `storeSet/storeGet/storeDel/storeKeys/storeExport/storeImport`: JSON in localStorage (prefix `c64.store.`); across builds with different names only if the browser shares file:// (Chromium yes; Firefox/Safari not verified).
- Limits found: `wasm_rewind` = tape, not state; `HEATMAP` cannot be enabled with `wasm_configure`; the shell `d` accepts only the address (16 lines); `wasm_sprite_info` only x,y.

## API 8 changes: why `type()` lost characters
Cause (measured): the KERNAL reads the keyboard only after initialization, about 2.75 million cycles (≈140 frames) after a reset. Keys pressed before are lost: `reset()` + 20 frames = whole string lost, +80 = only the beginning, from +140 nothing. Real time and Playwright have nothing to do with it (with the prompt ready no loss). It also happens with interrupts disabled (verified: a BASIC program that stops the CIA timer loses the whole string typed while waiting), disk loads, programs that do not consume keys.
Since API 8 `type` and `sendText` wait for the boot after a reset by themselves (`{noWait:true}` to disable). In the other cases wait for the prompt first (`runUntil({screenText:'READY.'})`).

## API 9 changes: keyboard
Two commands: `type` for **a key** (or several simultaneous keys) and `sendText` for **strings**. `key()` removed, the old `type(string)` no longer exists (no backward compatibility). Both press in the C64 matrix with the same times: `frames`/`framesPerKey` (press, min 1, default 3), `releaseFrames` (min 2, default 3); lower values → `BAD_ARG`.
Limits:
- Several simultaneous keys: in the matrix yes (verified on `$DC00/$DC01` with CIA stopped: `[WD]`), but the KERNAL (`GET`) reports only one key per scan (with W+D only D).
- Ghosting (3 keys at the corners of a rectangle activate a fourth) and lines shared with the joysticks: on a real C64; whether the core emulates them is not verified.
- Keys lost if the C64 does not read the keyboard: boot after reset (automatic wait), interrupts disabled, LOAD running, programs that do not read keys.
- Measured times (BASIC, 8 phase shifts): press 1–4 with release ≥2 = ok; release 1 = errors. A program sampling every N frames needs press ≥ N.
- Real time: tested with `type` and `sendText` (GET, F1, SHIFT+A, W+D, ~130 characters in ~10 s): as with the emulator stopped; the wait uses the cycle counter. Not tested: background browser, warp, NTSC.
- Characters that cannot be typed (`{ | ~`): `BAD_ARG`; `\` → pound, `_` → left arrow.

## API 10 changes: regression, screenshots and video
`regressSave(name,{ram,screen,only,exclude})` records a baseline (component hashes, RAM, PNG screen, cycles) and returns the JSON bundle. `regressCheck(name|bundle|JSON,{ignore,tolerance,only,exclude,ram,screen,strict,includeCpu,image,maxGroups})` compares and returns `{pass,reasons,hash,ram:{groups},screen:{diffPixels,bbox,image}}`. `regressList()`.
Limits: CPU hash excluded (unstable, depends on the debugger history) unless `includeCpu:true`; baseline and test must start from the same deterministic state (`loadState` + same inputs with the emulator stopped).
Screenshots: `screenshot`, `screenSave`/`screenDiff`. Deterministic animation: `recordGif`. Video: `recordVideo({frames|seconds,fps,mime,bitrate,scale})` → `{data(base64),mime,bytes,frames,width,height}` via `MediaRecorder` (WebM VP9/VP8). `scale` = integer 1-4 (zoom without interpolation: 3 → 1152×810, 4 → 1536×1080, about full HD; beyond is not allowed); `bitrate` (bit/s, default 2,500,000) is only a request to the encoder: measured at scale 3, 60 frames, 8 Mbit/s produced a smaller file (52 KB) than the default (66 KB), so it is not a quality guarantee. No CRF/keyframes/preset (not exposed by `MediaRecorder`). Limits: real-time encoding (not deterministic, ≈2 s per 100 frames even with the emulator stopped), no audio, 384×270 (× scale), requires `MediaRecorder` (`UNSUPPORTED`), tested only on Chromium.
```sh
c64 regress save base --out base.json
c64 regress check @@base.json --out diff.png      # exit 0/1
c64 --out clip.webm recordVideo '{"seconds":3}'
```

## Input scripts (API 11)
`runScript(text,{noWait})` runs a sequence of inputs described in a text file; `scriptCheck(text)` only validates (errors with line number). From the shell: `c64 script file.txt`, `c64 scriptCheck file.txt`.
```
# comment (also at the end of a line)
0   L              # <frame> <input> [duration]
140 O
280 A
300 JOY2-UP 30     # joystick 2 up, held 30 frames
+100 JOY2-FIRE     # +N = N frames after the previous line
wait "READY." 5s   # waits for the text on screen (timeout: frames, or seconds with s; default 3000 frames)
0 text "print 6*7\n"
wait 50            # waits 50 frames
wait pc=0xC000 600
```
- Time is in PAL frames from the start of the script, **after the automatic wait for the boot** (like `type`/`sendText`; `{noWait:true}` to disable it). After each `wait` time restarts from 0. Lines between two `wait`s must be in increasing frame order.
- Input: a key (`L`, `RETURN`, `F1`, `SHIFT+A`, `RUN/STOP`: same names as `type`), simultaneous keys with `&` (`W&D`), `JOY1-` or `JOY2-` + `UP|DOWN|LEFT|RIGHT|FIRE` (also with `&`; keys and joysticks are not mixed on the same line), `text "string"` (JSON string: `\n` = RETURN; same rules as `sendText`, optional duration = frames per key).
- Duration: press frames, default 3, minimum 1. A key pressed again less than 2 frames after the release produces a warning (measured: release too short = lost presses).
- `text` blocks the script until the string is typed: the following events already due start immediately.
- Before starting, the whole script is validated (unknown key, invalid duration, lines out of order, malformed `wait`).
- No `if`/`goto`/loops/variables/`include`: for logic use a JavaScript script with the API (`runUntil`, `screenText`, ...).
- **Since build 19 (API 15) scripts also have commands** (`poke`, `assert`, `wait mem=`, `saveState`/`loadState`, `screenshot`, `regress`, `call`, `video start|stop`, `rec start|stop`): see `scripting.md` (complete guide with examples).
- Returns `{events,frames,warnings}` (plus `outputs`, `log`, `videoOpen`, `recOpen` if commands are used). Tested with the emulator stopped and in real time (L-O-A, joystick up/fire/left+fire read from `$DC00`, `wait` on text with timeout, syntax errors). Not tested: very long scripts, `wait pc=`.
- `runScript` is recorded by `recordStart` as a single event.

## API 14 changes: tools for long tests and videos
**`runLoop(code,{frames,every})`**: runs a control loop INSIDE the page (no HTTP call per step). `code` is the body of a JS function with parameters `(c64,i,state)`; `return false` ends it; `every` = frames per step (default 2), `frames` = maximum. From the shell: `c64 runLoop 'code' '{"frames":600,"every":2}'`.
Measured: 300 steps of 2 frames in 12.2 s (≈ real time, 25 steps/s) against 3 steps/s with one HTTP call per step (`runFrames` via HTTP waits ~0.26 s: it avoids losing frames after a core pause). The loop is limited by the emulator real time (unless warp is used, not exact).
```
c64 runLoop 'const hp=c64.peek("c_hp"); if(hp===0) return false; c64.joy(2,{right:true},2);' '{"frames":3000}'
```
**Inside `runLoop`, `joy(port,state,frames)` does not advance the emulator** (API 18): it presses immediately and releases after `frames` frames of the loop; no `await` needed. Outside `runLoop` it is as before (returns a promise that advances `frames` frames). Before, inside `runLoop`, it ran its own `runFrames` concurrently with the one of the loop and the loop never returned (reproduced: timeout at 60 s).
**Deterministic video with inputs: `c64 video`**. Screenshots are captured inside the page every `every` emulated frames while an input script, a JS loop or N frames run; the daemon encodes them with **ffmpeg** (libx264, must be in the PATH: the Dockerfile installs it). Requires the emulator stopped (`pause`). No skipped frames, no dependency on real time.
```
c64 --out clip.mp4 video test.txt                     # input script (.txt)
c64 --out clip.mp4 video bot.js '{"loopOpts":{"frames":3000}}'   # JS loop in the page (.js)
c64 --out clip.mp4 video 500                            # 500 frames without input
```
Options (JSON): `every` (2 = 25 fps), `fps` (default 50/every), `scale` (1-4, sharp pixels, default 3 = 1152×810), `crf` (x264 quality, default 20), `preset`. The file reaches the client (`--out`). No audio. Underlying methods, usable also from code: `capStart({every})`, `capRun('script'|'loop'|'frames',arg)`, `capTake(n)`, `capStop()`. Tested: 350-frame script (178 images) and a loop that stops on a screen text, in mp4 H.264. Not tested: durations of tens of minutes (images not yet encoded wait in a queue, max 200).
**`runFrames(n,{fast:true})`**: exact also with warp. The bulk runs in warp, the last 70 frames at normal speed (plus a step that absorbs the warp latency). Measured: 500 frames in 0.64 s (normal: 10 s), 1500 in 2.2 s (normal: 30 s), difference from the expected cycles 0 in all tests, same `stateHash` as normal mode. Below 140 frames it does not use warp. If the margin is not enough it returns `exact:false`.
**Warp: exit latency (measured)**: after `warp(false)` the FIRST `runFrames` still advances at warp speed (+26 frames in one test). A `loadState` right after cancels it. In warp `runFrames(30)` ran 53. That is why plain warp is not exact: use `{fast:true}`.
**`stateHash`**: the CPU component depends on the debugger history (the first call after the debugger starts differs from the following ones, while Memory, VIC, SID, CIA and drive are identical): the overall hash now **excludes** it (`includeCpu:true` to include it). Components are always listed.
**Label sets** (modules/overlays with different addresses): `loadLabels(text,{set:'lobby'})` creates a set and activates it (`activate:false` not to activate it); `useLabels('lobby')`; `labelSets()`; from any set read with `lobby:name` (e.g. `peek('lobby:read_input')`).
**`runUntil({screenMatch:'name',maxDiff:0,tolerance:0,rect})`**: waits for the screen to match a screenshot saved with `screenSave` (at most `maxDiff` different pixels). Useful for games with their own fonts and bitmaps, where `screenText` does not help.
**`driveTrace(frames,{every,drive})`**: head history (track, half track, offset, motor, sync) sampled every `every` frames; the LED is not exposed.
**`recordStop({format:'text'})`**: exports the recording as an input script (`{text,frames,events,notExported}`). Converts `type`, `sendText` and `joy(port,state,frames)`; everything else (poke, state joy, sendJoy, runScript...) becomes a `# not exported` comment. Time is from the start of the recording: start it after the boot.
**`loadFile`/`start` with `program`**: the name is converted to lowercase (the program is loaded by typing `load"name*"` on the keyboard: the uppercase name would produce PETSCII graphics and `FILE NOT FOUND`).
**States to files**: already possible: `c64 --out s.state saveState name '{"export":true}'` and `c64 loadState @s.state` (tested: identical cycles after reloading).
**Client**: `--quiet` (no output, only errors and exit code) and `--compact` (JSON on one line).
Not done: audio (neither in the video nor WAV), several instances in parallel, per-routine profiler, conditional breakpoints on registers.

## API 15 changes: commands in scripts
Details and examples in **`scripting.md`**. Summary: `poke ADDR v,..`, `assert mem=ADDR VAL [&MASK]` / `assert screen "t"` (error `ASSERT`), `wait mem=ADDR VAL [&MASK] [timeout]`, `saveState/loadState NAME`, `screenshot FILE`, `regress save|check NAME` (error `REGRESS`), `call ADDR [a= x= y=]`, `video start [NAME] [every= scale= crf=] [keep]` / `video stop`, `rec start [NAME] [keep]` / `rec stop`. Without `keep` the closing of video and recording is guaranteed at the end of the script (also on error); with `keep` they stay open and are closed by hand (`c64 --out f.mp4 videoStop`, `c64 recordStop '{"format":"text"}'`).
Video in scripts requires the daemon (uses `capArm`/`capClipStop` + ffmpeg) and the emulator stopped. Client: `--outdir DIR` writes the produced files (screenshots, videos, recordings) even if the script fails. A script error carries `outputs` and `log` (`e.outputs`, `e.log`).
**Audio in the video: not done.** Measured: `wasm_copy_into_sound_buffer` returns blocks of 1024 samples, ~79k samples per 100 frames (88.2k expected at 44.1 kHz), amplitude ~0.002 with a SID tone on, and it changes after `wasm_open_main_thread_audio`: not deterministic. Alternative not tested: synthesize the SID offline from the registers (`sidTrace`). Real-time audio is instead available with `grabBrowserVideoAndAudio` (API 16).

## API 16 changes: `grabBrowserVideoAndAudio` (browser video + audio, real time)
Recorder **independent of the emulator**: a browser `MediaRecorder` (encoding in its own thread) captures the canvas and the page audio into a single `.webm` (VP9 + Opus). It does not use `run0`/`runFrames`, does not stop nor advance the emulator and is not synchronized with emulated time: the emulator must run in real time (`resume()`); with the emulator stopped the video is a still image (warning in the result). **Not deterministic**; the deterministic recording (`c64 video`, `video start` in scripts) stays as it is, but silent.
```
c64 grabBrowserVideoAndAudio '{"action":"start","keyboard":"below","joy2":"below"}'
... (use the emulator normally, also with c64 script)
c64 --out clip.webm grabBrowserVideoAndAudio '{"action":"stop"}'
c64 --out clip.webm grabBrowserVideoAndAudio '{"seconds":10,"joy2":"overlay"}'   # starts, waits 10 s, stops (blocks the daemon for 10 s)
```
Options: `action` (`start`|`stop`|`status`; with `seconds` it records and stops by itself), **`keyboard`, `joy1`, `joy2`** (each `none` default | `below` | `overlay`, independent), `scale` (1-4, default 2), `fps` (50), `bitrate` (4000000), `audio` (true), `audioGain` (API 18, default 1: gain applied only to the recording; the core audio is very low), `mime`. `stop` returns `{data(base64),mime,bytes,seconds,width,height,audio,audioPeak,controls,warnings}`; `audioPeak` is the peak (0-1) of the recorded signal: ~0 = silence.
**Command panel** (pressed keys and joysticks, live), one choice per element: `none` = not shown; `below` = in the panel below the video (the video becomes taller): first the joysticks (each with **FIRE on the left, cross stick on the right**), below the full C64 keyboard; `overlay` = over the screen, semi-transparent (keyboard 50%, joysticks 65%), video size unchanged. In overlay the stick is drawn as **two circles** (base + knob moving in the pressed direction, orange) and FIRE is a circle (red when pressed). Position in overlay: keyboard bottom left, joysticks bottom right (FIRE to the left of the stick); **if the keyboard is not in overlay and there is only one joystick in overlay**, FIRE goes in the bottom-left corner of the screen and the stick bottom right (enlarged); if it is not in overlay and there are two joysticks in overlay, joy1 is on the left and joy2 on the right (each with FIRE to the left of the stick; this case is my interpretation, not specified). Examples: `{"keyboard":"below","joy1":"below","joy2":"below"}`, `{"joy2":"overlay"}`, `{"keyboard":"overlay","joy1":"overlay","joy2":"overlay"}`. What goes through `wasm_schedule_key` and `action` lights up (API, scripts, virtual keyboard and joysticks of the page). Delayed keys (`delay`) are shown at clock time (20 ms per frame), so in real time they are aligned, with the emulator stopped/warp they are not.
Measured (headless Chromium, no sound card): the page AudioContext is `running`, the audio track is present and a SID tone that is on shows up in the file (`max_volume` ≈ −19 dB with `volumedetect`); video 768×870 with keyboard and joysticks `below`, 768×540 with `overlay`/`none` at scale 2. **Not verified**: long durations (block memory), fine audio/video sync (drift possible: two clocks), audio with audio disabled by the page (`gainNode` missing → video only, warning), virtual keyboard/joysticks of the full page. Conversion: `ffmpeg -i clip.webm clip.mp4`.

## API 17 changes: alternative ROMs
`loadRom(kind,data,{name})` (kind `kernal` 8192 bytes | `basic` 8192 | `chargen` 4096 | `floppy` 16384), `clearRoms([kind])`, `roms()` (active user ROMs), `start({roms:{kernal:..}})`. Effective from the next `start()` (when started: `stop`, `loadRom`, `start`). Client: `c64 roms [filter]` lists the files in `roms/vice-roms` and `$C64_ROMS`; `c64 rom kernal 251104-04` loads by part of the name (`drive` = `floppy`).
Tested: all the VICE C64 Kernals (`901227-01/-02/-03`, `251104-04` SX-64, `390852-01` Games System, `901246-01` 4064, `906145-02`) and the chargen `906143-02` start; drives: `1541` and `1541-II` work (LOAD"$",8 + LIST from a test D64); `1540`, `1551`, `2031` (16 KB) stay in LOADING (test interrupted at 2500 frames); `1570/1571/1581` (32 KB) are refused (the core emulates only the 1541 family). JiffyDOS and similar: cannot be provided from here (proprietary); with your own copy it loads as a user ROM, but it is **not verified** that the core accepts it nor that it works. Third-party ROMs are not verified for license: `roms/roms.md`.

## Misc
`eval(code)` runs JS in the emulator context (`wasm_*` functions, `action(...)`, ...). `sleep(ms)`.

## `postMessage` channel
For a container page or a bridge: send `{c64:'call', id, method:'peek', args:[49152]}` to the page window;
the answer goes back to the sender as `{c64:'result', id, ok:true, value}` or `{c64:'result', id, ok:false, error}`.

## Examples (command line)
```sh
c64 dump 0x0400 64                 # screen, first 64 cells
c64 peek 0x2B 2                    # pointer to the BASIC start
c64 poke 0xD020 2                  # red border
c64 loadFile game.d64 @game.d64 '{"autoload":true,"program":"GAME"}'
c64 pause; c64 runFrames 200
c64 runUntil '{"pc":"read_input","when":{"addr":"cur_level","value":0}}'
c64 saveState before; c64 trace '{"until":"read_input","last":8}'
c64 screenSave a; c64 sendText x; c64 screenDiff a null
c64 --out clip.gif recordGif '{"frames":60,"every":2}'
c64 --out disk.d64 diskImage
```

## API 18 changes: fixes from field tests
**Serialized runs.** `runFrames`/`runUntil`/`call`/`runScript` etc. go through an internal queue: one at a time. Before, two concurrent `runFrames` stopped each other (the `halt()` of the first left the second waiting for cycles that never came). Moreover: if the core does not advance for 5 s during a run, error `STALL` (instead of waiting forever).

**Interrupting a job: `abort()`, `c64 abort`, client disconnection.** `c64 abort` (POST `/abort`, bypasses the queue) interrupts the running job (`runFrames`, `runUntil`, `runLoop`, script, video): error `ABORTED` to the client of that job; the emulator stays stopped; the queued jobs continue. If the client is closed or killed while waiting, the daemon does `abort` by itself (if the job was still queued it is skipped, `CLIENT_GONE`). No more `pkill -9` needed. Tested: a 200000-frame runFrames stopped in <1 s; client killed with SIGKILL, daemon free again.

**State of long jobs: `c64 status`** (GET `/status`, bypasses the queue, works while another client is waiting): `{busy, method, elapsedMs, queued, progress:{frozen,cycles,run:{frames,of},loop:{iterations,frames,of}}}`. `progress()` is also an API method.

**`call(a,r,{timeoutFrames,noWait,frames})`.** If the routine does not return: error `CALL_TIMEOUT` with a clear message (address, PC, hint); only PC and the work area (`$0334`) are restored, not the registers. `{noWait:true,frames:N}` (default 2): jumps to the routine with `JMP` (input registers a/x/y), lets it run N frames and returns `{started:true,pc,frames}` without waiting for the return: for routines that do not return (e.g. level change). In a script: `call ADDR nowait`. With `noWait` the `$0334` scratch is not restored and the core continues from the routine.

**Text in screen code: `findText(text|codes,{raw,all,exact})`, `screenCodes()`, `runUntil({text})`, script `wait text "TEXT" [timeout]`.** Searches the screen RAM chosen by the VIC as screen code, not as KERNAL text: it works also with custom charsets if the codes are the standard ones (A-Z = 1-26, 0x20-0x3F as ASCII). Letters case insensitive, bit 7 (reverse) ignored unless `exact`. For codes of a custom font: array (`findText([18,5,1,4,25])`). Returns `{row,col,addr}` (rows and columns from 0) or `null`; `all:true` → list; the match is within a line. Limits: does not see graphic glyphs nor text drawn on the bitmap; not verified with a game using non-standard codes. Tested: READY., COMMODORE, missing → `null`, `runUntil`, `wait text` (ok and timeout).

**`grabBrowserVideoAndAudio({audioGain})`.** Gain applied only to the recording (default 1). Measured: the core audio is very low (peak ~0.002 = about −54 dBFS with a SID tone: see also API 16); with `audioGain` 8 and 30 the peak rises by about +19 and +31 dB as expected. Which value to use depends on the game: check `audioPeak` in the result (0–1; close to 1 = clipping). Not verified whether the low level depends on the core SID or on a page gain.

**Clarifications (they were not API bugs).**
- `runUntil({timeoutFrames})`: 3000 is only the **default**, not a limit; tested with 4000 (expires after 4000 frames = 80 s in real time).
- **The deterministic video runs in real time**: 200 emulated frames (`every=2`) ≈ 4–5 s of clock, also at scale 1; a bot with `joy` of 302 frames: 6.4 s. The "9 minutes" observed were the `joy` block in `runLoop` (above), not the capture. There is no way to go faster than real time while capturing (warp is not used with capture active); measured only at scale 1 and 3 and without a real game.
- `POKE` before `loadFile` with autoload: the autoload does a reset, so the `poke`s done before are lost (expected behavior). Do the `poke` **after** `loadFile` returned (it waits for the end of the autoload) or use `{autoload:false}`.
- Real-time recording (`grabBrowserVideoAndAudio`) with the core stopped: the clip is a still image (the result contains a warning).
- Not investigated: maximum hero life 198 against 192 in the game documentation (it concerns the game, not the emulator).

## API 25 changes
- `runLoop` returns `retriesTotal` (true total) and `retriesTruncated` (the `retries` list stops at 200 entries: with 300 forced steps it showed 200, reported by a project chat). `c64-batch`: `retriesCount` from the true total and `retriesTruncated`.
- Documented the test options `_forceRetry`/`_forceEvery` to check that a bot is repeatable.
- Measure of the cost of the exact step: the extra time comes from the core after the restore (see `c64-cli.md` §14).

## API 24 changes
- **Fix (R12)**: with the repetitions of exact steps API 23 lost held joysticks and keys (the core does not save them in the snapshot) → different outcomes. Now: input model reapplied at each restore, first attempt always from a restored state, consumed keyboard events rescheduled. `type()` inside `runLoop` does not advance the core and leaves no events in the core queue.
- `saveState(name)` also saves the held inputs (in memory only); `loadState(name)` restores them, `loadState(file/base64)` releases them all; warning if there were keyboard events still scheduled (the core queue is not emptied).
- **R13**: `examples/shell/11-determinism.sh` rewritten with a target that reads joystick and keyboard and forced repetitions.
- **R14**: `loadEncoding` accepts symbols (`NAME = value`, labels) and `.enc` blocks; option `{block}`.
- **R15**: script `assert text "…" [enc=] [addr=] [len=]`.
- **R16**: `c64-batch` reports `retriesCount` (with the fix the repetitions no longer change the outcome: no warning needed).

## API 23 changes
- **Exact steps**: `runFrames` and `runLoop` take a snapshot before each advance (≈5 ms) and, if the core overshot (a late browser makes it compute 2 frames in one go: measured ~1 step in 800–1000, more often with several instances), restore and repeat. Closed-loop bot from the same state ⇒ same outcome. `runLoop` returns `framesActual`, `exact`, `retries`. `{exact:false}` = previous behavior. In exact mode the first attempt skips the anti-catch-up wait (260 ms), the repeated ones do not.
- `loadEncoding(name, map|.cdef text)`, `encodings()`, `findText(…,{enc,len})`, `runUntil({text,textOpts:{enc,addr,len}})`, script `wait text "…" enc= addr= len=`.
- `headless/c64-batch`: several runs on several daemons in parallel (see `c64-cli.md` §14).
- Error message for `JOY2-UP&FIRE` in scripts: suggests `JOY2-UP&JOY2-FIRE`.
- Not feasible with this core (measured): synchronous run faster than real time (no exported wasm function; `SPEED_BOOST` has no effect), per-routine profiler (it would need a per-instruction hook: with breakpoints/step it costs ≥45 ms per event), fast `whenRegs` (`r` of the RetroShell shows only CIA/VIC/SID, not the CPU registers).

## API 22 changes
- `measure(from,to,{n})`: `n` repetitions with `{min,max,mean,samples}`.
- Determinism verified (without the game): same saved state + same `runLoop` with a bot that decides by reading memory → same cycles and same `regress` hash, 3 times out of 3. If a game gives different outcomes from the same state, the cause is not in the `runLoop` itself; see `getting-started.md` §7.
- Examples: the output of the shell scripts goes to `$TMPDIR/c64-examples-output` instead of the package.

## API 21 changes
- `findText(text,{map})`: game's own encoding (`{"0-9":45,"/":55}`); works also in `runUntil({text,textOpts:{map,addr}})`.
- `measure(from,to,{timeoutFrames})`: exact cycles between two PCs (via `runUntil` on breakpoints).
- `runUntil({pc, whenRegs:{a,x,y,p}})`: stop on the PC only with the given registers.
- Client: `c64 games` looks for `games/` also next to the repository (not only in the current folder).
- Verified that warp does not help step-by-step loops: after `warp(true)` each `runFrames` advances in jumps of ~26 frames (measured: 2→27, 2→26, 2→52), so `runLoop` in warp is neither exact nor fine; `runFrames(n,{fast:true})` stays the only exact use.

## API 20 changes
- `screenCodes({addr})`, `findText(text,{…,addr})`: `addr` = RAM address of the 1000 screen codes (default: the VIC one from `$D018`/`$DD00`). If `findText` returns `null` on a game screen, check `screenInfo()`: with `bitmap:true` the text is drawn as graphics and does not exist in the screen RAM; otherwise try `addr` with the address of the game's text RAM (`c64 dump`/`screenCodes` to locate it). The daemon has the `--headed` option (see `docs/c64-cli.md` §2).

## API 19 changes: fixes found while documenting every command (`docs/c64-cli.md`)
- **`reset({hard:true})`** gave `w.wasm_hard_reset is not a function` (it used the wrong name): now it really powers off/on (the cycle counter restarts from 0; tested).
- **The daemon crashed** if a result contained a BigInt (e.g. `c64 wasm wasm_get_cpu_cycles`: `TypeError: Do not know how to serialize a BigInt`): now BigInts become numbers (strings beyond 2^53) and a non-serializable result gives a `DAEMON` error instead of stopping the daemon.
- **`roms()`**: bytes were overestimated by 1 (8193 instead of 8192).
- **Client**: `c64 rom` without arguments shows the active user ROMs (`roms()` of the API; `c64 roms` stays the file list); `c64 rom KIND NAME` passes the file name to the loaded ROM (before `name:"kernal"`).
- **Documentation**: `docs/c64-cli.md` (every command), `examples/` (runnable examples). Clarified that JSON objects/arrays do not accept `0x..` as a number, that disks are attached with the core running and that `waitFor` returns `false` on expiry.
