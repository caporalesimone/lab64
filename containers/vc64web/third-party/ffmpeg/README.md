# ffmpeg — NOT included

**What it is**: the encoder used by the daemon for the deterministic videos (`c64 video`, `video start` in scripts): H.264 (libx264). It is not in the package: it must be in the PATH (the Dockerfile installs it with `apt`, Debian package `ffmpeg`).

**Origin**: https://ffmpeg.org
**License**: LGPL-2.1+ or GPL-2+ depending on how it is compiled; builds that include libx264 (like the Debian one, as far as I remember, not verified) are GPL. If a Docker image containing it is published, those terms apply.
