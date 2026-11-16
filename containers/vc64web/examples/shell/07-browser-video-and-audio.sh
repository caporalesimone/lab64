#!/bin/sh
# Video + audio from the browser (real time, not deterministic). The core must be running.
set -e; . "$(dirname "$0")/common.sh"
$C64 --quiet start; $C64 --quiet resume
# test SID tone: volume 15, voice 1 triangle
$C64 --quiet poke 0xD418 15; $C64 --quiet poke 0xD405 0; $C64 --quiet poke 0xD406 0xF0; $C64 --quiet poke 0xD401 0x20; $C64 --quiet poke 0xD404 0x11
# a) 3 seconds with keyboard and joystick below the video, amplified audio (the core audio is very low)
$C64 --out "$OUT/grab.webm" --compact grabBrowserVideoAndAudio '{"seconds":3,"keyboard":"below","joy2":"below","audioGain":8}'
# b) separate start and stop (in between you can use the emulator, also with "c64 script")
$C64 grabBrowserVideoAndAudio '{"action":"start","joy2":"overlay"}'
$C64 sendText 'print "hello"\n'; $C64 --quiet sleep 2000
$C64 --out "$OUT/grab2.webm" grabBrowserVideoAndAudio '{"action":"stop"}'
ffmpeg -y -loglevel error -i "$OUT/grab.webm" "$OUT/grab.mp4" && echo "converted to $OUT/grab.mp4"
