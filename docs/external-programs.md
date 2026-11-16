# External programs

Copyright © 2026 - Simone Caporale

The third-party programs that go into the images and where they come from. Copyright holders, SPDX licenses and what is still
unverified are in [THIRD-PARTY.md](../THIRD-PARTY.md); how the images are built is in [images.md](images.md).

**Latest versions, compiled from source** where possible (owner's rule, 14/11); only binaries and licenses go into the images,
the sources are thrown away. Versions, URLs and checksums: [`build-scripts/sources.conf`](../build-scripts/sources.conf), the only place that has them.
Copyright holders, SPDX licenses and what is still unverified for **every** component (these programs, fonts and ROMs; libraries are not listed): [THIRD-PARTY.md](../THIRD-PARTY.md).

| Program | Version (14/11/2026) | License | Source | Image |
|---|---|---|---|---|
| VICE (reference emulator, gtk3) | 3.10 (latest release) | GPL-2.0 | official tarball (SourceForge) | `lab64-tools` (`/opt/vice`) |
| 64tass (6502 assembler) | 1.60.3243 (latest source release) | GPL-2.0 | official source zip (SourceForge) | `lab64-tools` |
| cc65 (cc65, ca65, ld65) | V2.19 (30/05/2020, the last tag; its sources print "2.18"). Master was checked on 14/11: byte-identical Krill binaries, ca65/ld65 fixes only for other CPUs and corner cases, so the tag | zlib | GitHub, tag commit | `lab64-tools` |
| cc1541 (writes .d64 disks) | 4.2 (latest release) | MIT | upstream tarball kept by Debian (the Bitbucket repository answered 404 on 14/11) | `lab64-tools` |
| ZX0 by Einar Saukas (compressor) | latest commit (17/12/2021, format v2) | BSD-3 | GitHub, fixed commit | `lab64-tools` |
| sidplayfp (console SID player, renders `.sid` to WAV) with libsidplayfp and libresidfp (SID emulation) | sidplayfp 3.2.3, libsidplayfp 3.1.2, libresidfp 1.3.0 (latest releases on 15/11/2026) | GPL-2.0-or-later | GitHub release tarballs of github.com/libsidplayfp; the three are compiled in the `sidplayfp-build` stage, the libraries static (only the `sidplayfp` binary and the licenses go into the image; it needs only libc and libm: `-w` writes a file, the audio backend loads a sound library with `dlopen` only when a device is used). **libsidplayfp 3 dropped the classic reSID** and moved reSIDfp to libresidfp: the engines are `residfp` and `sidlite` (a lightweight emulation based on cRSID) | `lab64-tools` (`/opt/c64/bin`) |
| KasmVNC (X server with web client) | 1.5.2 (latest release) | GPL-2.0 | official `.deb` for Ubuntu 24.04 (binaries: building it needs its whole X server tree) | `lab64-viewer` |
| jsSID (SID player in JavaScript, Hermit) | 0.9.1 (last commit, 29/02/2016) | WTFPL | GitHub, fixed commit; only `jsSID.js` + `README.txt`, served locally (no CDN); Lab64 hooks added at build time by `containers/viewer/jssid_patch.py` (per-voice scope, mute, filter bypass, memory, audio output routing, play routine cycles, envelopes, filter override, 6581 DC offsets after reSID: `$D418` digis, external output filter 16 kHz / 16 Hz after reSID's `extfilt`, hard clamp, PAL / NTSC clock and frame period (19656 / 17095 cycles: 50.12 / 59.83 Hz VBI; CIA tunes latch + 1) from the PSID flags with `setvideo()`; the same patched core is also built as an AudioWorklet module, `jssid-worklet.js`, by the same script, and `www/sidengine.js` is its main-thread proxy; `getstate()` / `setstate()` (the whole emulation, bit-exact), `ff(n)` (n samples without output), `setks(p, n)` (clock scale, default 1: the audible engine never uses it) and `getinit()` (init cycles, CIA flag): 25 replacements) | `lab64-viewer` (`vendor/jssid/`) |
| Matplotlib, NumPy (charts and arrays in project tools) | 3.11.2, 2.5.4 (latest on 15/11/2026) | Matplotlib license (BSD-style), BSD-3 | PyPI wheels (pip in the `py-build` stage) | `lab64-tools` (`/opt/py`) |
| WeasyPrint (HTML + CSS -> PDF) | 70.0 | BSD-3 | PyPI (pip in the `pdf-build` stage) | `lab64-pdf-gen` (`/opt/pdf`) |
| `containers/vc64web/` (our variant of vc64web: in-browser emulator + command-line control) | build 32 / API 25 | see `containers/vc64web/docs/INCLUSION.md` (not verified) | in this repository | `lab64-vc64web` |
| C64 ROMs (`roms/vice-roms/{C64,DRIVES}`) | | see `roms/roms.md` | the Commodore ROMs are not in git (the user adds them, the only ROM folder, read only when an image is built) | |

Ubuntu packages (`make`, `perl`, Python and its libraries, Xvfb, ffmpeg, PulseAudio, Node in the viewer) come from Ubuntu 24.04
at the time of the build; the vc64web image starts from `node:22-bookworm-slim`.
