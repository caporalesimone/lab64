# How this package sits in the game repository

Copyright © 2026 - Simone Caporale (inclusion notes). The package contents are described in its `README.md`.

| | |
|---|---|
| Package | `containers/vc64web` = `c64-tools` build **32**, API **25** (files `BUILD`, `headless/APIVER`), with the changes below |
| Archive received | `c64-tools-v32-api25.zip`, 13/11/2026 (provided by the owner, produced by another chat; not a git repository) |
| What it contains | in-browser C64 emulator (**vc64web**, VirtualC64 in WebAssembly, `third-party/vc64web/`) + our command-line control (daemon `headless/c64d.js`, client `headless/c64`, `headless/c64-batch`), the portable page (`portable/`), documentation and examples |
| Where we use it | image `lab64-vc64web` of Lab64 (the C64 toolchain this package belongs to), used by projects built with Lab64 (regression tests in the emulator, demo videos, bot experiments) |
| Role | **secondary**: VICE stays the only authoritative reference |
| Future | the owner will publish it as a repository of its own; then only the artifact (the image or the generated pages) will stay here. That is why the package is **self-contained**: no path towards the game project |

## Layout (13/11)
```
build.py  BUILD  README.md  Dockerfile  docker-compose.yml  .dockerignore  .gitignore
headless/      daemon, client, API (sources of the remote control)
portable/      standalone page (shell.html, asm/)
roms/          ROMs: vice-roms/{C64,DRIVES}/, roms.md (which files are needed, SHA-256, licenses, where to find them)
third-party/   vc64web (emulator), READMEs of ffmpeg, nodejs, playwright
docs/          package documentation, CHANGELOG.md, this file
examples/      runnable examples
work/          work folders mounted in Docker: games/, roms/ (extra ROMs), scripts/
out/           (not in git) generated pages, unless --out is passed
```
Compared with the zip: `roms/` replaces `third-party/vice-roms/` and `third-party/open-roms/` (same subtree as the project
Lab64 `roms/`, **identical file by file**: checked by Lab64 `check_env.sh`); `games/`, `roms/` (extra ROMs) and
`scripts/` are in `work/`; `CHANGELOG.md` and these notes in `docs/`; removed `headless/x` (a PNG with the wrong name) and the Python
caches. The `headless/` and `portable/` names stayed: the package documentation and API use them.

## Our changes compared with the zip
- `build.py`: folders as **parameters** (`--vice-roms`, `--out`, `--tag`, or the variables `C64_VICE_ROMS`,
  `C64_OUT`, `C64_IMAGE`), with defaults relative to the package (`roms/vice-roms`, `out`, `c64d`);
  optional ROMs (missing variants are not in the menu of the portable page); Docker image built with the context `pages=<out>`
  (`--build-context`) and, if `C64_CA_BUNDLE` is set, with the CA as a secret; `--no-ffmpeg-check`.
- `portable/shell.html`: 2 lines (the menu of the portable page lists only the embedded variants); 13/11 evening: parameter
  `?disk=URL[&program=NAME]` (downloads and starts the disk, `fetch` with `cache:'no-cache'`; `docs/CHANGELOG.md`).
- `Dockerfile`: the pages come from the `pages` context, the ROMs from `roms/`; optional CA (`--secret id=ca`) for `npm`/Playwright.
- `.dockerignore`, `docker-compose.yml` (`additional_contexts: pages: ./out`, volumes in `work/`), `headless/c64` (looks for the ROMs in
  `roms/` and for the games in `work/games`).
- 14/11: the whole package translated into English (owner's rule: Lab64 is in English): code comments and messages, page
  texts, documentation, examples (files renamed: `01-hello.txt`, `count-memory.js`, `11-determinism.sh` ...). The screen of the
  key test program now says `KEY AND JOYSTICK TEST` (`runKeyTest()` waits for this text). Checked: `EMU-10`..`EMU-16` 7/7 PASS.
- Verified on 13/11 [MEASURED]: with the ROMs of the new `roms/` the two generated pages are **byte for byte identical** to those of
  the previous build; the image builds and the daemon answers (`/ping` 200, `c64 start`).

## In the game project
- The package is in Lab64 `containers/vc64web/` (13/11: the game's C64 toolchain `toolchain/`, formerly `third-party-tools/`; 14/11: its own repository, Lab64).
- `build-images.sh vc64web`: pages generated in the `lab64-tools` container (`build.py --no-docker --no-ffmpeg-check --out
  out/cache/vc64web`, in Lab64's own `out/`), then `docker build -t lab64-vc64web --build-context pages=out/cache/vc64web containers/vc64web`;
  the folder is deleted once the image exists. Since 1.10 the image holds both pages: `c64-headless.html` and the portable `VirtualC64-vNN.html`.
  Rebuilt only when the package changes (`build-images.sh --force vc64web`). **Never** `--bump-version`.
- The Lab64 viewer (`lab64 view`, which also starts the vc64web container) serves the project `out/` over HTTP; `/out/cache/vc64web/` is a **proxy to the daemon** of the `lab64-vc64web` container (`c64d`: `GET /pages/`, only `VirtualC64-vNN.html`), so the page is on the viewer origin and opens disks with `?disk=/out/<disk>`. The control center offers it as "Empty vc64web" and as a **↓ HTML** download (one file, e.g. for the phone). Only the portable page, one build: `lab64 page [FOLDER]` (`build.py --portable-only`).
- `lab64 test --emu` (or `lab64 up vc64web`) starts the container; the tests get `EMU_URL` (and `C64_EMU=1` with `--emu`).

## Updating the package
1. Extract the new zip into an empty folder in `out/tmp/`.
2. Replace the package files, **without** `.git` and **without** `out/`, and **redo the changes** of the section above (visible
   with `git diff` on the 13/11 commit); put `roms/` back as it is (identical to Lab64 `roms/`).
3. `lab64 images --force vc64web`, then, in a project with emulator tests, `lab64 test --emu regression -k EMU` (projects use only the
   `lab64` command); `git status` clean except the package files.
4. Update `docs/C64-API.md` of this package (and the projects' own docs) if the API or the behavior changes.

## License
**Not verified** (see `third-party/vc64web/README.md`: maybe GPL-3.0 for VirtualC64; the JS libraries have their own licenses).
Before publishing: check the license of vc64web and do not publish the generated pages nor the
Commodore ROMs of `roms/vice-roms/` (game TODO `I7`).
