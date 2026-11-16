#!/bin/sh
# Runs a command in a Lab64 container, with the project mounted at /work and Lab64 at /lab64 (read-only). Copyright (c) 2026 - Simone Caporale
# Normally started by the command line (lab64 run, lab64 build, ...): projects call "lab64", not this script.
#   run.sh tools make                    run.sh pdf-gen python3 tools/manual.py        run.sh tools    (interactive shell)
#   run.sh myproject-image:1 make        (an existing image by its full name)
# Name: tools, pdf-gen, ... = image lab64-<name>:<VERSION of Lab64>; the full name of an existing image is used as is.
# The project may require a Lab64 version: LAB64_VERSION in its lab64.env (it must match the file VERSION).
# Project: the current folder (or C64_PROJECT). Inside the container: LAB64=/lab64, the container lab64 command in the PATH and
# the Lab64 Python library importable (image ENV).
# Runs as the host user (the files in out/ stay theirs); HOME in out/tmp/home.
# Variables passed (when set): EMU_URL, C64_VIEW, DISPLAY, PULSE_SERVER, C64_MEMPROBE, C64_HOST_DIR, C64_EMU and those of C64_PASS_ENV
# (project lab64.env). They are passed by name (-e NAME), so values with spaces are safe; C64_DOCKER_ARGS is split on spaces.
# Extra docker options: C64_DOCKER_ARGS="--network lab64 ...". With the compose stack up (lab64 up) a tools command runs in
# the lab64-tools service with docker exec (C64_NO_EXEC=1: a new container anyway).
set -eu
TC=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "${C64_PROJECT:-.}" && pwd)
[ -f "$ROOT/lab64.env" ] && . "$ROOT/lab64.env"
[ $# -ge 1 ] || { sed -n 2,10p "$0"; exit 1; }
IMG=$1; shift
VER=$(cat "$TC/VERSION")
if [ -n "${LAB64_VERSION:-}" ] && [ "$LAB64_VERSION" != "$VER" ]; then
    echo "this project needs Lab64 $LAB64_VERSION (lab64.env), $TC is $VER" >&2; exit 1
fi
docker image inspect "$IMG" >/dev/null 2>&1 || IMG=lab64-$IMG:$VER
[ $# -ge 1 ] || set -- bash
TTY=""; if [ -t 0 ] && [ -t 1 ]; then TTY="-it"; fi
mkdir -p "$ROOT/out/tmp/home"
ENVS=""
for v in EMU_URL C64_VIEW DISPLAY PULSE_SERVER C64_MEMPROBE C64_HOST_DIR C64_EMU ${C64_PASS_ENV:-}; do
    eval "[ -n \"\${$v+x}\" ]" && ENVS="$ENVS -e $v"
done
# (15/11) the compose stack is up for THIS project (lab64 up): the command runs in its tools container (docker exec, no new
# container). Of C64_DOCKER_ARGS only the -e entries apply there (network and volumes are already part of the stack).
if [ "$IMG" = "lab64-tools:$VER" ] && [ -z "${C64_NO_EXEC:-}" ] &&
   [ "$(docker inspect -f '{{.State.Running}} {{index .Config.Labels "lab64.project"}}' lab64-tools 2>/dev/null)" = "true $ROOT" ]; then
    XE=""; P=""
    for w in ${C64_DOCKER_ARGS:-}; do [ "$P" = "-e" ] && XE="$XE -e $w"; P=$w; done
    # shellcheck disable=SC2086
    exec docker exec $TTY -u "$(id -u):$(id -g)" -w /work -e HOME=/work/out/tmp/home -e LANG=C.UTF-8 $ENVS $XE lab64-tools "$@"
fi
# Lab64 is mounted read-only, unless it IS the project (build-images.sh builds the vc64web pages in Lab64's own out/)
LRO=":ro"; [ "$TC" = "$ROOT" ] && LRO=""
# shellcheck disable=SC2086
exec docker run --rm $TTY --init -u "$(id -u):$(id -g)" -e HOME=/work/out/tmp/home -e LANG=C.UTF-8 -e LAB64=/lab64 $ENVS \
    ${C64_DOCKER_ARGS:-} -v "$ROOT":/work -v "$TC":/lab64$LRO -w /work "$IMG" "$@"
