# third-party

One folder per third-party component, each with a `README.md` that says what it is, where it comes from (link) and its license. **The licenses are the ones I could read in the files or remember: where it says «not verified», check before publishing.**

| Folder | Contents | Included | Note |
|---|---|---|---|
| `vc64web/` | emulator (wasm + JS) | yes | license not verified (GPL?) |
| `../roms/vice-roms/` | compatible Commodore ROMs (7 Kernals, 2 chargens, Basic, 1541 and 1541-II drives) | yes, also in the repo | **redistribution rights to be verified** |
| `../roms/open-roms/` | free ROMs | yes | LGPL-3+; PXLfont font to be verified |
| `playwright/` | headless Chromium | no | documentation only |
| `ffmpeg/` | video encoder | no | documentation only |
| `nodejs/` | runtime | no | documentation only |

The HTML files generated in `out/` (portable and headless) **embed** vc64web and the default VICE ROMs: treat them as the most restrictive of the included components.
