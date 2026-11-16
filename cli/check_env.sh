#!/bin/sh
# Checks the HOST environment before using Lab64 and the project (13/11, owner's request).
# Copyright (c) 2026 - Simone Caporale
#   lab64 check-env   (from the project folder)
#   one line per check: OK / WARNING / ERROR; exits 1 if there is at least one ERROR
# The host needs only: sh, Docker (with BuildKit and Compose v2), git, curl (source downloads). Everything else runs in the containers.
# It also checks WHERE the project is: in the WSL Linux filesystem (fast) or on a Windows disk (/mnt/c, slow and with
# permission and line-ending problems). Method: the filesystem type of the mount point that holds the project folder, read
# from /proc/self/mountinfo (the mount with the longest prefix), not the path name.
TC=$(cd "$(dirname "$0")/.." && pwd) || exit 1
ROOT=$(cd "${C64_PROJECT:-.}" && pwd) || exit 1
REL=$TC                                # Lab64 folder (ROMs, sources of the external programs)
cd "$ROOT" || exit 1
[ -f lab64.env ] && . ./lab64.env
VER=$(cat "$TC/VERSION")
echo "Lab64 $VER: $TC"
ERR=0; WARN=0
ok()   { printf '  OK       %s\n' "$*"; }
warn() { printf '  WARNING  %s\n' "$*"; WARN=$((WARN + 1)); }
err()  { printf '  ERROR    %s\n' "$*"; ERR=$((ERR + 1)); }
if [ -n "${LAB64_VERSION:-}" ] && [ "$LAB64_VERSION" != "$VER" ]; then
    err "the project needs Lab64 $LAB64_VERSION (LAB64_VERSION in lab64.env), this Lab64 is $VER"
fi

echo "== system =="
OS=$(uname -s)
WSL=0
if [ -r /proc/sys/kernel/osrelease ] && grep -qi microsoft /proc/sys/kernel/osrelease; then WSL=1; fi
[ -n "${WSL_DISTRO_NAME:-}" ] || [ -n "${WSL_INTEROP:-}" ] && WSL=1
case "$OS" in
Linux)  if [ $WSL = 1 ]; then ok "Linux in WSL (${WSL_DISTRO_NAME:-unknown distribution})"; else ok "Linux"; fi ;;
Darwin) warn "macOS: not tested (Docker Desktop should be enough)" ;;
*)      err "$OS: Linux or WSL2 needed (on Windows: open the project inside WSL)" ;;
esac

echo "== project folder: $ROOT =="
if [ -r /proc/self/mountinfo ]; then
    # mountinfo fields: 5 = mount point; after the " - " separator: filesystem type and source
    M=$(awk -v p="$ROOT" '
        { mp=$5; gsub(/\\040/, " ", mp); for (i=7; i<=NF; i++) if ($i == "-") { fs=$(i+1); src=$(i+2); break }
          if ((p == mp || index(p, mp == "/" ? "/" : mp "/") == 1) && length(mp) >= best) { best=length(mp); r=mp " " fs " " src } }
        END { print r }' /proc/self/mountinfo)
    MP=${M%% *}; R=${M#* }; FS=${R%% *}; SRC=${R#* }
    case "$FS" in
    9p|drvfs|v9fs|virtiofs|fuse.grpcfuse|fuseblk|cifs|smb3|nfs|nfs4|vboxsf)
        if [ $WSL = 1 ]; then err "the project is on a Windows disk ($FS, mounted on $MP): move it into the WSL filesystem (e.g. ~/projects), it is much faster and avoids permission and line-ending problems"
        else warn "shared or network filesystem ($FS on $MP): build and tests can be slow"; fi ;;
    ext4|ext3|xfs|btrfs|zfs|overlay|tmpfs|f2fs) ok "filesystem $FS (mount $MP)" ;;
    "") warn "filesystem type not found in /proc/self/mountinfo" ;;
    *) warn "filesystem $FS (mount $MP, $SRC): not classified" ;;
    esac
else
    warn "no /proc/self/mountinfo: filesystem type not checked"
fi
case "$ROOT" in /mnt/[a-z]/*) [ $WSL = 1 ] && err "path under /mnt/<drive>: a Windows disk seen from WSL" ;; esac
case "$ROOT" in *" "*) warn "the project path contains spaces: the lab64 commands handle them (tested: init, build, test, manual, map, publish), but better avoid them" ;; esac
FREE=$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}')
[ -n "$FREE" ] && { [ "$FREE" -ge 10 ] && ok "free space: $FREE GB" || warn "free space: $FREE GB (images + VICE + out/ ~ 8 GB)"; }

echo "== host programs =="
for p in git curl; do command -v $p >/dev/null && ok "$p: $(command -v $p)" || err "$p not found"; done
L=$(PATH=${LAB64_USER_PATH:-$PATH} command -v lab64 2>/dev/null || true)
if [ -z "$L" ]; then warn "lab64 is not in the PATH ($TC/cli/lab64 install)"
elif [ "$(readlink -f "$L")" = "$TC/cli/lab64" ]; then ok "lab64 in the PATH: $L"
else warn "lab64 in the PATH is another Lab64: $L -> $(readlink -f "$L")"; fi
if command -v docker >/dev/null; then
    ok "docker: $(docker --version 2>/dev/null)"
    if docker info >/dev/null 2>&1; then ok "Docker daemon reachable"
    else err "the Docker daemon does not answer (start it; on Linux add the user to the docker group; on Windows: Docker Desktop with WSL integration)"; fi
    docker buildx version >/dev/null 2>&1 && ok "BuildKit (docker buildx)" || warn "docker buildx not found: BuildKit and --build-context are needed (Docker >= 23)"
    docker compose version >/dev/null 2>&1 && ok "$(docker compose version 2>/dev/null | head -1)" || err "Docker Compose v2 not found (docker compose): needed by lab64 up / view (package docker-compose-plugin, or Docker Desktop)"
else
    err "Docker not found (https://docs.docker.com/get-docker/)"
fi

echo "== git and line endings =="
if git rev-parse --git-dir >/dev/null 2>&1; then
    A=$(git config core.autocrlf || true)
    [ "$A" = "true" ] && err "core.autocrlf=true: the scripts would become CRLF (git config core.autocrlf false)" || ok "core.autocrlf=${A:-not set}"
    [ -f .gitattributes ] && ok ".gitattributes (eol=lf)" || err ".gitattributes missing"
    CR=$(git ls-files --eol 2>/dev/null | awk '$2 ~ /crlf/ && ($4 ~ /\.(sh|py)$/ || $4 ~ /Dockerfile$/) {print $4}' | head -5)
    [ -z "$CR" ] && ok "no script with CRLF line endings" || err "scripts with CRLF in the working copy: $CR"
else
    warn "not a git repository"
fi

echo "== ROM ($REL/roms/roms.md) =="
if R=$("$REL/build-scripts/check_roms.sh" 2>&1); then ok "$R"
else err "Commodore ROMs missing or wrong (the image builds stop until they are fixed):"; printf '%s\n' "$R" | sed 's/^/             /'; fi

echo "== Docker images and external program sources =="
if docker info >/dev/null 2>&1; then
    for i in lab64-tools:$VER lab64-vc64web:$VER lab64-viewer:$VER lab64-pdf-gen:$VER ${C64_EXTRA_IMAGES:-}; do
        docker image inspect "$i" >/dev/null 2>&1 && ok "image $i" || warn "image $i missing (lab64 images; the commands build it when needed)"
    done
fi
# (14/11) every external program is compiled INSIDE the images, from the sources listed in sources.conf (downloaded by
# build-images.sh into downloads/ and deleted once the images exist)
if docker image inspect "lab64-tools:$VER" >/dev/null 2>&1; then
    V=$(docker run --rm "lab64-tools:$VER" sh -c 'x64sc --version 2>&1 | head -1; 64tass --version | head -1; cc65 --version 2>&1 | head -1; cc1541 2>&1 | grep -m1 version' 2>/dev/null | tr '\n' ';')
    ok "programs in lab64-tools: $V"
fi
[ -f "$REL/build-scripts/sources.conf" ] && ok "sources.conf: $(grep -c '_VERSION=' "$REL/build-scripts/sources.conf") programs" || err "sources.conf missing in $REL"

echo
if [ $ERR -gt 0 ]; then echo "RESULT: $ERR errors, $WARN warnings"; exit 1; fi
echo "RESULT: ok ($WARN warnings)"
