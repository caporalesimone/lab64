# Lab64 images (13/11, Lab64 since 14/11): ONE multi-stage Dockerfile, one image per target. Copyright (c) 2026 - Simone Caporale
#   build-scripts/build-images.sh [--force] [names]     (passes the contexts and arguments below; no need to run docker build by hand)
#
#   base            ubuntu + CA + locale + /work. Stage WITHOUT an image name: it never runs, it is only the common parent.
#   tools-builder   base + compilers and development libraries. Only for the compile stages: it never becomes an image.
#   vice-build      VICE, from the official tarball
#   tass64-build    64tass, from the official source zip
#   cc65-build      cc65 (cc65, ca65, ld65 + libraries and configs), from the repository at a fixed commit
#   cc1541-build    cc1541, from the upstream tarball
#   zx0-build       zx0, from the repository at a fixed commit
#   sidplayfp-build libresidfp + libsidplayfp + sidplayfp (SID player, renders .sid to WAV), from the release tarballs, static
#                   (all sources: build context "downloads" = downloads/, filled on the host by build-images.sh from sources.conf)
#   builder         base + make, perl, Python generators + 64tass, cc65, zx0, cc1541 (/opt/c64). Internal stage: no image
#   tools           builder + VICE (x64sc, c1541 and their data in /opt/vice) + sidplayfp (/opt/c64/bin) + libraries, Xvfb, ffmpeg -> lab64-tools
#   viewer          base + KasmVNC Xvnc, PulseAudio, Node server (index, screen with audio)       -> lab64-viewer
#   pdf-gen         base + Python 3, PyYAML, Pillow, pango, DejaVu fonts + WeasyPrint (venv)      -> lab64-pdf-gen
# Compilers live ONLY in the *-build stages: the final images get the programs already compiled (COPY --from). The BuildKit cache
# keeps the compiled stages: they are recompiled only when a source or the base changes (docker builder prune empties the cache).
# Builder and VICE are ONE image (14/11): the tests assemble variants (64tass) and run them in VICE in the same container.
# The secondary emulator (lab64-vc64web) has its own Dockerfile in the self-contained package containers/vc64web/ (official node base).
# Ubuntu version in ONE place: ARG UBUNTU (changing it rebuilds all the images and recompiles the external programs).
ARG UBUNTU=24.04

FROM ubuntu:${UBUNTU} AS base
ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
CMD ["bash"]

# --- compilers and development libraries (same base as the final images: the binaries use the same libraries)
FROM base AS tools-builder
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential autoconf automake pkg-config flex bison xa65 dos2unix texinfo file unzip \
        libpng-dev libgif-dev libjpeg-dev libasound2-dev libpulse-dev libcurl4-openssl-dev libevdev-dev \
        libmpg123-dev libvorbis-dev libflac-dev libfontconfig1-dev zlib1g-dev libgtk-3-dev libglew-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src

# Every *-build stage copies its result into /out (bin/ and share/), plus the license of the program in /out/licenses/<name>.
# VICE (gtk3; headless tried and dropped: segfault at start-up). Installed in /opt/vice: the data is where the executable looks
# for it (/opt/vice/share/vice), so no copies next to the executable.
FROM tools-builder AS vice-build
ARG VICE_VERSION
COPY --from=downloads vice-${VICE_VERSION}.tar.gz /src/
RUN tar xzf vice-${VICE_VERSION}.tar.gz && cd vice-${VICE_VERSION} \
    && ./configure --prefix=/opt/vice --enable-gtk3ui --disable-pdf-docs --without-oss > /src/configure.log 2>&1 \
    && make -j"$(nproc)" > /src/make.log 2>&1 && make install > /src/install.log 2>&1 \
    || { tail -30 /src/*.log; exit 1; }
# only what is needed goes into the image: x64sc (C64), c1541 (disks) and the data (~9 MB). A failed copy stops the build; only
# "x64sc --version" may fail (its output is informative). Separate layer: changing it never recompiles VICE.
RUN mkdir -p /out/bin /out/licenses && cp /opt/vice/bin/x64sc /opt/vice/bin/c1541 /out/bin/ && cp -a /opt/vice/share /out/share \
    && cp vice-${VICE_VERSION}/COPYING /out/licenses/vice \
    && { /out/bin/x64sc --version > /out/VERSION.txt 2>&1 || true; }

FROM tools-builder AS tass64-build
ARG TASS64_VERSION
COPY --from=downloads 64tass-${TASS64_VERSION}-src.zip /src/
RUN unzip -q 64tass-${TASS64_VERSION}-src.zip && make -s -C 64tass-${TASS64_VERSION}-src -j"$(nproc)" >/dev/null \
    && mkdir -p /out/bin /out/licenses && cp 64tass-${TASS64_VERSION}-src/64tass /out/bin/ \
    && cp 64tass-${TASS64_VERSION}-src/LICENSE-GPL-2.0 /out/licenses/64tass

FROM tools-builder AS cc65-build
ARG CC65_VERSION
COPY --from=downloads cc65-${CC65_VERSION}.tar.gz /src/
RUN tar xzf cc65-${CC65_VERSION}.tar.gz && cd cc65-${CC65_VERSION} \
    && make -j"$(nproc)" PREFIX=/opt/c64 > /src/make.log 2>&1 && make install PREFIX=/opt/c64 > /src/install.log 2>&1 \
    || { tail -30 /src/*.log; exit 1; }
# PREFIX=/opt/c64 is compiled into the programs (where cc65 / ld65 look for their libraries and configs): same path in the image
RUN rm -rf /opt/c64/share/man /opt/c64/share/doc && mkdir -p /out /opt/c64/licenses \
    && cp cc65-${CC65_VERSION}/LICENSE /opt/c64/licenses/cc65 && cp -a /opt/c64/. /out/

FROM tools-builder AS cc1541-build
ARG CC1541_VERSION
COPY --from=downloads cc1541-${CC1541_VERSION}.tar.gz /src/
RUN tar xzf cc1541-${CC1541_VERSION}.tar.gz && make -s -C cc1541-${CC1541_VERSION} cc1541 >/dev/null \
    && mkdir -p /out/bin /out/licenses && cp cc1541-${CC1541_VERSION}/cc1541 /out/bin/ \
    && cp cc1541-${CC1541_VERSION}/LICENSE.txt /out/licenses/cc1541

FROM tools-builder AS zx0-build
ARG ZX0_VERSION
COPY --from=downloads zx0-${ZX0_VERSION}.tar.gz /src/
RUN tar xzf zx0-${ZX0_VERSION}.tar.gz && cd zx0-${ZX0_VERSION}/src \
    && mkdir -p /out/bin /out/licenses && gcc -O2 -fcommon -o /out/bin/zx0 zx0.c optimize.c compress.c memory.c \
    && cp ../LICENSE /out/licenses/zx0

# sidplayfp (SID renderer): libresidfp (SID emulation) and libsidplayfp (player engine) as static libraries, then the sidplayfp
# program linked against them: no extra runtime libraries (libstdc++ and libgcc static too; the audio backend, miniaudio, loads the
# system audio libraries with dlopen only when a sound device is used: "sidplayfp -w" writes a file and needs none).
# pkg-config --static: the private dependencies of the static libraries come with them.
FROM tools-builder AS sidplayfp-build
ARG LIBRESIDFP_VERSION
ARG LIBSIDPLAYFP_VERSION
ARG SIDPLAYFP_VERSION
COPY --from=downloads libresidfp-${LIBRESIDFP_VERSION}.tar.gz libsidplayfp-${LIBSIDPLAYFP_VERSION}.tar.gz sidplayfp-${SIDPLAYFP_VERSION}.tar.gz /src/
ENV PKG_CONFIG_PATH=/opt/sidplayfp/lib/pkgconfig PKG_CONFIG="pkg-config --static"
# libresidfp: --with-simd=runtime picks the SSE / AVX code of the resampler when the CPU has it (about 3x faster than none); the
# default build is plain C++. (The sums differ in the last bits between CPUs: renders are reproducible on one machine.)
RUN for p in libresidfp-${LIBRESIDFP_VERSION} libsidplayfp-${LIBSIDPLAYFP_VERSION}; do \
        tar xzf $p.tar.gz && cd $p \
        && ./configure --prefix=/opt/sidplayfp --enable-static --disable-shared --disable-dependency-tracking $([ "${p#libresidfp}" != "$p" ] && echo --with-simd=runtime) CXXFLAGS="-O2" > /src/$p.configure.log 2>&1 \
        && make -j"$(nproc)" > /src/$p.make.log 2>&1 && make install > /src/$p.install.log 2>&1 \
        || { tail -30 /src/*.log; exit 1; }; \
        cd /src; \
    done
RUN tar xzf sidplayfp-${SIDPLAYFP_VERSION}.tar.gz && cd sidplayfp-${SIDPLAYFP_VERSION} \
    && ./configure --prefix=/opt/sidplayfp --disable-dependency-tracking CXXFLAGS="-O2" LDFLAGS="-static-libstdc++ -static-libgcc" > /src/sidplayfp.configure.log 2>&1 \
    && make -j"$(nproc)" > /src/sidplayfp.make.log 2>&1 \
    || { tail -30 /src/sidplayfp*.log; exit 1; }
RUN mkdir -p /out/bin /out/licenses && cp sidplayfp-${SIDPLAYFP_VERSION}/src/sidplayfp /out/bin/ && strip /out/bin/sidplayfp \
    && cp libresidfp-${LIBRESIDFP_VERSION}/COPYING /out/licenses/libresidfp && cp libsidplayfp-${LIBSIDPLAYFP_VERSION}/COPYING /out/licenses/libsidplayfp \
    && cp sidplayfp-${SIDPLAYFP_VERSION}/COPYING /out/licenses/sidplayfp \
    && { ldd /out/bin/sidplayfp > /out/ldd.txt; cat /out/ldd.txt; /out/bin/sidplayfp --help | head -3; }

# --- building C64 programs. No VICE, display or C compiler.
#   64tass                  6502 assembler (/opt/c64/bin)
#   cc65                    cc65, ca65, ld65 and their libraries (/opt/c64/bin, /opt/c64/share/cc65): Krill's Loader
#   make perl unzip         Krill's Loader build (from its zip)
#   python3 + pil/yaml/numpy/matplotlib   generators, atlas, maps, simulators (matplotlib: simulator charts)
#   git zip                 branch versions and zip archives
#   zx0, cc1541             compressor and disk writer (/opt/c64/bin, in the PATH)
#   licenses of the programs compiled here: /opt/c64/licenses/
# --- Matplotlib and NumPy from PyPI (15/11): a venv that also sees the Ubuntu packages (Pillow, PyYAML); pip stays here
FROM base AS py-build
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pil python3-yaml \
    && rm -rf /var/lib/apt/lists/*
ARG MATPLOTLIB_VERSION
ARG NUMPY_VERSION
RUN --mount=type=secret,id=ca if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    python3 -m venv --system-site-packages /opt/py \
    && /opt/py/bin/pip install --no-cache-dir -q matplotlib==${MATPLOTLIB_VERSION} numpy==${NUMPY_VERSION} \
    && /opt/py/bin/pip uninstall -y -q pip && find /opt/py -name __pycache__ -prune -exec rm -rf {} +

# dpkg: no documentation, man pages or translations in the final images (the copyright files stay: licenses)
FROM base AS slim
RUN printf '%s\n' 'path-exclude=/usr/share/doc/*' 'path-include=/usr/share/doc/*/copyright' 'path-exclude=/usr/share/man/*' \
        'path-exclude=/usr/share/info/*' 'path-exclude=/usr/share/locale/*' 'path-exclude=/usr/share/lintian/*' \
        > /etc/dpkg/dpkg.cfg.d/01-lab64-slim

FROM slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 MPLBACKEND=Agg PATH=/opt/c64/bin:/opt/py/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends \
        make perl unzip zip git \
        python3 python3-pil python3-yaml \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'
COPY --from=tass64-build /out/ /opt/c64/
COPY --from=cc65-build /out/ /opt/c64/
COPY --from=cc1541-build /out/ /opt/c64/
COPY --from=zx0-build /out/ /opt/c64/
COPY --from=py-build /opt/py /opt/py

# --- VICE without a screen (tests, screenshots, measures, music rendering): VICE, its libraries, the virtual display and ffmpeg
# (WAV -> MP3). It starts from builder: the tests assemble variants (64tass).
FROM builder AS tools
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgtk-3-0t64 libglew2.2 libgl1 libpulse0 libasound2t64 libpng16-16t64 libevdev2 libcurl4t64 \
        xvfb xauth procps ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=vice-build /out/bin/ /opt/vice/bin/
COPY --from=vice-build /out/share/ /opt/vice/share/
COPY --from=vice-build /out/VERSION.txt /opt/vice/VERSION.txt
COPY --from=vice-build /out/licenses/ /opt/c64/licenses/
COPY --from=sidplayfp-build /out/bin/ /opt/c64/bin/
COPY --from=sidplayfp-build /out/licenses/ /opt/c64/licenses/
# (16/11, owner's rule) the ROMs are read from Lab64's roms/ folder ONLY at build time (build context "roms"); at run time everything uses this copy
COPY --from=roms . /opt/roms/
# Lab64 contract inside the containers (15/11): Lab64 mounted at /lab64 by run.sh; its container command line (containers/common/lab64-worker, linked as lab64)
# and its Python libraries (containers/common/py, containers/tools/py) importable, so project scripts never need a path to Lab64
ENV PATH=/opt/vice/bin:$PATH LAB64=/lab64 PYTHONPATH=/lab64/containers/common/py:/lab64/containers/tools/py C64_ROMS=/opt/roms
# (1.11) the container side of the lab64 command lives in the repository (mounted at /lab64 at run time): the link makes it "lab64" for the project scripts
RUN ln -s /lab64/containers/common/lab64-worker /usr/local/bin/lab64

# --- shared screen to watch in the browser, with audio (13/11): KasmVNC Xvnc (official package, context "downloads") + PulseAudio + Node server (containers/viewer/server.js) on http://localhost:6080.
# The other containers draw on the same screen and play sound by mounting the lab64-x11 volume (DISPLAY=:99,
# PULSE_SERVER=unix:/tmp/.X11-unix/pulse). The server uses pulseaudio2 (native module): compiled with the same node that runs it.
FROM base AS viewer-node
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm build-essential python3 libpulse-dev \
    && rm -rf /var/lib/apt/lists/*
COPY --from=viewer-src package.json /opt/viewer/
RUN --mount=type=secret,id=ca if [ -s /run/secrets/ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca; npm config set cafile /run/secrets/ca; fi; \
    cd /opt/viewer && npm install --omit=dev --no-audit --no-fund && rm -f package-lock.json
# jsSID (SID player of sid.html): only the script and its README (license) from the downloaded source, plus the Lab64 hooks
# (per-voice scope, mute, filter bypass: containers/viewer/jssid_patch.py) and its AudioWorklet build (jssid-worklet.js: the same patched
# core + containers/viewer/jssid_worklet_tail.js, generated by the same script)
ARG JSSID_VERSION
COPY --from=downloads jssid-${JSSID_VERSION}.tar.gz /tmp/
COPY --from=viewer-src jssid_patch.py jssid_worklet_tail.js /tmp/
RUN mkdir -p /opt/vendor/jssid && tar xzf /tmp/jssid-${JSSID_VERSION}.tar.gz -C /tmp \
    && cp /tmp/jssid-${JSSID_VERSION}/jsSID.js /tmp/jssid-${JSSID_VERSION}/README.txt /opt/vendor/jssid/ \
    && python3 /tmp/jssid_patch.py /opt/vendor/jssid/jsSID.js /opt/vendor/jssid/jssid-worklet.js

FROM slim AS viewer
ARG KASMVNC_VERSION
COPY --from=downloads kasmvnc-${KASMVNC_VERSION}.deb /tmp/kasmvnc.deb
# only the Xvnc libraries (the package dependencies WITHOUT perl, needed by the unused vncserver script) + the package files
RUN apt-get update && apt-get install -y --no-install-recommends \
        libfreetype6 libgbm1 libgl1 libpixman-1-0 libpng16-16t64 libssl3t64 libunwind8 libx11-6 libxau6 libxcursor1 libxdmcp6 \
        libxext6 libxfixes3 libxfont2 libxrandr2 libxshmfence1 libxtst6 xauth x11-xkb-utils xkb-data \
        pulseaudio nodejs procps \
    && dpkg-deb -x /tmp/kasmvnc.deb / && ln -sf /usr/bin/Xkasmvnc /usr/bin/Xvnc \
    && mkdir -p /opt/licenses && cp -r /usr/share/doc/kasmvncserver /opt/licenses/kasmvnc \
    && rm -rf /var/lib/apt/lists/* /tmp/kasmvnc.deb /usr/share/doc/kasmvncserver /usr/share/man/*
# (15/11) /usr/share/doc stays: the "slim" dpkg rule already leaves out the documentation and keeps the copyright files on
# purpose; only the KasmVNC files (unpacked with dpkg-deb, outside that rule, copied to /opt/licenses/kasmvnc) are removed
COPY --from=viewer-node /opt/viewer/node_modules /opt/viewer/node_modules
COPY --from=viewer-node /opt/vendor/ /opt/viewer/www/vendor/
COPY --from=viewer-src . /opt/viewer/
EXPOSE 6080
CMD ["sh", "/opt/viewer/start.sh"]

# --- HTML + CSS -> PDF (14/11): WeasyPrint in a virtual environment built with pip in a separate stage (pip never reaches the
# final image). The venv sees the Ubuntu packages (--system-site-packages: PyYAML, Pillow). No browser, no compilers.
FROM base AS pdf-build
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-yaml python3-pil \
    && rm -rf /var/lib/apt/lists/*
ARG WEASYPRINT_VERSION
RUN --mount=type=secret,id=ca if [ -s /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; \
    python3 -m venv --system-site-packages /opt/pdf && /opt/pdf/bin/pip install --no-cache-dir -q weasyprint==${WEASYPRINT_VERSION} \
    && /opt/pdf/bin/pip uninstall -y -q pip && mkdir -p /opt/pdf/licenses \
    && cp /opt/pdf/lib/python3*/site-packages/weasyprint-*.dist-info/licenses/LICENSE /opt/pdf/licenses/weasyprint 2>/dev/null \
    || cp /opt/pdf/lib/python3*/site-packages/weasyprint-*.dist-info/LICENSE /opt/pdf/licenses/weasyprint

FROM slim AS pdf-gen
ENV PYTHONDONTWRITEBYTECODE=1 PATH=/opt/pdf/bin:$PATH LAB64=/lab64 PYTHONPATH=/lab64/containers/common/py:/lab64/containers/pdf-gen
RUN ln -s /lab64/containers/common/lab64-worker /usr/local/bin/lab64
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-yaml python3-pil \
        libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=pdf-build /opt/pdf /opt/pdf
