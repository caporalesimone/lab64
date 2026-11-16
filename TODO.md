# Lab64 TODO

Copyright © 2026 - Simone Caporale

Open work only. A finished item is deleted (its decision goes into the docs). Items are grouped by category and,
inside a category, ordered by size. **Sizes**: **XS** = minutes or a decision; **S** = hours; **M** = 1–2 days; **L** = several
days; **XL** = weeks. IDs are stable: `L<n>` (Lab64).

## 1 — Publishing (before the repository goes public)

### L3 Images on a registry, repository on GitHub — S
- `build-images.sh` stays (local builds); add `lab64 images --pull` from a registry (tags `:<VERSION>`), CI that builds and pushes.
  Release assets of a project on GitHub (the content of `out/releases/v<V>/`): a `lab64 publish --github` step, to design.

## 2 — Command line and project contract

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

## 3 — Manual (`lab64 manual`)

### L8 More base themes — S each
- Done: `c64`, `plain`. Candidates when wanted: `c128` (grey and blue), `breadbin` (brown and beige).

### L18 Type scale per format — S
- The format changes only the sheet; the type sizes are those of the theme (8 pt, made for A5). A `--size` per format in the
  base themes (e.g. A4 = 10 pt) would give a sensible default for bigger sheets. Texts still have to be written per format.

## 4 — Memory map (`lab64 map`)

### L11 (ex game T1) Scenarios from the run-time probe — S-M
- Done: scenarios listed by the project (`;@scenario`, `C64_MAP_SCENARIOS`) with free space and conflicts; label pairs.
  Missing: deriving the scenarios from the probe dumps (which modules were in memory in each VICE session), so no list is needed.

### L19 Annotations: more — S
- `;@map` inside macros or generated sources is read only if the generated file is among the sources of the listing (it is).
  Not done: areas in the page map coloured by annotation; `free-after` values other than free text (e.g. checked against labels).

## 5 — Tests and VICE

### L29 `c64test.test(slow=...)` — XS (question for the owner)
- The flag is stored in the registry (`slow`, also set by `script()`) but the Lab64 engine never reads it. Kept because a project
  may read it (Lab64 cannot see the projects). Owner: does any project use it? If not, remove it (and document the removal).

### L30 `vicemon.labels()` / `listing()` default to `"game"` — XS (question for the owner)
- A leftover of the first project: the default build of a new project writes `out/work/main.lbl` / `main.lst`, so the skeleton
  passes the name (`labels("main")`). Changing the default would break a project that calls them without argument. Owner: switch
  the default to `"main"` (a version bump, in the migration notes) or keep `"game"`?

### L21 One container for every command: monitor port and orphans — S-M
- With the stack up all the tools commands run in the same `lab64-tools` container (`docker exec`), so they share VICE's remote
  monitor port 6510: two commands that start VICE at the same time (a test run and a `lab64 run` of a project tool) talk to each
  other's VICE. The test lock covers only test runs. And an interrupted `docker exec` without a TTY leaves its process running in
  the container (no signal is forwarded): an orphan VICE that keeps 6510. With `docker run --rm --init` neither happens, so the
  "same results" of docs/command-line.md holds only for one command at a time.
- Proposal: a monitor port per process (free port chosen by `vicemon.Vice`, passed to x64sc with `-remotemonitoraddress`) or a
  lock in `vicemon.Vice`; cleanup of orphan VICE processes when a command starts (or `docker exec` wrapped so that it forwards
  signals / kills its process group on exit).

### L13 (ex game J10) Parallel tests — M
- More workers: one Xvfb per worker, different remote monitor ports, temporary files in `out/tmp/<worker>`, tests that assemble
  variants isolated (a project may rewrite its own build), one report. In the viewer: more screens (`VIEW_SCREENS=N`, one Xvnc
  per screen; estimate ~30 lines and 30–60 MB of RAM per screen, not measured). Duration caps stay.

## 6 — Images

### L24 Concurrent image builds and downloads — S
- Two `lab64` commands that find an image missing both run `build-images.sh`, which write the same `downloads/` files (`.part`
  then rename) and both delete `downloads/` at the end. Needs a lock (e.g. `flock` on `downloads/.lock`, or `mkdir` as a lock in
  POSIX sh) around fetch + build.

### L25 Dependencies not pinned — S
- Against "versions only in `sources.conf`": pip installs only the top-level packages with a version (Matplotlib, NumPy,
  WeasyPrint); their dependencies (pyparsing, fonttools, cffi, tinycss2, ...) float. The viewer's npm install has no lock file
  (`package.json` ranges; the lock is deleted after the install). Proposal: constraints files / a `package-lock.json` generated once
  and kept in the repository, with their versions listed in `sources.conf` (or referenced from it).

### L26 VICE data: copy only what is needed — S
- `/opt/vice/share` is copied whole into `lab64-tools`: ROMs of all the machines and fonts.
  Decision (15/11): copy only `C64/`, `DRIVES/` and what x64sc / c1541 really load (keymaps, palettes, GTK3 UI data); check
  that VICE starts and the tests pass, compare the image size.

### L14 (ex game I10) Smaller images: what is left — M
- Done on 15/11: tools 1553 -> 1283 MB (Matplotlib and NumPy from pip), vc64web 2116 -> 1508 MB (headless shell only), dpkg rule
  without docs / man / translations.
- Left, all change the setup (results to compare): `lab64-tools` still has mesa + LLVM (~180 MB, needed by VICE's GTK3 OpenGL
  output, also in Xvfb) and ffmpeg with its codecs (`libflite` 27 MB, ...): a VICE without GL is not an option (the owner watches
  it on the viewer screen); a smaller ffmpeg build would have to give identical encodings. `lab64-viewer` 779 MB: mesa + LLVM
  again (KasmVNC's Xvnc), PulseAudio pulls GStreamer codecs (~55 MB). `lab64-vc64web`: Chromium's system libraries (~470 MB in
  `/usr/lib`).

### L15 (ex game I9) Windows through WSL2 — S
- Never tried: `lab64 check-env`, a project build, `lab64 up` and `lab64 view` on WSL2 + Docker Desktop (WSL detection tested only
  with a sample `mountinfo`; X11 and Unix sockets in the `lab64-x11` volume on Windows not verified; the gain of the always-on
  tools container there not measured).

## 7 — Viewer

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

### L36 Parallel `lab64 test` (regression) by number of CPUs — M
- Today one run at a time (`out/tmp/.test.lock`): the VICE monitor port (6510, fixed in `containers/tools/py/vicemon.py`) is unique, and two runs
  talked over each other (random failures seen during the project restructuring).
- To do: monitor port per worker (6510+N, passed to `vicemon.py` and to VICE `-remotemonitoraddress`); working folder per worker
  (`out/tmp`, the `.d64` written by the save tests, Krill caches); lock per worker plus a scheduler that hands out the tests from
  the list; workers = number of CPUs (`nproc`), overridable (`lab64 test --jobs N`, `C64_TEST_JOBS`); one merged report and the
  same time caps (`C64_TEST_CAPS`).
- Open points (not measured): CPU use of one VICE instance (if it saturates a core, 2 workers on 2 CPUs give less than 2x); tests
  that measure cycles (frame pacing, PERF, music IRQ) may become unstable on a shared CPU, so they may need to run alone.
  Smoke + sanity (~21 s, mostly VICE start-up) is probably not worth parallelizing; the regression (~6-7 min) is.

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
