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
# C64_CA_BUNDLE=FILE: CA of a TLS-intercepting proxy, passed as a secret to the builds that download with npm (vc64web, viewer).
set -eu
TC=$(cd "$(dirname "$0")/.." && pwd)
. "$TC/build-scripts/sources.conf"
VER=$(cat "$TC/VERSION")
DL="$TC/downloads"
FORCE=0; [ "${1:-}" = "--force" ] && { FORCE=1; shift; }
NAMES="${*:-tools viewer vc64web pdf-gen}"
SECRET=""; [ -n "${C64_CA_BUNDLE:-}" ] && SECRET="--secret id=ca,src=$C64_CA_BUNDLE"
have() { docker image inspect "lab64-$1:$VER" >/dev/null 2>&1; }
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
target() {                             # docker build of a target of the Lab64 Dockerfile, with the downloaded sources
    mkdir -p "$DL"
    case $1 in
    viewer) fetch KASMVNC "kasmvnc-$KASMVNC_VERSION.deb"; fetch JSSID "jssid-$JSSID_VERSION.tar.gz" ;;
    tools)  fetch VICE "vice-$VICE_VERSION.tar.gz"; fetch TASS64 "64tass-$TASS64_VERSION-src.zip"
            fetch CC65 "cc65-$CC65_VERSION.tar.gz"; fetch CC1541 "cc1541-$CC1541_VERSION.tar.gz"; fetch ZX0 "zx0-$ZX0_VERSION.tar.gz"
            fetch LIBRESIDFP "libresidfp-$LIBRESIDFP_VERSION.tar.gz"; fetch LIBSIDPLAYFP "libsidplayfp-$LIBSIDPLAYFP_VERSION.tar.gz"
            fetch SIDPLAYFP "sidplayfp-$SIDPLAYFP_VERSION.tar.gz" ;;
    esac
    # shellcheck disable=SC2086
    DOCKER_BUILDKIT=1 docker build -q $SECRET --target "$1" -t "$2:$VER" -t "$2:latest" \
        --build-arg VICE_VERSION="$VICE_VERSION" --build-arg TASS64_VERSION="$TASS64_VERSION" --build-arg CC65_VERSION="$CC65_VERSION" \
        --build-arg CC1541_VERSION="$CC1541_VERSION" --build-arg ZX0_VERSION="$ZX0_VERSION" --build-arg KASMVNC_VERSION="$KASMVNC_VERSION" \
        --build-arg LIBRESIDFP_VERSION="$LIBRESIDFP_VERSION" --build-arg LIBSIDPLAYFP_VERSION="$LIBSIDPLAYFP_VERSION" --build-arg SIDPLAYFP_VERSION="$SIDPLAYFP_VERSION" \
        --build-arg WEASYPRINT_VERSION="$WEASYPRINT_VERSION" --build-arg JSSID_VERSION="$JSSID_VERSION" \
        --build-arg MATPLOTLIB_VERSION="$MATPLOTLIB_VERSION" --build-arg NUMPY_VERSION="$NUMPY_VERSION" \
        --build-context downloads="$DL" --build-context roms="$TC/roms" --build-context viewer-src="$TC/containers/viewer" "$TC/docker" >/dev/null
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
        DOCKER_BUILDKIT=1 docker build -q $SECRET -t "lab64-vc64web:$VER" -t lab64-vc64web:latest --build-context pages="$TC/out/cache/vc64web" --build-context roms="$TC/roms" \
            "$TC/containers/vc64web" >/dev/null ;;
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
