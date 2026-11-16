# CLAUDE.md — Lab64

Lab64: **assemble, test, emulate and analyze C64 programs**, a toolchain for the Commodore 64 that runs in Docker containers.
Owner: Simone Caporale (engineer). Read [README.md](README.md) first (overview and index of the documentation); the reference is in [docs/](docs/).

## Talking with the owner
- **Answer in Italian in the chat**, precise, technical and direct. ALWAYS say when a piece of information is not 100% certain.
- Files for the owner are delivered as files (SendUserFile), not as published artifacts.

## Language of the repository
- **Everything in this repository is in English**: code, comments, scripts, generated pages, README, docs, messages and **commit
  messages**.
- Copyright line: "Copyright (c) 2026 - Simone Caporale" in code, "Copyright © 2026 - Simone Caporale" in documents.

## What Lab64 is and is not
- Lab64 is **generic**: it knows nothing about any project, and **no project name appears in this repository**. A project uses
  it only through the `lab64` command (host: `cli/lab64`, in the PATH with `lab64 install`; containers: `containers/common/lab64-worker`, linked as `lab64`) and the
  Python library, never through a path to Lab64, and configures it with `lab64.env` in its root. Nothing project-specific goes
  here; generic parts of a project can move here.
- A change here must keep the owner's projects green (their build with smoke and sanity tests) and the `lab64 init` skeleton
  (`lab64 init --yes && lab64 build && lab64 test && lab64 manual && lab64 map` in an empty folder), with the compose stack
  down and up (`lab64 up`: the commands run with `docker exec`).

## Containers
- Everything runs **only in containers**. Host requirements: sh, Docker with BuildKit and Compose v2, git, curl. Linux, or Windows **only through
  WSL2** (project in the WSL filesystem). Python runs only in the containers.
- In the containers: project at **`/work`** (read-write), Lab64 at **`/lab64`** (read-only), `LAB64=/lab64`, `cli/` in the PATH
  and `py/` importable (image ENV). These are the only absolute paths allowed. Scripts find Lab64 from their own location and
  the project from the current folder (or `C64_PROJECT`).
- Images (tag `:<VERSION>` and `:latest`): `lab64-tools` (build + VICE, on demand), `lab64-pdf-gen` (HTML -> PDF, on demand),
  `lab64-viewer` and `lab64-vc64web` (services). One multi-stage
  `docker/Dockerfile` (vc64web has its own, self-contained package). Ubuntu version in one place (`ARG UBUNTU`). Images stay
  **minimal**: compilers only in the `*-build` stages. (14/11, owner's rule) external programs at the **latest version**, compiled
  **from source** inside the image build wherever possible; only binaries and licenses go into the images. Versions, URLs and
  checksums only in `build-scripts/sources.conf`.
- **Security**: no container gets the Docker socket (it is root on the host). The viewer is the only component reachable from the
  browser: it keeps its Host allowlist, same-origin check and JSON-only control API (`/control`, and `/render` since 1.8), and talks to the player
  (always running with it; no network) through a Unix socket in the `lab64-x11` volume.
- What is needed only to build an image (the sources in `downloads/`, the pages in `out/`) is deleted once the image exists. **(16/11, owner's rule) The
  images are self-contained**: nothing generated on the host is needed to run them (Lab64's `out/` can always be deleted); the portable vc64web
  page is inside `lab64-vc64web` and the viewer shows it by proxy (`lab64 page` builds only that page, the control center downloads it).
- **(16/11, owner's rule) The images are never published in a public registry** (Docker Hub, GHCR public, ...): they contain the Commodore
  ROMs and third-party programs. They may be pushed **only to a private registry of the owner at home**. Never run `docker push` to
  anything else, never make an image or an image archive public.

## Scripts and code
- Layout ([docs/architecture.md](docs/architecture.md), "Repository tree"): `cli/` = HOST side (`lab64` = the only command to use, `run.sh`, `check_env.sh`);
  `build-scripts/` (`build-images.sh`, `check_roms.sh`, `sources.conf`); `docker/` (`Dockerfile`, `compose.yaml`); `containers/<name>/` =
  the files that go into that container; `containers/common/` = goes into every image (`lab64-worker` = container side of `lab64`,
  linked as `/usr/local/bin/lab64`; `py/` with `lab64env.py` = the one reader of `lab64.env`, `d64.py` = the one `.d64` reader, `psid.py`);
  `containers/tools/` (`py/`, `test/run.py`, `memmap/`), `containers/pdf-gen/` (`c64manual.py`, `themes/`), `containers/viewer/`,
  `containers/vc64web/`; `roms/`; `docs/` (the documentation, screenshots). Bump `VERSION` when an image or an interface
  used by projects changes (projects pin it with `LAB64_VERSION`).
- Shell (POSIX sh/bash) when a script only runs commands; Python when there is real logic. No Python wrappers around shell commands.
  External Python libraries only if they are in the container.
- After changing a script: run it from another folder.
- Line endings always LF (`.gitattributes`).

## Git
- Branch `main`. **One commit per concluded activity** (green builds of the projects + smoke and sanity), message in English: short
  title + body with what and why, plus the `Co-Authored-By` line (never the `Claude-Session` link: owner's rule, 16/11). Author: **Simone Caporale `<caporalesimone@gmail.com>`**.
- `git status` clean before delivering; never rewrite history unless the owner asks.
- Out of git: `out/`, downloaded sources (`downloads/`), caches. The Commodore ROMs (`roms/vice-roms/{C64,DRIVES}`, **the only ROM
  folder**: every user of the ROMs takes them from there) are **not in git** (exact file names in `.gitignore`; folders pushed empty with `.gitkeep`). The
  user copies them in BEFORE building the images, which contain them and are never distributed. That folder is read **only at image build time**
  (docker build context `roms`; copies in `/opt/roms` and `/app/roms`): at run time nothing uses it; `build-scripts/check_roms.sh` (file names + SHA-256
  from `roms/roms.md`) stops the image build and is shown by `lab64 check-env`.

## Documentation
- [README.md](README.md) is the overview and the index of the documentation, one file per topic in [docs/](docs/) is the reference of Lab64
  (the tutorial is [docs/getting-started.md](docs/getting-started.md)), [TODO.md](TODO.md)
  the open work (categories, items ordered by size XS..XL). Update them in the same work when a command, a script, an image, a
  variable or the viewer contract changes. Projects keep their own docs for how they use Lab64.
- [THIRD-PARTY.md](THIRD-PARTY.md): every third-party component with copyright and license. Update it in the same work when a
  program, library, font, ROM or base image is added, removed or changes version (`build-scripts/sources.conf`, Dockerfiles). Never state a
  copyright or license that was not read in a primary source: mark it unverified.
