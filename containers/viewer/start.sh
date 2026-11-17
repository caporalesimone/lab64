#!/bin/sh
# Start-up of lab64-viewer (13/11). Copyright (c) 2026 - Simone Caporale
#   screen :99 = KasmVNC Xvnc, started and stopped by server.js on request (1.12: OFF by default, the remote screen costs CPU; VIEW_SCREEN=on
#   starts it with the viewer; lab64 screen on|off, or the switch in the page) - see startScreen() in server.js
#   audio = PulseAudio, virtual card "c64"; the clients (VICE in the other containers) use the anonymous socket /tmp/.X11-unix/pulse
#   web server on 6080 (server.js): index, live screen with audio, project out/
# Variables: VIEW_SIZE (1280x1000), VIEW_SCREEN (off|on), VIEW_PASSWORD (optional), VIEW_DISK (disk proposed in the index), VIEW_TITLE, VIEW_PLAYER, VIEW_HOSTS.
set -e
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 /tmp/.X11-unix/pulse
mkdir -p /tmp/.X11-unix /run/pulse; chmod 1777 /tmp/.X11-unix
pulseaudio --system --disallow-exit --disallow-module-loading --exit-idle-time=-1 -n \
  -L "module-null-sink sink_name=c64 rate=44100" \
  -L "module-native-protocol-unix auth-anonymous=1 socket=/run/pulse/native" \
  -L "module-native-protocol-unix auth-anonymous=1 socket=/tmp/.X11-unix/pulse" \
  -L "module-always-sink" --daemonize=yes --log-target=stderr 2>/tmp/pulse.log
mkdir -p /root/.vnc; touch /root/.kasmpasswd
chmod 777 /tmp/.X11-unix/pulse 2>/dev/null || true
cd /opt/viewer && PULSE_SERVER=unix:/run/pulse/native exec node server.js
