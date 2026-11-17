# Lab64 TODO

Copyright © 2026 - Simone Caporale

Open work only. A finished item is deleted (its decision goes into the docs). Items are grouped by category and,
inside a category, ordered by size. **Sizes**: **XS** = minutes or a decision; **S** = hours; **M** = 1–2 days; **L** = several
days; **XL** = weeks. IDs are stable: `L<n>` (Lab64).

## 1 — Command line and project contract

### L22 Stack up during a version change — XS (decision) + S
- After `lab64 upgrade` (new `VERSION`) the commands still enter the running `lab64-tools` container of the OLD version until
  `lab64 down` / `lab64 up` (`run.sh` checks only the project label, not the image tag). Options: `run.sh` compares the image of the
  running container with `lab64-tools:<VERSION>` and falls back to `docker run` with a warning; or `lab64 upgrade` restarts the
  stack itself. To decide.

### L4 `lab64 init` templates — S
- Today one skeleton (assembly, 64tass). Options: `--template asm|c` (cc65 C project), `--template game` (IRQ, raster, joystick
  input, sprite). Keep the default the smallest one.

### L17 Compose: more than one project at a time — M (only if needed)
- The stack has fixed names (`lab64-tools`, `lab64-viewer`, ...): one project at a time, `lab64 up` for another asks to stop the
  first. For several: a compose project name and a viewer port per project.

## 2 — Manual (`lab64 manual`)

### L8 More base themes — S each
- Done: `c64`, `plain`. Candidates when wanted: `c128` (grey and blue), `breadbin` (brown and beige).

### L18 Type scale per format — S
- The format changes only the sheet; the type sizes are those of the theme (8 pt, made for A5). A `--size` per format in the
  base themes (e.g. A4 = 10 pt) would give a sensible default for bigger sheets. Texts still have to be written per format.

## 3 — Tests and VICE

### L36 (with ex L13, ex game J10) Parallel `lab64 test` by number of CPUs — M
- Today one run at a time (`out/tmp/.test.lock`): the VICE monitor port (6510, fixed in `containers/tools/py/vicemon.py`) is unique, and two runs
  talked over each other (random failures seen during the project restructuring).
- To do: monitor port per worker (6510+N, passed to `vicemon.py` and to VICE `-remotemonitoraddress`); working folder per worker
  (`out/tmp`, the `.d64` written by the save tests, Krill caches); lock per worker plus a scheduler that hands out the tests from
  the list; workers = number of CPUs (`nproc`), overridable (`lab64 test --jobs N`, `C64_TEST_JOBS`); one merged report and the
  same time caps (`C64_TEST_CAPS`).
- Open points (not measured): CPU use of one VICE instance (if it saturates a core, 2 workers on 2 CPUs give less than 2x); tests
  that measure cycles (frame pacing, PERF, music IRQ) may become unstable on a shared CPU, so they may need to run alone.
  Smoke + sanity (~21 s, mostly VICE start-up) is probably not worth parallelizing; the regression (~6-7 min) is.
- Also (ex L13): one Xvfb per worker, tests that assemble variants isolated (a project may rewrite its own build); in the viewer
  more screens (`VIEW_SCREENS=N`, one Xvnc per screen; ~30 lines and 30-60 MB of RAM per screen, not measured).

## 4 — Images

### L14 (ex game I10) Smaller images: what is left — M
- Done on 15/11: tools 1553 -> 1283 MB (Matplotlib and NumPy from pip), vc64web 2116 -> 1508 MB (headless shell only), dpkg rule
  without docs / man / translations.
- Left, all change the setup (results to compare): `lab64-tools` still has mesa + LLVM (~180 MB, needed by VICE's GTK3 OpenGL
  output, also in Xvfb) and ffmpeg with its codecs (`libflite` 27 MB, ...): a VICE without GL is not an option (the owner watches
  it on the viewer screen); a smaller ffmpeg build would have to give identical encodings. `lab64-viewer` 779 MB: mesa + LLVM
  again (KasmVNC's Xvnc), PulseAudio pulls GStreamer codecs (~55 MB). `lab64-vc64web`: Chromium's system libraries (~470 MB in
  `/usr/lib`).

## 5 — Viewer

### L27 Viewer server: Range requests, player socket permissions — S
- `server.js` ignores `Range`: big files (videos, disks) cannot be resumed or seeked; answer `206` with `Content-Range` for one
  range.
- The player socket `lab64-player.sock` is mode 0666 in the `lab64-x11` volume, which every one-shot test container mounts: any
  of them can drive the player. Tighten (0660 with a shared group, or a token in the volume readable only by the viewer and the
  player).

### L34 SID Studio reSID: the analyzer, what is left — S
- Done in 1.9: a silent jsSID locked to the WAV feeds registers, envelopes, per-voice scopes, voice info, player CPU, piano roll and automation
  (docs/manifest.md, SID Studio row). Left greyed on purpose: solo, the filter override, the filter curve over the spectrum.
- Uncertain / to watch: (1) the two clock constants (0.999796 PAL, 0.999604 NTSC) and the first-play model (`lab64FirstPlay`, `SPF_*` in
  `jssid_worklet_tail.js`) were measured for sidplayfp 3.2.3 at 44.1 kHz on the four `cal_*` tunes (about 1 ms accuracy, cross-correlation
  on the 17 game tunes: median 1-4 ms, a few windows with low correlation); another sidplayfp version or a 48 kHz context may need them
  measured again (the page's re-lock only sees scheduling errors, not a wrong constant). (2) PAL CIA tunes: sidplayfp's own timing has a
  1.8 ms step that the analyzer does not follow. (3) The analyzer follows jsSID's CPU/SID model, not reSIDfp's: tunes that depend on
  exact cycles (digis, raster-timed effects) can show different registers than the WAV sounds; per-voice scopes are jsSID's shape.
  (4) Output latency comes from `getOutputTimestamp()`; on a browser without it the panels use `outputLatency + baseLatency`.
  (5) Solo / override would need a render with the voice muted (`-u`) to be heard; not done. (6) Checkpoints are 66 KB each, 18 for 3:00;
  a 10-minute LEN is 60 (4 MB), fine, but the build runs in one Web Worker per tune load.

### L35 SID Studio reSID: engine and render details — S
- libsidplayfp 3 has no classic reSID (engines: reSIDfp, sidlite). Classic reSID would need libsidplayfp 2.16 beside 3.x (a second
  build of the player); decide if it is worth it. The render has no real progress (the page shows the elapsed time and an estimate
  from the speed of the previous render); sidplayfp prints none with `-q`. No fade-out or start offset in the UI (sidrender has them).
- `lab64 publish` renders the MP3s one after the other (about 12x real time on a 2-core machine): rendering in parallel needs a
  second core per render and a bound on the cache (1 GiB).
- Reproducibility is checked on one machine; reSIDfp's SIMD code (`--with-simd=runtime`) may differ in the last bits between CPUs.

### L16 (ex game J13) Overlay (C64 keyboard, Joy 1, Joy 2): real devices — S-M
- Tried only in a headless browser. To do: real touch screen (multi-touch stick + fire, rotation, key size), real browser and
  keyboard, **physical gamepad** through the Gamepad API (same `keyDown/keyUp` as Joy 1/2; estimate S, needs a real pad).
  Known limits: keys go to the window under the pointer (no window manager), so the overlay moves the pointer to the centre of the
  screen (VICE window centred: assumption, not verified with other screen sizes); with sticky SHIFT the C64 graphic keys come
  out without shift.

### L20 vc64web daemon on the viewer screen — S
- The daemon's Chromium runs headless. To watch it live: image built with `HEADED=1` (full Chromium), `C64_HEADED=1`, `DISPLAY`
  and the `lab64-x11` volume in the compose service. Not wired: today vc64web is watched through screenshots, videos (`c64
  video`) and the VirtualC64 page of the viewer (which runs in the user's browser).
