# Architecture: layout, paths and scripts

Copyright © 2026 - Simone Caporale

Where things live in the repository, what runs on the host and what runs in the containers, and the scripts behind the command line.
The command is described in [command-line.md](command-line.md), the images in [images.md](images.md).

## Layout and paths

- Lab64 lives **anywhere** (e.g. `~/lab64`). A project never refers to it by path: it uses the **`lab64` command** (in the PATH
  after `<lab64 folder>/cli/lab64 install`, run once: see [Install the command](getting-started.md#install-the-command)), from the project folder (the current folder, or `C64_PROJECT`).
- In the containers the project is mounted at **`/work`** (read-write) and Lab64 at **`/lab64`** (read-only). The images set
  `LAB64=/lab64`, link the container side of the command line (`containers/common/lab64-worker`) as `/usr/local/bin/lab64` and make
  the Lab64 Python libraries importable (`containers/common/py`, plus `containers/tools/py` or `containers/pdf-gen`, per image):
  project scripts that run there call `lab64 map`, `lab64 test`, `from vicemon import Vice`, ... with no path to Lab64.

## Repository tree

```
README.md  TODO.md  LICENSE  THIRD-PARTY.md  CLAUDE.md  VERSION  .gitignore  .gitattributes
docs/                   the documentation (index in README.md), getting-started.md, screenshots/
cli/                    HOST side (what you run): lab64 (the only command to use), run.sh, check_env.sh
build-scripts/          host scripts that build the images: build-images.sh, check_roms.sh, sources.conf
docker/                 Dockerfile (all images but vc64web), compose.yaml (the services)
containers/
  common/               goes into every image: lab64-worker (container side of `lab64`), py/ (lab64env, d64, psid)
  tools/                lab64-tools: py/ (c64test, vicemon, c64publish, sidrender, viewer_player, vice_env.sh), test/run.py, memmap/
  pdf-gen/              lab64-pdf-gen: c64manual.py, themes/
  viewer/               lab64-viewer: server.js, start.sh, www/ (control center, live screen, SID Studio), jsSID patch
  vc64web/              lab64-vc64web: its own Dockerfile, headless daemon and client, page builders, docs
roms/                   vice-roms/{C64,DRIVES} (folders kept with .gitkeep; the 14 ROM files are ignored by roms/.gitignore); roms.md;
                        open-roms/ (optional placeholder, used only by the vc64web client `c64 rom`; contents ignored)
out/  downloads/        created at run time, not in git (builds and releases of a project; sources while the images build)
```

## What runs where (`cli/` vs `containers/`)

- **`cli/` runs on the host** (sh, with Docker and nothing else). `cli/lab64` is the **only command a person types**: it starts
  containers, services and image builds, and hands the Python work to the container side.
- **`containers/<name>/` is copied or mounted into that container** and runs there. `containers/common/` is available in every
  image; the other folders only in the image of the same name.
- The two halves of the command: **`cli/lab64`** (host) and **`containers/common/lab64-worker`** (container, Python: init, default
  build, tests, manual, map, publish; linked as `lab64` inside the images, so project scripts keep calling `lab64`). The host half
  calls the container half for those commands. No container gets the Docker socket.
- `cli/run.sh` is a host script (it starts a container), which is why it is not under `containers/`.
- Host requirements: sh, Docker (with BuildKit and Compose v2), git, curl. Linux, or Windows with WSL2 (the project in the WSL filesystem).
  Python runs only in the containers.

## Scripts

Behind the command line (projects use `lab64`, not these scripts); all work from the project folder.

| Script | What it does |
|---|---|
| `build-scripts/build-images.sh [--force] [names]` | (`lab64 images`) builds the missing images (`tools viewer vc64web pdf-gen`); downloads on the host the sources listed in `sources.conf` into `downloads/` (checked: SHA-256 or git commit) and deletes them once the images exist |
| `build-scripts/sources.conf` | **the only place** with versions, URLs and checksums of the external programs |
| `cli/run.sh <image> [command]` | runs a command with the project in `/work` and Lab64 in `/lab64`, as the host user; `tools` = `lab64-tools`, a full name is used as is |
| `docker/compose.yaml` | the services (`lab64 up`, `view`, `down`, `ps`): `tools`, `vc64web`, `viewer` = http://localhost:6080 (control center with build and test status, one card per version of `out/releases/`, trends and comparison; live screen with audio, KasmVNC + PulseAudio; vc64web in the browser; the project `out/`), `player` with `C64_VIEW_PLAYER` (`containers/tools/py/viewer_player.py`); the viewer restarts by itself if its server stops with an error (`restart: on-failure`) |
| `containers/tools/memmap/c64map.py` | (`lab64 map`) **automatic** memory and disk map, with no configuration: reads the 64tass listings (`-L`), the labels (`-l`), the PRGs and the `.d64`; writes `index.html` and `memmap.json`. `--work`, `--disk`, `--out`, `--title` (default `C64_VIEW_TITLE`). Static analysis: limits in the page. `--probe DIR` (default `out/work/memprobe`): RAM dumps of the run-time probe in VICE (`containers/tools/memmap/probe.py`: the test library fills the RAM with a known pattern after the boot and saves it at the end of every session; only the dumps made with the same disk are used) add the memory really written. `memmap.json` has `metrics` in the viewer format. **Optional comments in the sources**: `;@map` (memory the analysis cannot see; `free-after=`, `scenario=`, `layout`), `;@free` (free memory by use, checked), `;@scenario` (what is in memory together: modules and disk files); `--strict` = exit 1 on an annotation problem; see [memory-maps.md](memory-maps.md). Every pair of labels `NAME` / `NAME_end` (`C64_MAP_PAIRS`) names an area by itself. **Second probe pass**: `C64_MEMPROBE=2` runs the same scenarios with another fill pattern; with dumps of both patterns no byte written with the pattern value is left as "never written". **Several programs**: `C64_MAP_PROGRAM_<NAME>` in `lab64.env` gives one map per program (`program-<name>.html`) and makes `index.html` an index ([memory-maps-programs.md](memory-maps-programs.md)) |
| `cli/check_env.sh` | (`lab64 check-env`) checks the host: `lab64` in the PATH, Compose, system, WSL and project location, Docker, line endings, ROMs, images, tools |
