#!/bin/sh
# Start-up of lab64-viewer (13/11). Copyright (c) 2026 - Simone Caporale
#   screen :99 = KasmVNC Xvnc (local clients without X authorization: -ac; socket only, no TCP; WebSocket on 127.0.0.1:6901)
#   audio = PulseAudio, virtual card "c64"; the clients (VICE in the other containers) use the anonymous socket /tmp/.X11-unix/pulse
#   web server on 6080 (server.js): index, live screen with audio, project out/
# Variables: VIEW_SIZE (1280x1000), VIEW_PASSWORD (optional), VIEW_DISK (disk proposed in the index), VIEW_TITLE, VIEW_PLAYER, VIEW_HOSTS.
set -e
G=$(printf '%s' "${VIEW_SIZE:-1280x1000}" | cut -dx -f1,2)          # also accepts the old 1280x1000x24 format
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 /tmp/.X11-unix/pulse
mkdir -p /tmp/.X11-unix /run/pulse; chmod 1777 /tmp/.X11-unix
pulseaudio --system --disallow-exit --disallow-module-loading --exit-idle-time=-1 -n \
  -L "module-null-sink sink_name=c64 rate=44100" \
  -L "module-native-protocol-unix auth-anonymous=1 socket=/run/pulse/native" \
  -L "module-native-protocol-unix auth-anonymous=1 socket=/tmp/.X11-unix/pulse" \
  -L "module-always-sink" --daemonize=yes --log-target=stderr 2>/tmp/pulse.log
mkdir -p /root/.vnc; touch /root/.kasmpasswd
# -PublicIP: without it, Xvnc 1.5 queries STUN servers on the Internet before opening the web port
Xvnc :99 -geometry "$G" -depth 24 -ac -nolisten tcp -extension MIT-SHM -PublicIP 127.0.0.1 \
  -websocketPort 6901 -interface 127.0.0.1 -disableBasicAuth -SecurityTypes None -sslOnly 0 -AlwaysShared \
  -httpd /usr/share/kasmvnc/www -RectThreads 0 -Log '*:stderr:30' > /tmp/xvnc.log 2>&1 &
for i in $(seq 50); do [ -S /tmp/.X11-unix/X99 ] && break; sleep 0.1; done
chmod 777 /tmp/.X11-unix/pulse 2>/dev/null || true
cd /opt/viewer && PULSE_SERVER=unix:/run/pulse/native exec node server.js
