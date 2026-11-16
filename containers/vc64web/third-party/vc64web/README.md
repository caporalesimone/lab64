# vc64web (in-browser C64 emulator)

**What it is**: WebAssembly port of VirtualC64 (C64/1541 emulator). This folder holds the subset needed to run: `index.html`, `vc64.js`, `vc64.wasm`, `js/`, `css/`, `sounds/` (plus `UPSTREAM-README.md`, the original README). It is the component that is **embedded** (as base64) in `portable/VirtualC64-vNN.html` and in `headless/c64-headless.html`: publishing one of those two files means publishing this code too.

**Origin**: https://github.com/vc64web/vc64web.github.io (checkout used: commit `469b63818d1a8f4d654fd3985b82aeb4e03fabba`, 28/10/2026). The C++ core compiled into `vc64.wasm` is VirtualC64 by Dirk W. Hoffmann: https://github.com/dirkwhoffmann/virtualc64

**License**: **not verified.** The checkout has no license file and the original README does not mention one. As far as I know, VirtualC64 is under GPL-3.0 (general knowledge, not checked here): to be verified on the two repositories before publishing. If it is GPL, distributing the HTML with the embedded wasm requires making the corresponding source available and keeping the license.

**Libraries included in `js/`** (licenses deduced from the file headers or from my knowledge, to be checked):
| File | What it is | License |
|---|---|---|
| `jszip.min.js` | JSZip 3.10.1 | MIT or GPLv3 (dual, stated in the file header) |
| `eruda.js` | Eruda 3.1.0 (mobile console) | not verified (I believe MIT) |
| `jquery-3.7.1.min.js` | jQuery 3.7.1 | not verified (I believe MIT) |
| `bootstrap.bundle.min.js` | Bootstrap | not verified (I believe MIT) |
| `cm6/` | CodeMirror 6 bundle + JSHint | not verified (I believe MIT) |

**Our changes**: no file of this folder was modified. The build produces a modified copy of `index.html` (manifest/analytics removed, ROMs and resources embedded) only inside the generated HTML files.
