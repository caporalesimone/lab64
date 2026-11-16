# C64 ROMs

Copyright © 2026 - Simone Caporale (notes). This is the **only** ROM folder of Lab64: every user of the ROMs
takes them from here.

## Default set

Kernal `vice-roms/C64/kernal-901227-03.bin`, BASIC `vice-roms/C64/basic-901226-01.bin`, chargen `vice-roms/C64/chargen-901225-01.bin`,
1541-II drive `vice-roms/DRIVES/dos1541ii-251968-03.bin` (+ 1541 `dos1541-325302-01+901229-05.bin`). Required by VICE
(`tools/vice/vice_rom.py`, which also passes 1570 and 1571) and by the vc64web build; the others are optional.

## Files

| File | Bytes | SHA-256 | License | Contents |
|---|---|---|---|---|
| `vice-roms/C64/kernal-901227-03.bin` | 8192 | `83c60d47047d7beab8e5b7bf6f67f80daa088b7a6a27de0d7e016f6484042721` | Commodore (proprietary) | C64 Kernal rev. 3, the most common |
| `vice-roms/C64/basic-901226-01.bin` | 8192 | `89878cea0a268734696de11c4bae593eaaa506465d2029d619c0e0cbccdfa62d` | Commodore (proprietary) | BASIC V2 |
| `vice-roms/C64/chargen-901225-01.bin` | 4096 | `fd0d53b8480e86163ac98998976c72cc58d5dd8eb824ed7b829774e74213b420` | Commodore (proprietary) | standard character generator |
| `vice-roms/DRIVES/dos1541ii-251968-03.bin` | 16384 | `326c289c38753323d7e8167897447cf61ef35189d82eb8d75210ece949adda7c` | Commodore (proprietary) | firmware 1541-II |
| `vice-roms/DRIVES/dos1541-325302-01+901229-05.bin` | 16384 | `d1d45afb46fd4e2b48d93ca367b889d75654a3b7acf73044e51f6d880c09369e` | Commodore (proprietary) | firmware 1541 |
| `vice-roms/DRIVES/dos1570-315090-01.bin` | 32768 | `948e042a17578446124f8982857e9a77d9de86fd5f8d939ba5785e62faef6870` | Commodore (proprietary) | firmware 1570 (test KRILL-18) |
| `vice-roms/DRIVES/dos1571-310654-05.bin` | 32768 | `1fd73459b54a72a737609a879c283645acc37835de2c121633153db9fac81d45` | Commodore (proprietary) | firmware 1571 (test KRILL-18) |
| `vice-roms/C64/kernal-901227-02.bin` | 8192 | `675cf19a3e04bf68e41cc7a9010b353e51845ed9069db65496c52b79f1e1385f` | Commodore (proprietary) | Kernal rev. 2 (menu of the portable page) |
| `vice-roms/C64/kernal-901227-01.bin` | 8192 | `f585600a2e47d0224459e878184d3f4cce2665bfcce65e61732530c6d89c4269` | Commodore (proprietary) | Kernal rev. 1 (portable) |
| `vice-roms/C64/kernal-251104-04.bin` | 8192 | `81ad3a08920f2782ab031bb3ae02789d1f5f216c3d24d262e752a2b13e9faf73` | Commodore (proprietary) | Kernal SX-64 (portable) |
| `vice-roms/C64/kernal-390852-01.bin` | 8192 | `0a644f5e7f6ef8cb67b07e7a80f3f9a35584d9b131294c64f6e747a7e5c8a789` | Commodore (proprietary) | Kernal C64 Games System (portable) |
| `vice-roms/C64/kernal-901246-01.bin` | 8192 | `b2b430a134514af11f3ed64c0929fc5241d8436ba7b12514ec02d1b2cb2fd533` | Commodore (proprietary) | Kernal 4064 / PET 64, identification not certain (portable) |
| `vice-roms/C64/kernal-906145-02.bin` | 8192 | `48af48070ec9adda79ae7f65b772c422062eb12e69214a7cf788e6947a3b4117` | Commodore (proprietary) | unidentified Kernal (portable) |
| `vice-roms/C64/chargen-906143-02.bin` | 4096 | `0f4a5b0f9ec0d86639ba316053e330fdd849692623a41f8de4a420fcd47c55ee` | Commodore (proprietary) | alternative chargen (portable) |

## Optional: Open ROMs (`open-roms/`)

`roms/open-roms/` is an empty placeholder (kept with `.gitkeep`; its contents are ignored by `roms/.gitignore`, never in git).
Free replacement ROMs (e.g. the MEGA65 Open ROMs) put there are **optional** and are used **only** by the vc64web client:
`c64 roms` lists them and `c64 rom kernal NAME` loads one in place of the Commodore Kernal until the next start. VICE, the tests and the
vc64web pages do not use them, and `check_roms.sh` does not check them. They reach the images (`lab64-tools`: `/opt/roms/open-roms`,
unused; `lab64-vc64web`: `/app/roms/open-roms`) only when the images are rebuilt: `lab64 images --force tools vc64web`.
Their license is the user's responsibility. Not tested here: booting an Open ROM Kernal in vc64web.

## Where to get them

- `vice-roms/C64/*`, `vice-roms/DRIVES/*`: VICE data folder, `data/C64/` and `data/DRIVES/` of the source tarball
  (https://sourceforge.net/projects/vice-emu/files/releases/) or of the git mirror: `https://github.com/VICE-Team/svn-mirror/raw/main/vice/data/C64/<file>`, `https://github.com/VICE-Team/svn-mirror/raw/main/vice/data/DRIVES/<file>`
  (in the mirror the `+` of `dos1541-325302-01+901229-05.bin` must be written `%2B`). **Mirror URLs not opened from here** (restricted network): not verified.

**Not in git (16/11)**: the 14 Commodore ROM files (every `vice-roms/...` row of the table, in `roms/vice-roms/{C64,DRIVES}`, **the only place**) are listed by exact name in `roms/.gitignore`; the folders are pushed empty. **The user adds them before building
the images.** The folder is read **only while an image is built** (docker build context `roms`: `lab64-tools` copies it to `/opt/roms`, `lab64-vc64web` to `/app/roms`); VICE, the SID renderer and the vc64web page builds then use the copy inside the image, and nothing reads this folder at run time. The images are built by the user and never distributed. `check_roms.sh` verifies names and SHA-256
against the table above: `lab64 images` (and every command that builds an image) stops with the list of what is missing or wrong, and
`lab64 check-env` reports it as an error.

**Copyright**: the Commodore ROMs are not free: neither the repository nor the images may be published with them. The descriptions of the variants come from the vc64web package: `901246-01` and
`906145-02` are not identified with certainty.
