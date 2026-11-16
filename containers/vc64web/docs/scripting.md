# Scripting — guide to the c64d script language

Copyright © 2026 Simone Caporale · version: `c64.info()`

A script is a text file that describes **timed inputs** (keys, joystick, text), **waits**, **checks** (assert, regression), **memory changes** and **recordings** (video, inputs). It runs inside the emulator with exact emulated time: same script + same initial state = same result.

```
c64 scriptCheck test.txt                      # validation only (errors with line number)
c64 script test.txt                           # runs it
c64 --outdir out script test.txt              # runs it and saves screenshots / videos / recordings in out/
```
Exit code: 0 = ok, 1 = error (syntax, `ASSERT`, `REGRESS`, `TIMEOUT`, `CALL_TIMEOUT`, `ABORTED`, `STALL`, ...). The message always contains the line number: `ERROR ASSERT: script line 12: assert failed: mem[$0400]=$05, expected == $06`.
From JavaScript: `await c64.runScript(text)` / `c64.scriptCheck(text)`.

---

## 1. Time model

- Time is in **PAL frames** (19656 cycles) from the start of the script, after the automatic boot wait (the KERNAL scans the keyboard only after ~2.75 M cycles from reset; `{noWait:true}` disables it).
- Line with a time: `<N>` = absolute, `+<N>` = N frames after the previous line. Lines must be in increasing order.
- **Sequence points**: `wait ...` and every command **without** a frame in front (see §4) wait for the previous events (key releases included) to finish; then **time restarts from 0**.
- Commands can also have a frame in front (`120 screenshot s1`): then they fire at that time, without breaking the segment and without resetting time (except `loadState`, which wants the form without a frame).
- There are no `if`, `goto`, loops, variables, `include` (design choice: for logic use JavaScript, see §9).

## 2. Input

| Line | Meaning |
|---|---|
| `0 L` | key `L` pressed at frame 0 (default duration 3 frames) |
| `140 O 5` | key `O`, pressed for 5 frames (minimum 1) |
| `10 SHIFT+A` · `10 RUN/STOP` · `10 F1` | same names as `c64.type()` |
| `10 W&D` | simultaneous keys with `&` |
| `300 JOY2-UP 30` | joystick port 1 or 2: `UP DOWN LEFT RIGHT FIRE`, also with `&` |
| `0 text "print 6*7\n"` | JSON string (`\n` = RETURN), like `sendText`; optional duration = frames per key |
| `# ...` | comment (also at the end of a line) |

Keys and joystick do not mix on the same line. `text` blocks the script until the string is typed. A key pressed again less than 2 frames after its release gives a warning (measured: lost presses).

## 3. Waits

| Line | Waits for |
|---|---|
| `wait 50` | 50 frames |
| `wait "READY." 5s` | text on the screen (case-insensitive). Timeout in frames, or seconds with `s`; default 3000 frames |
| `wait pc=0xC000 600` | PC at the address (or label) |
| `wait text "TEXT" 5s` | text in the screen RAM as **screen code** (API 18): it also works with custom charsets; see `findText` in C64-API.md |
| `assert text "XP" enc=hud addr=$8400` | (API 24) like `wait text` but with no wait: `ASSERT` error at once if the text (screen code) is not there; options `enc= addr= len=` |
| `wait text "LV 21" enc=hud addr=$8400 3000` | (API 23) with a loaded encoding (`loadEncoding`), area (`addr=`, also a label) and linear length (`len=`) |
| `wait mem=0x02A7 0x03 600` | `mem[addr] == value` |
| `wait mem=lives 0 &0x0F 10s` | with a mask: `(mem & 0x0F) == (value & 0x0F)` |
| `wait mem!=0x02A7 0` | `mem[addr] != value` |

When the timeout expires: `TIMEOUT` error with the line number (exit 1). Addresses: `0x..`, `$..`, decimal or **labels** loaded with `c64.loadLabels` (also `set:name`). Memory is read as the CPU sees it (I/O and ROM visible according to `$01`).

## 4. Commands

They are written on their own (sequence point, then time restarts from 0) or with a frame in front.

| Command | Effect |
|---|---|
| `poke ADDR v1,v2,.. [ram]` | writes bytes (0-255). `ram` = writes into the RAM under ROM/I-O |
| `assert mem=ADDR VALUE [&MASK]` | if false: `ASSERT` error, script interrupted. Also `mem!=` |
| `assert screen "text"` | the text must be on the screen (case-insensitive) |
| `saveState NAME` · `loadState NAME` | full core snapshot in memory (CPU, RAM, VIC, SID, CIA, drive, disk). `loadState` also restores the cycle counter |
| `screenshot FILE` | PNG (`.png` extension added if missing), saved by the client in `--outdir` |
| `regress save NAME` | baseline (component hashes + RAM + screen) |
| `regress check NAME [tolerance=N] [ignore=A-B ...]` | compares with the baseline; if different: `REGRESS` error with the reasons. `ignore=0x0400-0x07E7` excludes ranges |
| `call ADDR [a=N] [x=N] [y=N] [timeout=N] [nowait]` | JSR to a subroutine and return (registers and PC restored); output registers in the `log` field of the result. With `nowait` (API 18) it jumps to the routine without waiting for the return: for routines that never return (level change); the core goes on from there. If the routine does not return and `nowait` is missing: `CALL_TIMEOUT` error. |
| `video start [NAME] [every=N] [scale=N] [crf=N] [keep]` | starts recording an mp4 video (see §5) |
| `video stop` | closes the video |
| `rec start [NAME] [keep]` · `rec stop` | records the script inputs as a text script (see §6) |

Names (states, baselines, files) can contain only letters, digits, `_`, `.`, `-`. States and baselines live in the page while the daemon stays up: they can be reused across different scripts.

## 5. Video: `video start` / `video stop`

```
video start intro every=2 scale=3          # intro.mp4, 25 fps, 1152x810
...
video stop
```
- **Deterministic** capture: one screenshot every `every` emulated frames (default 2 → 25 fps; `fps = 50/every`), encoded by ffmpeg in the daemon. The video does not depend on the computer speed.
- `scale` 1-4 (integer scaling with sharp pixels, default 3; 4 = 1536×1080), `crf` 0-51 (H.264 quality, default 20, lower = better).
- **Requirements**: `c64d` daemon with `ffmpeg` in the PATH and **emulator stopped** (`c64 pause`). Calling `runScript` directly from JavaScript without the daemon: `NO_RECORDER` error.
- One active video at a time (a second `video start` without a stop is a syntax error).

### Closing parameter: autostop (default) or `keep`
| Form | What happens at the end of the script |
|---|---|
| `video start clip` (= `autostop`) | **closing is guaranteed**: if there is no `video stop`, the video is closed at the end of the script, **even if the script ends with an error** (the partial file is saved anyway) |
| `video start clip keep` | the video **stays open** after the script and keeps recording every emulated frame of the following calls (`runFrames`, other scripts, ...). Stop it by hand: `c64 --out clip.mp4 videoStop`, or with `video stop` in another script (then the file comes out among that script's `outputs`) |

With `keep` the script result contains `"videoOpen": "clip.mp4"`. If the script that started a `keep` fails, the video stays open (close it with `videoStop`).
Without the `--out`/`--outdir` destination the client saves nothing: remember to pass it.

## 6. Input recording: `rec start` / `rec stop`

It records the input events executed from that point (keys, joystick, script `text` and the input API calls made later with `keep`) and exports them as a re-runnable **text script** (`recordStop({format:'text'})`).
```
rec start session            # session.txt
...
rec stop                     # (or autostop at the end of the script; with keep it stays active)
```
Same closing rule: default = closed at the end of the script (also on error); `keep` = stays active and is closed with `c64 recordStop '{"format":"text"}'`. Events that cannot be written as a script line (e.g. `poke`) end up as a `# not exported` comment. Verified: the export of keys, joystick and `text` reads back without errors with `scriptCheck`.
Remember that the exported time is relative to the start of the recording.

## 7. Result and produced files

`runScript` returns `{events, frames, warnings, outputs?, log?, videoOpen?, recOpen?}`.
- `outputs`: screenshots, videos, recordings (with the binary data). The `c64` client writes them in `--outdir` (default: current folder), with the file base name only, and removes them from the printed JSON.
- `log`: results of `call` and `regress check`.
- On error the client still writes the files already produced (also the partial video) before exiting with 1.

## 8. Practical examples

### 8.1 Loading and starting a program
```
wait "READY." 10s
0 text "load\"*\",8,1\n"
wait "READY." 30s
0 text "run\n"
wait 200
screenshot start
```

### 8.2 Testing a game: save the state after the menu, then try different moves
```
# prepare.txt  (run once)
wait "PRESS FIRE" 20s
0 JOY2-FIRE 5
wait mem=0x0800 1 30s          # 1 = level loaded (example address)
saveState level1
```
```
# try_jump.txt
loadState level1
0   JOY2-RIGHT 40
+10 JOY2-FIRE 6
wait 60
assert mem=0x0801 0x03          # e.g. "in the air" flag = 3
screenshot jump
```
A `loadState` instead of a reset makes every try independent and very fast.

### 8.3 Forcing a condition and checking the effect
```
loadState level1
poke 0x0802 99                  # lives = 99 (example address)
0 JOY2-LEFT 30
wait 100
assert mem=0x0802 99            # lives must not change while walking
assert screen "SCORE"
```

### 8.4 Regression after a code change
```
# 1) with the good version
loadState level1
0 JOY2-RIGHT 100
wait 50
regress save walk
```
```
# 2) with the new version (same starting state)
loadState level1
0 JOY2-RIGHT 100
wait 50
regress check walk ignore=0x0400-0x07E7 ignore=0xD800-0xDBE7
```
`c64 script ...; echo $?` → 0 if equal, 1 if different: usable in CI.

### 8.5 Calling a routine of the program
```
loadState level1
call 0xC000 a=3                 # JSR $C000 with A=3
call spriteInit x=1 y=2         # with a label (loadLabels)
```
The result (a, x, y, p on exit) is in `log`.

### 8.6 Video of a session, guaranteed close
```
video start demo every=2 scale=3
wait "READY." 10s
0 text "10 for i=1 to 5:print i:next\n"
+80 text "run\n"
wait 150
```
It ends without `video stop`: `demo.mp4` is closed anyway at the end of the script.
```
c64 pause ; c64 --outdir out script demo.txt
```

### 8.7 Video that goes on after the script (`keep`) and manual close
```
video start long keep
wait "READY." 10s
0 text "run\n"
```
```
c64 script start.txt                       # -> "videoOpen":"long.mp4"
c64 runFrames 500                          # these are recorded too
c64 sendText 'print 1\n'
c64 --out long.mp4 videoStop               # stops and saves
```

### 8.8 Several clips in one script
```
video start part1 every=2
...
video stop
loadState level2
video start part2 every=1 scale=2
...
video stop
```

### 8.9 Recording your own moves and replaying them
```
rec start moves keep
```
then play through the API (`c64 type ...`, `c64 joy ...`) and finally:
```
c64 recordStop '{"format":"text"}' --compact     # script text, re-runnable with c64 script
```

### 8.10 Waiting for a game text (screen code) and jumping into a routine that never returns
```
loadState village
wait text "LORD OF RUIN" 10s          # searches as screen code: also works with custom charsets (API 18)
0 call 0xC000 a=20 x=0 nowait        # jumps to a routine that never returns (e.g. level change); the core goes on from there
wait 60
screenshot after_change
```
`wait text` does not see graphic glyphs nor text drawn on the bitmap. `call` without `nowait` on a routine that never returns ends with `CALL_TIMEOUT`.

### 8.11 Interrupting a running script or job
From another terminal: `c64 abort` interrupts the running job (the script ends with `ABORTED`, the emulator stays stopped; the files already produced, partial video included, are delivered anyway: tested with `video start`, exit 1), `c64 status` shows the job and its progress. If the `c64` client is closed or killed, the daemon interrupts its job by itself.

## 9. When logic is needed

For conditions, loops and decisions that depend on the state use JavaScript with the API (`runUntil`, `screenText`, `peek`, in-page `runLoop`). A great combination: the text script for the input sequences and a `.js` for the logic.

## 10. Limits and things not verified

- **Audio in the deterministic video: not available** (for real-time audio see `grabBrowserVideoAndAudio` in C64-API.md: it can be started before and stopped after a script, with the joystick/keyboard panel). The core exposes a sample buffer, but in the measures taken (100 frames) the samples received were ~79k instead of the 88.2k expected at 44.1 kHz, with almost zero amplitude, and the behavior changes when the main audio is opened: it is not deterministic, so it is not recorded. The video is silent.
- The video needs the emulator stopped; with the emulator in real time `video start` gives an error.
- Tested: poke, assert (ok and failed), `wait mem=` (ok and timeout), saveState/loadState, screenshot, regress save/check (equal and different), call, video autostop, video `keep` + `videoStop`, `rec`. **Not tested**: very long scripts, `assert`/`wait mem=` in real time with long times, `wait mem=` in warp mode, `keep` videos of many minutes (memory/ffmpeg), Docker (never built here).
