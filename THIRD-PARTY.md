# Third-party components

Copyright © 2026 - Simone Caporale

One row per external program, font or data file, with who owns it and its license. Libraries (linked, bundled or imported by
those programs) and Lab64's own files are not listed here. It is a working list, **not a legal opinion**.
**Owner** is the copyright holder as stated upstream; "n/v" = **not verified** in a primary source (the row says what is missing).
Versions are pinned in `build-scripts/sources.conf`, `docker/Dockerfile` and `containers/vc64web/`; "not pinned" = whatever the
image build resolves. Each component links to its homepage or source repository.

## 1. Programs compiled from source in `lab64-tools`

| Component | What it does | Version | Owner | License |
|---|---|---|---|---|
| [**VICE**](https://vice-emu.sourceforge.io/) | reference emulator `x64sc`, `c1541`: tests, screenshots, live screen | 3.10 | VICE Team (core team 1999-2025 and former members, list in the tarball README) | GPL-2.0-or-later |
| [**64tass**](https://tass64.sourceforge.net/) | 6502 assembler | 1.60.3243 | Marek Matula (Taboo Productions) 1996; BiGFooT/BReeZe 2000; Soci/Singular 2001-2014 and later; bundled `avl.c` Franck Bui-Huu, `my_getopt.c` Benjamin Sittler | GPL-2.0-or-later; bundled `avl.c` LGPL-2.0-only, `isnprintf.c` LGPL-2.0-or-later (per-file map n/v) |
| [**cc65**](https://github.com/cc65/cc65) (`cc65`, `ca65`, `ld65`, libraries) | C compiler, assembler and linker, used as the build tools of Krill's loader | 2.19 (tag commit `5552824`) | Ullrich von Bassewitz and many contributors (no central notice; holders of `libsrc/` n/v) | Zlib |
| [**cc1541**](https://bitbucket.org/PTV_Claus/cc1541/src/master/) | writes `.d64` disks | 4.2 | JackAsser, Krill, Claus, Björn Esser (2008-2024) | MIT |
| [**ZX0**](https://github.com/einar-saukas/ZX0) | compressor `zx0` | 2.2-20211217 (commit `ecde3a2`) | Einar Saukas | BSD-3-Clause |
| [**sidplayfp**](https://github.com/libsidplayfp/sidplayfp) | console SID player, renders `.sid` to WAV (built with libsidplayfp 3.1.2 and libresidfp 1.3.0) | 3.2.3 | Simon White; Antti Lankila; Leandro Nini; bundled {fmt} Victor Zverovich, ghc::filesystem Steffen Schümann, miniaudio David Reid | GPL-2.0-or-later; {fmt}, ghc MIT; miniaudio public domain / MIT-0 |

## 2. `lab64-viewer` (control center, live screen, SID Studio)

| Component | What it does | Version | Owner | License |
|---|---|---|---|---|
| [**KasmVNC**](https://github.com/kasmtech/KasmVNC) (`Xvnc` and its web client) | the shared screen shown in the browser | 1.5.2 | Kasm Technologies LLC 2020 and the lines of the Debian `copyright` (AT&T, RealVNC, TightVNC, Sun, Cendio and others); web client bundle (noVNC and others) n/v | GPL-2.0-or-later; libwebp part BSD-3-Clause |
| [**PulseAudio**](https://gitlab.freedesktop.org/pulseaudio/pulseaudio) | sound server (also `libpulse` for VICE) | Ubuntu 24.04 package, not pinned | Lennart Poettering; Pierre Ossman and others | LGPL-2.1-or-later; parts GPL-2.0-or-later and permissive (g711) |
| [**Node.js**](https://nodejs.org/) | viewer server runtime | Ubuntu 24.04 package, not pinned | Node.js contributors | MIT with many bundled libraries |

## 3. Python in `lab64-tools` and `lab64-pdf-gen`

| Component | What it does | Version | Owner | License |
|---|---|---|---|---|
| [**WeasyPrint**](https://weasyprint.org/) | HTML + CSS to PDF (`lab64 manual`) | 70.0 | Simon Sapin and contributors | BSD-3-Clause |
| [**Python 3.12**](https://www.python.org/) | interpreter | Ubuntu 24.04 package, not pinned | Python Software Foundation and others | Python-2.0 and the licenses in `debian/copyright` |

## 4. `lab64-vc64web` (browser emulator and its headless daemon)

| Component | What it does | Version | Owner | License |
|---|---|---|---|---|
| [**vc64web**](https://github.com/vc64web/vc64web.github.io) front end (`index.html`, `vc64.js`, `js/vc64_*.js`, `ringbuffer.js`, `css/`, sounds, sprites) | web page of VirtualC64 | deployment checkout `469b638` (28/10/2026) | no project copyright line upstream; `ringbuffer.js` names "mithrendal"; holders n/v | GPL-3.0 (`virtualc64web` repository; the deployment repository has no license file) |
| [**VirtualC64**](https://github.com/dirkwhoffmann/virtualc64) core (`vc64.wasm`) | C64 and 1541 emulation | not known (wasm built by vc64web) | Dirk W. Hoffmann per `third-party/vc64web/README.md` (n/v in a source header) | application GPL-3.0-or-later, core MPL-2.0 (except reSID), Peddle MIT, reSID GPL-2.0-or-later; which parts are in the wasm n/v |
| [**MEGA65 Open ROMs**](https://github.com/MEGA65/open-roms) (inside `vc64.wasm`: strings "M.E.G.A. C64 OpenROM") | free Kernal / Basic / chargen used by VirtualC64 only when the Commodore ROMs are missing (with Lab64 they are always loaded) | not known | MEGA65 / Open ROMs project contributors (n/v) | n/v |
| [**C64 Pro Mono**](https://style64.org/c64-truetype) font | C64 text in the pages | v1.202 | Style (http://style64.org) 2010-2014 | custom terms in the font file, not open source |
| [**Node.js**](https://nodejs.org/) | runtime of `c64d.js` and the `c64` client | 22.x (image `node:22-bookworm-slim`) | Node.js contributors | MIT with bundled components |
| [**Chromium**](https://www.chromium.org/) headless shell | runs the emulator page | 153.0.8010.12 | The Chromium Authors | BSD-3-Clause; many third-party components (not enumerated) |
| [**ffmpeg**](https://ffmpeg.org/) | H.264 videos (libx264) | Debian bookworm / Ubuntu 24.04 packages, not pinned | many holders (`debian/copyright`) | LGPL-2.1-or-later and GPL-2.0-or-later (default Debian build: GPL) |

## 5. ROMs, data and fonts

| Component | What it does | Version | Owner | License |
|---|---|---|---|---|
| **Commodore ROMs**, 14 files (`roms/vice-roms/{C64,DRIVES}`, names and SHA-256 in `roms/roms.md`) | Kernals, BASIC, character sets and drive firmware for VICE and vc64web | as in `roms/roms.md` | Commodore Business Machines (per the VICE README) | proprietary; **not in git**: the user copies them before building the images, which are never published. Redistribution conditions not assessed; variants `901246-01`, `906145-02` unidentified |
| [VICE](https://vice-emu.sourceforge.io/) data folder (all ROM sets, `share/vice`) | data of the VICE build | VICE 3.10 | as the ROMs; fonts and shaders below | as above |
| [**C64 Pro Mono**](https://style64.org/c64-truetype) in VICE data | font of VICE | v1.21 | Style 2010-2019 | the same custom terms (software package only if freely provided) |
| [**PetMe**](https://www.kreativekorp.com/software/fonts/c64.shtml) fonts in VICE data | fonts of VICE | with VICE 3.10 | Rebecca Bettencourt (Kreative Software) | Kreative Software Relay Fonts Free Use License v1.2f |
| VICE GLSL shaders (`bicubic*.frag`) | video filters of VICE | with VICE 3.10 | adapted from a GPL-2.0 bicubic implementation ([quark-shaders](https://github.com/hizzlekizzle/quark-shaders) by hizzlekizzle); no holder line | GPL-2.0 (covered by VICE's notice) |
| [**DejaVu**](https://dejavu-fonts.github.io/) fonts (`fonts-dejavu-core`) | manual themes and key caps in the PDFs | Ubuntu 24.04 (2.37-8) | Bitstream, Inc. (Vera); Tavmjong Bah (Arev); DejaVu changes public domain | Bitstream-Vera |

Not part of Lab64: **Krill's Loader** (a project builds it from its own zip; no file of it is here), which is why cc65 is in the build
image. The operating system and the Ubuntu / Debian packages of the images are not listed: their licenses are in
`/usr/share/doc/<pkg>/copyright` inside each image. The previous long form of this document (with the verification trail and the full
VICE copyright notice) is in the history of the project before 1.11.
