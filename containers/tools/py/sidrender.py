#!/usr/bin/env python3
"""Renders a .sid file to WAV with sidplayfp (and to MP3 with ffmpeg). Copyright (c) 2026 - Simone Caporale

Generic (no project knowledge), runs in lab64-tools (sidplayfp in /opt/c64/bin, ffmpeg). Used by SID Studio (through the viewer
player daemon, containers/tools/py/viewer_player.py), by `lab64 publish` (C64_PUBLISH_SID_RENDER, containers/tools/py/c64publish.py) and from the command line:

    lab64 run python3 -m sidrender song.sid --subtune 2 --model 8580 --length 90 --fade 5 -o song.wav
    lab64 run python3 -m sidrender song.sid --engine sidlite --mute 1,3 --no-filter --json
    lab64 run python3 -m sidrender song.sid --mp3 song.mp3            (192 kbit/s)

    from sidrender import render, normalize
    r = render(open("song.sid", "rb").read(), {"subtune": 2, "model": "8580", "length": 90})
    r["path"], r["seconds"], r["took"], r["cached"]          (WAV in out/cache/sidrender/<sha256>.wav)

Parameters (defaults in DEFAULTS; everything is validated against a whitelist or a range, nothing but numbers and fixed option
strings ever reaches the sidplayfp command line; unknown names are refused):
  engine      residfp | sidlite            (libsidplayfp 3 has no classic reSID). residfp: the reSIDfp emulation; sidlite: the
                                           lightweight one. fcurve, frange, cw and old_caps exist only for residfp (ignored otherwise)
  model       auto | 6581 | 8580           auto = what the tune's header says (6581 when it says nothing). model_force: use it even
                                           if the tune asks for the other chip (explicit 6581 / 8580 without force = default only)
  video       auto | pal | ntsc            auto = the clock flags of the header (PAL when unknown); video_force: PAL / NTSC even if the
                                           tune was written for the other (no speed fixing: pitch and tempo follow the clock)
  subtune     1..number of subtunes        length / start / fade: seconds. length counts from start (the WAV lasts `length`);
  start       0..3600                      the fade-out is INSIDE the length (it ends at the end of the file, -fob)
  length      1..1200 (default 180)        fade: whole seconds 0..60, at most the length
  mute        voices 1..3 to silence       (-u)         filter: false = no SID filter emulation (-nf)
  digiboost   8580 digi volume boost       fcurve  null | "auto" | 0..1  filter curve (0 dark .. 1 bright; 6581 and 8580)
  frange      null | "auto" | 0..1         6581 filter range ("auto" = the recommended value for the tune's author, when known;
                                           in this sidplayfp version fcurve "auto" does the same: it is one switch for both)
  cw          null | w | a | s             combined waveforms weak / average / strong      old_caps  6581 with the old (330 pF) capacitors
  bits        16 | 32                      16-bit PCM or 32-bit float WAV (44100 Hz; mono, or stereo for tunes with two SID chips)
Reproducibility: the power-on delay of the C64 is random by default in sidplayfp; here it is ALWAYS fixed (--delay=0) and the ini
file (Lab64 ROMs, defaults) is written fresh for every render, so the same file and parameters give the same bytes. The cache key is
the SHA-256 of the file bytes + the normalized parameters + the sidplayfp version and binary hash.
ROMs: KERNAL 901227-03, BASIC 901226-01 and chargen 901225-01 of Lab64 (roms/vice-roms/C64) are given to sidplayfp: RSID tunes need them."""
import hashlib, json, math, os, re, shutil, struct, subprocess, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "common", "py"))   # psid, d64, lab64env
import psid  # noqa: E402  (containers/common/py/psid.py)
from lab64env import project  # noqa: E402  (containers/common/py/lab64env.py)

HERE = os.path.dirname(os.path.abspath(__file__))
ROMS = os.path.join(os.environ.get("C64_ROMS", "/opt/roms"), "vice-roms", "C64")   # the copy inside the image
SIDPLAYFP = "/opt/c64/bin/sidplayfp"
RATE = 44100
MAX_SID = 65536 + 0x7C + 8              # a PSID: header + 2-byte load address + up to 64 KB of data (+ v4 extras)
MAX_LENGTH, MAX_START, MAX_FADE = 1200, 3600, 60
CACHE_LIMIT = 1 << 30                   # the cache folder keeps at most 1 GiB (oldest files go first)
TIMEOUT = 300                           # seconds for one sidplayfp run
DEFAULT_LENGTH = 180
DEFAULTS = {"engine": "residfp", "model": "auto", "model_force": False, "video": "auto", "video_force": False, "subtune": 1,
            "start": 0, "length": DEFAULT_LENGTH, "fade": 0, "mute": [], "filter": True, "digiboost": False, "fcurve": None,
            "frange": None, "cw": None, "old_caps": False, "bits": 16}
ENGINES = {"residfp": "--residfp", "sidlite": "--sidlite"}


class SidRenderError(ValueError):
    """invalid file or parameters"""


def _num(v, name, lo, hi, nd=3):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < lo or v > hi:
        raise SidRenderError("%s must be a number from %s to %s" % (name, lo, hi))
    return round(float(v), nd)


def _bool(v, name):
    if not isinstance(v, bool):
        raise SidRenderError("%s must be true or false" % name)
    return v


def _choice(v, name, allowed):
    if not isinstance(v, str) or v not in allowed:
        raise SidRenderError("%s must be one of: %s" % (name, ", ".join(allowed)))
    return v


def normalize(params, songs=None):
    """the validated, complete, canonical parameters (a new dict); SidRenderError when something is wrong. songs: the number of
    subtunes of the file, when known (the subtune is checked against it)"""
    p = dict(DEFAULTS)
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise SidRenderError("params must be an object")
    for k in params:
        if k not in DEFAULTS:
            raise SidRenderError("unknown parameter: %s" % (k if isinstance(k, str) and re.fullmatch(r"[A-Za-z0-9_]{1,24}", k) else "?"))
    p.update(params)
    q = {}
    q["engine"] = _choice(p["engine"], "engine", list(ENGINES))
    q["model"] = _choice(p["model"], "model", ["auto", "6581", "8580"])
    q["model_force"] = _bool(p["model_force"], "model_force") and q["model"] != "auto"
    q["video"] = _choice(p["video"], "video", ["auto", "pal", "ntsc"])
    q["video_force"] = _bool(p["video_force"], "video_force") and q["video"] != "auto"
    st = p["subtune"]
    if isinstance(st, bool) or not isinstance(st, int) or st < 1 or st > (songs or 256):
        raise SidRenderError("subtune must be a whole number from 1 to %d" % (songs or 256))
    q["subtune"] = st
    q["start"] = _num(p["start"], "start", 0, MAX_START)
    q["length"] = _num(p["length"], "length", 1, MAX_LENGTH)
    f = p["fade"]
    if isinstance(f, bool) or not isinstance(f, int) or f < 0 or f > MAX_FADE or f > q["length"]:
        raise SidRenderError("fade must be a whole number of seconds from 0 to %d, at most the length" % MAX_FADE)
    q["fade"] = f
    m = p["mute"]
    if not isinstance(m, (list, tuple)) or len(m) > 3 or any(isinstance(x, bool) or x not in (1, 2, 3) for x in m):
        raise SidRenderError("mute must be a list of voices (1, 2, 3)")
    q["mute"] = sorted(set(m))
    q["filter"] = _bool(p["filter"], "filter")
    q["digiboost"] = _bool(p["digiboost"], "digiboost")
    for k in ("fcurve", "frange"):
        v = p[k]
        q[k] = None if v is None else "auto" if v == "auto" and isinstance(v, str) else _num(v, k + " (or \"auto\")", 0, 1, 4)
    q["cw"] = None if p["cw"] is None else _choice(p["cw"], "cw", ["w", "a", "s"])
    q["old_caps"] = _bool(p["old_caps"], "old_caps")
    b = p["bits"]
    if isinstance(b, bool) or b not in (16, 32):
        raise SidRenderError("bits must be 16 or 32")
    q["bits"] = int(b)
    if q["engine"] != "residfp":                        # residfp only: the same file would otherwise get several cache entries
        q["fcurve"] = q["frange"] = q["cw"] = None
        q["old_caps"] = False
    return q


def _time(s):                                           # sidplayfp [mins:]secs[.milli]: always M:SS.mmm
    ms = int(round(s * 1000))
    return "%d:%02d.%03d" % (ms // 60000, ms // 1000 % 60, ms % 1000)


def command(q, wav, sid):
    """the sidplayfp argument list (a list: no shell) for the normalized parameters q"""
    c = [SIDPLAYFP, "-q", "-w" + wav, "-t" + _time(q["length"]), "-os%d" % q["subtune"], "-f%d" % RATE, "-p%d" % q["bits"],
         "--delay=0", ENGINES[q["engine"]]]
    if q["start"] > 0:
        c.append("-b" + _time(q["start"]))
    if q["fade"]:
        c.append("-fob%d" % q["fade"])
    if q["model"] != "auto":
        c.append({"6581": "-mo", "8580": "-mn"}[q["model"]] + ("f" if q["model_force"] else ""))
    if q["video"] != "auto":
        c.append({"pal": "-vp", "ntsc": "-vn"}[q["video"]] + ("f" if q["video_force"] else ""))
    c += ["-u%d" % v for v in q["mute"]]
    if not q["filter"]:
        c.append("-nf")
    if q["digiboost"]:
        c.append("--digiboost")
    for k in ("fcurve", "frange"):
        if q[k] is not None:
            c.append("--%s=%s" % (k, q[k] if q[k] == "auto" else "%.4f" % q[k]))
    if q["cw"]:
        c.append("-cw" + q["cw"])
    if q["old_caps"]:
        c.append("-co")
    return c + [sid]


def _ini():
    """sidplayfp.ini written for every render: the Lab64 ROMs and fixed defaults (so no user or system file changes the sound)"""
    rom = lambda f: os.path.realpath(os.path.join(ROMS, f))
    return "\n".join(["[SIDPlayfp]", "Version = 2", "Songlength Database =", "Default Play Length = 0:00", "Default Record Length = 3:00",
                      "Kernal Rom = " + rom("kernal-901227-03.bin"), "Basic Rom = " + rom("basic-901226-01.bin"),
                      "Chargen Rom = " + rom("chargen-901225-01.bin"), "VerboseLevel = 0", "",
                      "[Console]", "Ansi = false", "", "[Audio]", "Frequency = %d" % RATE, "Channels = 0", "BitsPerSample = 16", "",
                      "[Emulation]", "Engine = RESIDFP", "C64Model = PAL", "ForceC64Model = false", "DigiBoost = false",
                      "SidModel = MOS6581", "ForceSidModel = false", "UseFilter = true", "FilterCurve6581 = 0.5",
                      "FilterRange6581 = 0.5", "FilterCurve8580 = 0.5", "CombinedWaveforms = AVERAGE", "Old6581Caps = false",
                      "PowerOnDelay = 0", "Sampling = RESAMPLE", "ResidFastSampling = false", ""])


_version = []


def version():
    """`sidplayfp --version` + a hash of the binary (part of the cache key: another build may sound different)"""
    if not _version:
        try:
            out = subprocess.run([SIDPLAYFP, "--version"], capture_output=True, text=True, timeout=20).stdout
            with open(SIDPLAYFP, "rb") as f:
                _version.append(" ".join(out.split("\n")[0:2]).strip() + " " + hashlib.sha256(f.read()).hexdigest()[:16])
        except (OSError, subprocess.SubprocessError):
            raise RuntimeError("sidplayfp not found (%s): run it in lab64-tools" % SIDPLAYFP)
    return _version[0]


def wav_info(path):
    """{"rate", "channels", "bits", "float", "frames", "seconds"} read from the RIFF/WAVE chunks (also 32-bit float files)"""
    with open(path, "rb") as f:
        h = f.read(12)
        if h[:4] != b"RIFF" or h[8:12] != b"WAVE":
            raise RuntimeError("not a WAV file")
        fmt = None
        while True:
            ch = f.read(8)
            if len(ch) < 8:
                raise RuntimeError("WAV without data")
            n = struct.unpack("<I", ch[4:])[0]
            if ch[:4] == b"fmt ":
                fmt = struct.unpack("<HHIIHH", f.read(16)); f.seek(n - 16, 1)
            elif ch[:4] == b"data":
                if fmt is None:
                    raise RuntimeError("WAV: data before fmt")
                tag, chn, rate, _, ba, bits = fmt
                size = min(n, os.path.getsize(path) - f.tell())
                frames = size // ba
                return {"rate": rate, "channels": chn, "bits": bits, "float": tag == 3, "frames": frames, "seconds": round(frames / rate, 3)}
            else:
                f.seek(n + (n & 1), 1)


def cache_dir(root=None):
    return os.path.join(project(root), "out", "cache", "sidrender")


def key(data, q):
    """the cache key: SHA-256 of the file bytes + the normalized parameters + the sidplayfp version"""
    h = hashlib.sha256(data)
    h.update(b"\0" + json.dumps(q, sort_keys=True, separators=(",", ":")).encode() + b"\0" + version().encode())
    return h.hexdigest()


def _prune(d, keep):
    try:
        fs = [(e.stat().st_mtime, e.stat().st_size, e.path) for e in os.scandir(d) if e.is_file() and re.fullmatch(r"[0-9a-f]{64}\.(wav|mp3)", e.name)]
    except OSError:
        return
    total = sum(s for _, s, _ in fs)
    for _, s, p in sorted(fs):
        if total <= CACHE_LIMIT:
            break
        if p != keep:
            try:
                os.remove(p); total -= s
            except OSError:
                pass


def render(data, params=None, root=None, timeout=TIMEOUT):
    """renders the .sid bytes with the parameters; returns {"path", "file" (name in the cache folder), "key", "seconds" (length of
    the WAV), "took" (render time, 0 when cached), "cached", "params" (normalized), "tune" (header), "rate", "channels", "bits"}.
    SidRenderError for a bad file or parameters, RuntimeError when sidplayfp fails."""
    if not isinstance(data, (bytes, bytearray)):
        raise SidRenderError("the .sid must be bytes")
    if len(data) > MAX_SID:
        raise SidRenderError("the .sid is too large (%d bytes, at most %d)" % (len(data), MAX_SID))
    try:
        tune = psid.info(bytes(data))
    except ValueError as e:
        raise SidRenderError(str(e))
    q = normalize(params, tune["songs"])
    k = key(bytes(data), q)
    d = cache_dir(root)
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, k + ".wav")
    base = {"path": out, "file": k + ".wav", "key": k, "params": q, "tune": tune}
    if os.path.isfile(out):
        try:
            os.utime(out)
            return dict(base, took=0.0, cached=True, **_wavmeta(out))
        except (OSError, RuntimeError):
            pass                                        # damaged entry: render again
    work = tempfile.mkdtemp(prefix=".work-", dir=d)
    try:
        cfg = os.path.join(work, "cfg", "sidplayfp")
        os.makedirs(cfg)
        with open(os.path.join(cfg, "sidplayfp.ini"), "w") as f:
            f.write(_ini())
        sid, tmp = os.path.join(work, "in.sid"), os.path.join(work, "out.wav")
        with open(sid, "wb") as f:
            f.write(data)
        env = {"PATH": "/opt/c64/bin:/usr/bin:/bin", "HOME": work, "XDG_CONFIG_HOME": os.path.join(work, "cfg"),
               "XDG_DATA_HOME": os.path.join(work, "data"), "LANG": "C.UTF-8"}
        t0 = time.monotonic()
        try:
            r = subprocess.run(command(q, tmp, sid), env=env, cwd=work, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError("sidplayfp took more than %d s" % timeout)
        took = time.monotonic() - t0
        if r.returncode != 0 or not os.path.isfile(tmp):
            msg = (r.stderr.decode("utf-8", "replace") + r.stdout.decode("utf-8", "replace")).strip().splitlines()
            raise RuntimeError("sidplayfp failed (exit %s): %s" % (r.returncode, " | ".join(msg[-3:])[:300]))
        meta = _wavmeta(tmp)
        os.replace(tmp, out)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    _prune(d, out)
    return dict(base, took=round(took, 3), cached=False, **meta)


def _wavmeta(path):
    w = wav_info(path)
    return {"seconds": w["seconds"], "rate": w["rate"], "channels": w["channels"], "bits": w["bits"]}


def mp3_name(sid_path, subtune, songs):
    """name of the published MP3 of a subtune, next to the .sid: <stem>.mp3 when the file has one subtune, else <stem>-<n>.mp3"""
    stem = os.path.splitext(sid_path)[0]
    return stem + ".mp3" if songs == 1 else "%s-%d.mp3" % (stem, subtune)


def to_mp3(wav, mp3, title="", artist="", kbps=192):
    """WAV -> MP3 (ffmpeg, libmp3lame, constant bit rate kbps, bit-exact flags: the same input gives the same file)"""
    clean = lambda t: "".join(c for c in str(t) if c.isprintable())[:100]
    tmp = mp3 + ".part"
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-fflags", "+bitexact", "-i", wav, "-map_metadata", "-1", "-flags:a", "+bitexact",
           "-codec:a", "libmp3lame", "-b:a", "%dk" % kbps, "-id3v2_version", "3", "-write_xing", "0"]
    if title:
        cmd += ["-metadata", "title=" + clean(title)]
    if artist:
        cmd += ["-metadata", "artist=" + clean(artist)]
    r = subprocess.run(cmd + ["-f", "mp3", tmp], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError("ffmpeg failed: " + r.stderr.strip()[-300:])
    os.replace(tmp, mp3)


def _parser():
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m sidrender", description="render a .sid file to WAV (sidplayfp); see containers/tools/py/sidrender.py")
    ap.add_argument("sid", help=".sid file")
    ap.add_argument("-o", "--output", help="copy the WAV here (default: only the cache, out/cache/sidrender/<key>.wav)")
    ap.add_argument("--mp3", help="also write this MP3 (192 kbit/s)")
    ap.add_argument("--engine", choices=list(ENGINES))
    ap.add_argument("--model", choices=["auto", "6581", "8580"])
    ap.add_argument("--force-model", action="store_true", help="use --model even if the tune asks for the other chip")
    ap.add_argument("--video", choices=["auto", "pal", "ntsc"])
    ap.add_argument("--force-video", action="store_true", help="use --video even if the tune was written for the other standard")
    ap.add_argument("--subtune", type=int)
    ap.add_argument("--start", type=float, help="seconds skipped at the start")
    ap.add_argument("--length", type=float, help="seconds (default %d)" % DEFAULT_LENGTH)
    ap.add_argument("--fade", type=int, help="fade-out seconds (inside the length)")
    ap.add_argument("--mute", help="voices to mute, e.g. 1,3")
    ap.add_argument("--no-filter", action="store_true")
    ap.add_argument("--digiboost", action="store_true")
    ap.add_argument("--fcurve", help="0..1 or auto (residfp)")
    ap.add_argument("--frange", help="0..1 or auto (residfp, 6581)")
    ap.add_argument("-cw", "--cw", choices=["w", "a", "s"], help="combined waveforms weak / average / strong (residfp)")
    ap.add_argument("-co", "--old-caps", action="store_true", help="6581 with the old capacitors (residfp)")
    ap.add_argument("--bits", type=int, choices=[16, 32])
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    return ap


def main(argv):
    a = _parser().parse_args(argv)
    p = {}
    for name in ("engine", "model", "video", "subtune", "start", "length", "fade", "cw", "bits"):
        if getattr(a, name) is not None:
            p[name] = getattr(a, name)
    p.update(model_force=a.force_model, video_force=a.force_video, filter=not a.no_filter, digiboost=a.digiboost, old_caps=a.old_caps)
    try:
        if a.mute:
            p["mute"] = [int(x) for x in a.mute.split(",")]
        for k in ("fcurve", "frange"):
            v = getattr(a, k)
            if v is not None:
                p[k] = v if v == "auto" else float(v)
    except ValueError:
        sys.exit("sidrender: --mute is a list of voices (1,2,3), --fcurve / --frange a number or auto")
    try:
        with open(a.sid, "rb") as f:
            data = f.read(MAX_SID + 1)
        r = render(data, p)
        if a.output:
            shutil.copyfile(r["path"], a.output)
        if a.mp3:
            to_mp3(r["path"], a.mp3, r["tune"]["name"], r["tune"]["author"])
    except (SidRenderError, RuntimeError, OSError) as e:
        sys.exit("sidrender: %s" % e)
    if a.json:
        print(json.dumps({k: r[k] for k in ("path", "seconds", "took", "cached", "key", "params", "rate", "channels")}))
    else:
        print("%s  %.1f s of audio, rendered in %.2f s (%s)%s" % (a.output or r["path"], r["seconds"], r["took"],
              "%.0fx real time" % (r["seconds"] / r["took"]) if r["took"] else "from the cache", "  + " + a.mp3 if a.mp3 else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
