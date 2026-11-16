# Rendering SID files

Copyright © 2026 - Simone Caporale

`containers/tools/py/sidrender.py`. `sidplayfp` (libsidplayfp 3.1.2 + libresidfp 1.3.0, compiled in the image) renders a `.sid` to a WAV file faster than real time, with
no audio device. `sidrender.py` is the one way Lab64 runs it (SID Studio, `lab64 publish` and you). SID Studio and its `/render`
endpoint are in [viewer.md](viewer.md); `C64_PUBLISH_SID_RENDER` is in [configuration.md](configuration.md).

```sh
lab64 run python3 -m sidrender song.sid -o song.wav                       # 3:00, reSIDfp, what the header says
lab64 run python3 -m sidrender song.sid --subtune 2 --model 8580 --force-model --video ntsc --force-video --length 90 --fade 5
lab64 run python3 -m sidrender song.sid --mute 1,3 --no-filter --fcurve 0.3 --frange auto -cw s -co --bits 32 --json
lab64 run python3 -m sidrender song.sid --engine sidlite --mp3 song.mp3   # 192 kbit/s MP3 too (ffmpeg)
```

```python
from sidrender import render
r = render(open("song.sid", "rb").read(), {"subtune": 2, "model": "8580", "length": 90})
r["path"], r["seconds"], r["took"], r["cached"]
```

| Parameter | Values |
|---|---|
| `engine` | `residfp` (default) or `sidlite`. libsidplayfp 3 **dropped the classic reSID**; `fcurve`, `frange`, `cw`, `old_caps` exist only for `residfp` |
| `model`, `model_force` | `auto` (the header's SID model flag, 6581 when it says nothing) / `6581` / `8580`; with `model_force` the choice also overrides a tune that asks for the other chip (`-mo`/`-mn`, `-mof`/`-mnf`) |
| `video`, `video_force` | `auto` (the header's clock flags, PAL when unknown) / `pal` / `ntsc`; forced: pitch and tempo follow the clock (`-vp`/`-vn`, `-vpf`/`-vnf`) |
| `subtune` | 1 .. number of subtunes of the file |
| `start`, `length`, `fade` | seconds: skipped at the start (0 .. 3600), length of the WAV (1 .. 1200, default 180), whole seconds of fade-out **inside** the length (0 .. 60) |
| `mute` | voices to silence, a list of 1, 2, 3 (`-u`) |
| `filter` | `false` = no filter emulation (`-nf`) |
| `digiboost` | 8580 digi boost |
| `fcurve`, `frange` | `null`, `"auto"` or 0 .. 1: reSIDfp filter curve (0 dark .. 1 bright) and 6581 filter range. In this sidplayfp `auto` is one switch for both: the range recommended for the tune's author, when known |
| `cw` | `w`, `a`, `s`: weak / average / strong combined waveforms |
| `old_caps` | 6581 with the old (330 pF) capacitors (`-co`) |
| `bits` | 16 (PCM) or 32 (float) |

Output: 44100 Hz, mono (stereo for tunes with two SID chips). **Reproducible**: sidplayfp's power-on delay is random unless set, so
`--delay=0` is always passed (the C64 starts the same every time), and the ini file (the Lab64 KERNAL, BASIC and chargen ROMs of
`roms/vice-roms/C64`, so RSID tunes work, plus fixed defaults) is written fresh for every render in a private folder: no user or system
file changes the sound. The same file and parameters give the same bytes on one machine (the SIMD paths of reSIDfp may differ in the
last bits between CPUs). Every parameter is checked against a whitelist or a range, unknown names are refused, the command line is a
list (no shell) made only of fixed options and numbers. WAVs are cached in `out/cache/sidrender/<sha256>.wav`, the key being the
SHA-256 of the file bytes + the normalized parameters + the sidplayfp build; the folder is kept under 1 GiB (oldest first). `render()` returns
the path, the duration, the render time (0 when cached) and the normalized parameters. **Speed** (2 vCPU Xeon 2.1 GHz, 12 renders
of 60 s from three tunes): reSIDfp 6581 about 10.5x real time, 8580 about 14.5x, sidlite about 80x; a 3:00 tune takes about 15 s.
