# Docker images

Copyright © 2026 - Simone Caporale

How the Lab64 images are built and what each one contains. The external programs compiled into them are in
[external-programs.md](external-programs.md); the host and container layout is in [architecture.md](architecture.md).

One multi-stage Dockerfile, `docker/Dockerfile`: one image per target, all with the same parent. Tags: `lab64-<name>:<VERSION>`
(file `VERSION`, today 1.14) and `lab64-<name>:latest`. A project can require a version: `LAB64_VERSION` in its `lab64.env`
(the scripts stop if it differs).

| Image | Target | Contents | Runs |
|---|---|---|---|
| (none) | `base` | ubuntu (`ARG UBUNTU`, today 24.04) + CA + locale + `/work`. Common parent: **it has no name**, it never runs | |
| (none) | `tools-builder`, `vice-build`, `tass64-build`, `cc65-build`, `cc1541-build`, `zx0-build`, `sidplayfp-build` | compilers and development libraries; they compile the external programs from source. They stay in the BuildKit cache and never become images | |
| (none) | `py-build`, `slim` | `py-build`: Matplotlib and NumPy from PyPI in a venv (`/opt/py`; pip stays here). `slim`: base + dpkg rule that leaves out documentation, man pages and translations (copyright files stay) | |
| (none) | `builder` | make, perl, unzip, zip, git, Python 3 with Pillow, PyYAML (Ubuntu packages) + Matplotlib, NumPy (`/opt/py`); 64tass, cc65 (with its libraries), cc1541, zx0 in `/opt/c64`. Internal stage | |
| `lab64-tools` | `tools` | builder + VICE (`x64sc`, `c1541` and its data in `/opt/vice`), `sidplayfp` (`/opt/c64/bin`, statically linked, renders `.sid` to WAV), gtk3 libraries, Xvfb, ffmpeg. **One image for build and tests**: the tests assemble variants and run them in VICE | on demand |
| `lab64-viewer` | `viewer` | KasmVNC Xvnc (official package) + PulseAudio + Node server (`containers/viewer/server.js`): control center, screen with audio, `out/`, C64 keyboard and joystick overlay (`/input`), `/control` towards the player | service |
| `lab64-vc64web` | (Dockerfile of `containers/vc64web/`) | node, Playwright + `chromium-headless-shell` (the daemon runs headless; build argument `HEADED=1` adds the full Chromium for the debug mode with a window), ffmpeg (videos: frames captured in the page, encoded with libx264), daemon of the in-browser emulator | service |
| `lab64-pdf-gen` | `pdf-gen` | Python 3 with PyYAML and Pillow, pango, DejaVu fonts + WeasyPrint (in `/opt/pdf`, a venv built with pip in the `pdf-build` stage: pip does not reach the image). HTML + CSS -> PDF: instruction manuals (`lab64 manual`) | on demand |

Sizes (measured on 15/11, not re-measured since): `lab64-tools` about 1.3 GB (`sidplayfp` is a 1.9 MB static binary), `lab64-vc64web` about 1.5 GB (only the headless Chromium shell), `lab64-viewer` about 0.8 GB, `lab64-pdf-gen` about 0.3 GB.

To change Ubuntu: `ARG UBUNTU` in `docker/Dockerfile`, then `lab64 images --force` (it also recompiles every external program on the new base;
the KasmVNC package must match the Ubuntu release).

**Images and registries** (owner's rule, 16/11): the images contain the Commodore ROMs and third-party programs, so they are never
published in a public registry; at most pushed to a private registry at home.

## Building: lock, downloads, CPUs, pinned dependencies (1.13)

- **One build at a time** per Lab64 folder: `build-images.sh` holds the lock `downloads.lock/` (with the PID of its owner; a lock left by a
  dead process is taken over). A second `lab64` command that finds an image missing prints "waiting for it" and goes on after.
- The sources of an image are **downloaded in parallel** (each checked with its SHA-256 or commit, as before).
- BuildKit compiles the independent stages (VICE, sidplayfp, 64tass, cc65, ...) **at the same time**: each `make` gets `-j JOBS`, with
  `JOBS = nproc / 3` (at least 1), so together they use about the CPUs of the machine. `LAB64_BUILD_JOBS=N` overrides it (changing it
  recompiles those stages once). cc65 is always serial (its makefiles race).
- **Pinned dependencies**: the Python packages of the venvs with `pip install -c docker/constraints-tools.txt` / `constraints-pdf.txt`
  (all versions, dependencies included); the viewer's npm packages with `npm ci` from `containers/viewer/package-lock.json`. The
  top-level versions stay in `build-scripts/sources.conf`, which points to these files. To update one: change `sources.conf`, rebuild,
  write the new versions of the venv into the constraints file (`python -c "import importlib.metadata as m; ..."` on the venv's
  `site-packages`) or `npm install --package-lock-only` for the lock.
- **VICE data** in `lab64-tools` (`/opt/vice/share/vice`, ~0.6 MB instead of ~9 MB): `C64/` and `DRIVES/` without ROMs (palettes,
  keymaps, symbols, default resources), `GLSL/` (the GTK3 OpenGL output), `hotkeys/`, `common/` (fonts and the x64 icons). The other
  machines are not copied. Every ROM comes from Lab64's `roms/` (`/opt/roms`), passed on the command line.
