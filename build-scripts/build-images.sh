#!/bin/sh
# Builds the Lab64 images (13/11). Copyright (c) 2026 - Simone Caporale
#   lab64 images                       all the missing ones (the other commands build what they need by themselves)
#   lab64 images --force [names...]    rebuilds them (names: tools viewer vc64web pdf-gen)
# Tags: lab64-<name>:<VERSION> (file VERSION) and lab64-<name>:latest.
# tools, viewer: targets of the multi-stage Dockerfile docker/Dockerfile (common unnamed base stage).
#   (14/11, owner's rule) every external program is compiled FROM SOURCE in a *-build stage, at the latest version, and only the
#   binaries (and the licenses) go into the final images: VICE, 64tass, cc65, cc1541, zx0, sidplayfp in lab64-tools. KasmVNC (lab64-viewer) is
#   the official .deb (binaries only). Versions, URLs and checksums: sources.conf (the ONLY place).
#   The sources are downloaded ON THE HOST (curl or git: the computer's certificates and proxy) into downloads/, checked
#   (SHA-256 for files, commit for git) and passed to the build as the context "downloads". Once the images exist they are
#   deleted; --force downloads them again (same content: the BuildKit cache stays valid and nothing is recompiled).
# vc64web: pages generated in lab64-tools (into Lab64's own out/cache/vc64web, deleted once the image exists), image from the Dockerfile
#   of the self-contained package containers/vc64web; the image holds the headless page and the portable one (the viewer offers it).
# (1.13, TODO L24) one image build at a time per Lab64 folder (lock downloads.lock: two lab64 commands that find an image missing
#   wait for each other instead of writing the same downloads/); the sources of an image are downloaded in parallel; the compile
#   stages that BuildKit runs at the same time share the CPUs: make -j JOBS each (LAB64_BUILD_JOBS, default nproc / 3, at least 1).
# C64_CA_BUNDLE=FILE: CA of a TLS-intercepting proxy, passed as a secret to the builds that download with npm (vc64web, viewer).
set -eu
TC=$(cd "$(dirname "$0")/.." && pwd)
. "$TC/build-scripts/sources.conf"
VER=$(cat "$TC/VERSION")
DL="$TC/downloads"
# the full output of every docker build goes to this file; on a failure its last lines are shown (a failed RUN prints its own log there)
BUILD_LOG="${TMPDIR:-/tmp}/lab64-images.log"
build_failed() { echo "image build failed; last lines of $BUILD_LOG:" >&2; tail -n 80 "$BUILD_LOG" >&2; exit 1; }
FORCE=0; [ "${1:-}" = "--force" ] && { FORCE=1; shift; }
NAMES="${*:-tools viewer vc64web pdf-gen}"
# the lock: a folder (mkdir is atomic in POSIX sh) holding the PID of the owner; a lock left by a dead process is taken over.
# The nested call of vc64web_pages ("$0" tools) runs under the lock of its parent (LAB64_IMAGES_LOCKED).
LOCK="$TC/downloads.lock"
have() { docker image inspect "lab64-$1:$VER" >/dev/null 2>&1; }
if [ $FORCE = 0 ]; then                # nothing to build: no lock, no wait (the other commands call this to make sure an image exists)
    M=""; for n in $NAMES; do have "$n" || M="$M $n"; done
    [ -n "$M" ] || exit 0
fi
if [ -z "${LAB64_IMAGES_LOCKED:-}" ]; then
    n=0
    until mkdir "$LOCK" 2>/dev/null; do
        o=$(cat "$LOCK/pid" 2>/dev/null || true)
        if [ -n "$o" ] && ! kill -0 "$o" 2>/dev/null; then rm -rf "$LOCK"; continue; fi
        [ $n = 0 ] && echo "another image build is running (PID ${o:-?}): waiting for it"
        n=1; sleep 2
    done
    echo $$ > "$LOCK/pid"
    trap 'rm -rf "$LOCK"' EXIT
    trap 'exit 130' INT TERM HUP
    export LAB64_IMAGES_LOCKED=1
fi
NPROC=$(nproc 2>/dev/null || echo 2)
JOBS=${LAB64_BUILD_JOBS:-$(( NPROC / 3 ))}; [ "$JOBS" -ge 1 ] || JOBS=1
SECRET=""; [ -n "${C64_CA_BUNDLE:-}" ] && SECRET="--secret id=ca,src=$C64_CA_BUNDLE"
vc64web_pages() {                      # vc64web pages in Lab64's out/cache/vc64web/ (Lab64 itself is the project of this step)
    have tools || "$0" tools
    # the ROMs: the copy inside the lab64-tools image (made from roms/ when that image was built)
    C64_PROJECT="$TC" "$TC/cli/run.sh" tools python3 containers/vc64web/build.py --no-docker --no-ffmpeg-check --vice-roms /opt/roms/vice-roms --out out/cache/vc64web
}

# fetch NAME FILE: puts the source of program NAME (variables NAME_URL + NAME_SHA256, or NAME_GIT + NAME_REF of sources.conf)
# into downloads/FILE, if missing
fetch() {
    T="$DL/$2"; mkdir -p "$DL"
    eval "U=\${$1_URL:-}; S=\${$1_SHA256:-}; G=\${$1_GIT:-}; R=\${$1_REF:-}"
    if [ ! -s "$T" ]; then
        if [ -n "$U" ]; then
            echo "   downloading $U"
            curl -fsSL --retry 3 -o "$T.part" "$U" || { rm -f "$T.part"; echo "download failed: $U" >&2; exit 1; }
        else
            echo "   fetching $G at $R"
            W="$DL/.git-$1"; rm -rf "$W"; git init -q "$W"
            git -C "$W" fetch -q --depth 1 "$G" "$R" || { rm -rf "$W"; echo "git fetch failed: $G $R" >&2; exit 1; }
            git -C "$W" archive --format=tar.gz --prefix="${2%.tar.gz}/" -o "$T.part" FETCH_HEAD; rm -rf "$W"
        fi
        mv "$T.part" "$T"
    fi
    if [ -n "$U" ]; then
        H=$(sha256sum "$T" | cut -c1-64)
        [ "$H" = "$S" ] || { rm -f "$T"; echo "SHA-256 mismatch for $2: $H, sources.conf says $S" >&2; exit 1; }
        echo "   $2: sha256 ok"
    else
        echo "   $2: commit $R"
    fi
}
fetch_all() {                          # fetch_all NAME FILE [NAME FILE ...]: the downloads in parallel, one failure stops the build
    P=""
    while [ $# -ge 2 ]; do fetch "$1" "$2" & P="$P $!"; shift 2; done
    F=0; for p in $P; do wait "$p" || F=1; done
    [ $F = 0 ] || { echo "a download failed (see above)" >&2; exit 1; }
}
target() {                             # docker build of a target of the Lab64 Dockerfile, with the downloaded sources
    mkdir -p "$DL"
    case $1 in
    viewer) fetch_all KASMVNC "kasmvnc-$KASMVNC_VERSION.deb" JSSID "jssid-$JSSID_VERSION.tar.gz" ;;
    tools)  fetch_all VICE "vice-$VICE_VERSION.tar.gz" TASS64 "64tass-$TASS64_VERSION-src.zip" \
                CC65 "cc65-$CC65_VERSION.tar.gz" CC1541 "cc1541-$CC1541_VERSION.tar.gz" ZX0 "zx0-$ZX0_VERSION.tar.gz" \
                LIBRESIDFP "libresidfp-$LIBRESIDFP_VERSION.tar.gz" LIBSIDPLAYFP "libsidplayfp-$LIBSIDPLAYFP_VERSION.tar.gz" \
                SIDPLAYFP "sidplayfp-$SIDPLAYFP_VERSION.tar.gz" ;;
    esac
    # shellcheck disable=SC2086
    DOCKER_BUILDKIT=1 docker build --progress=plain $SECRET --target "$1" -t "$2:$VER" -t "$2:latest" --build-arg JOBS="$JOBS" \
        --build-arg VICE_VERSION="$VICE_VERSION" --build-arg TASS64_VERSION="$TASS64_VERSION" --build-arg CC65_VERSION="$CC65_VERSION" \
        --build-arg CC1541_VERSION="$CC1541_VERSION" --build-arg ZX0_VERSION="$ZX0_VERSION" --build-arg KASMVNC_VERSION="$KASMVNC_VERSION" \
        --build-arg LIBRESIDFP_VERSION="$LIBRESIDFP_VERSION" --build-arg LIBSIDPLAYFP_VERSION="$LIBSIDPLAYFP_VERSION" --build-arg SIDPLAYFP_VERSION="$SIDPLAYFP_VERSION" \
        --build-arg WEASYPRINT_VERSION="$WEASYPRINT_VERSION" --build-arg JSSID_VERSION="$JSSID_VERSION" \
        --build-arg MATPLOTLIB_VERSION="$MATPLOTLIB_VERSION" --build-arg NUMPY_VERSION="$NUMPY_VERSION" \
        --build-context downloads="$DL" --build-context roms="$TC/roms" --build-context viewer-src="$TC/containers/viewer" "$TC/docker" >"$BUILD_LOG" 2>&1 || build_failed
}
for n in $NAMES; do
    if [ $FORCE = 0 ] && have "$n"; then continue; fi
    echo "== image lab64-$n =="
    # the images contain the Commodore ROMs (not in git, for the user's own use only): the build stops if they are missing or different
    case $n in pdf-gen) ;; *) "$TC/build-scripts/check_roms.sh" || exit 1 ;; esac
    case $n in
    tools|viewer|pdf-gen) target "$n" "lab64-$n" ;;
    vc64web)
        vc64web_pages
        # shellcheck disable=SC2086
        DOCKER_BUILDKIT=1 docker build --progress=plain $SECRET -t "lab64-vc64web:$VER" -t lab64-vc64web:latest --build-context pages="$TC/out/cache/vc64web" --build-context roms="$TC/roms" \
            "$TC/containers/vc64web" >"$BUILD_LOG" 2>&1 || build_failed ;;
    *) echo "unknown image: $n" >&2; exit 1 ;;
    esac
    echo "   lab64-$n:$VER $(docker image inspect -f '{{.Size}}' "lab64-$n:$VER" | awk '{printf "%.0f MB", $1/1e6}')"
done
# (14/11, owner's rule) what is needed ONLY to build an image is removed once the image exists: the sources are compiled into the
# images; to rebuild them (--force) they are downloaded again.
# The vc64web headless page is needed only by the image build (c64d.js has it in the container).
# (1.10) both pages (headless and portable) are IN the lab64-vc64web image, and the viewer shows the portable one through the daemon:
# nothing generated stays on the host, Lab64's out/ can be deleted at any time.
if have tools && have viewer; then rm -rf "$DL"
elif have tools; then rm -f "$DL"/vice-* "$DL"/64tass-* "$DL"/cc65-* "$DL"/cc1541-* "$DL"/zx0-* "$DL"/libresidfp-* "$DL"/libsidplayfp-* "$DL"/sidplayfp-*
elif have viewer; then rm -f "$DL"/kasmvnc-* "$DL"/jssid-*; fi
have vc64web && rm -rf "$TC/out/cache/vc64web"
true
