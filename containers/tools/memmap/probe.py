#!/usr/bin/env python3
"""Run-time memory probe for VICE (14/11). Copyright (c) 2026 - Simone Caporale

Idea: right after the boot (BASIC at READY.) the RAM is filled with a known pattern; then the program runs (a test, a scenario);
at the end the whole RAM is saved. A byte that still holds the pattern was never written: the difference gives the memory that is
REALLY used while running, which the static analysis of containers/tools/memmap/c64map.py cannot see (data copied or unpacked at run
time, buffers behind pointers, the screen, decompression areas).

How a test library uses it (VICE remote monitor; nothing else is needed):
    for c in fill_commands(dir): monitor(c)       # after the boot, before loading the program
    ... run the scenario ...
    for c in dump_commands(path): monitor(c)      # at the end (the RAM under ROM and I/O too: "bank ram")
    write_meta(path, tag, disk)                   # which scenario and which disk, next to the dump
    (1.6) Vice.probe_checkpoint() saves more dumps in the middle of a session (same session id, increasing seq): see load()
containers/tools/memmap/c64map.py --probe DIR reads the dumps (only those made with the same disk as the map).

Limits:
  - probed RAM: $033C-$03FB (tape buffer), $0400-$07FF, $0803-$FFFF. Zero page, stack, $0200-$033B, $03FC-$03FF and $0800-$0802
    are used by BASIC/KERNAL at READY. (or must stay 0 for an empty BASIC program): not probed.
  - a byte written with the same value as the pattern looks untouched. The pattern never holds $00, $FF, $20 (the values used
    to clear memory and the screen) and changes at every address; for other data the chance is about 1 in 250 per byte.
    SECOND PASS (15/11): variant 2 of the pattern differs from variant 1 at every address. Running the scenarios once with each
    variant (C64_MEMPROBE=1, then C64_MEMPROBE=2, dumps in the same folder) removes those false "never written" bytes: a byte
    counts as never written only if it kept the pattern in every dump.
  - the monitor of the test library writes memory too (shortcuts of the tests, routine stubs): those bytes count as written.
  - only what the scenarios run is seen: code never run in the tests leaves its area as "loaded but not run"."""
import hashlib, json, os

RANGES = [(0x033C, 0x03FB), (0x0400, 0x07FF), (0x0803, 0xFFFF)]     # (start, end included)
SKIP = {0x00, 0xFF, 0x20}


def pattern(a, variant=1):
    """pattern byte of address a: changes at every address, never $00 / $FF / $20; variant 2 differs from 1 at every address"""
    v = (a * 157 + (a >> 8) * 59 + 0x6B) & 0xFF
    while v in SKIP:
        v = (v + 0x35) & 0xFF
    if variant == 2:
        first = v
        v = (v + 0x5B) & 0xFF
        while v in SKIP or v == first:
            v = (v + 0x35) & 0xFF
    return v


def probed(a):
    return any(s <= a <= e for s, e in RANGES)


def fill_commands(folder, variant=1):
    """monitor commands that fill the probed RAM with the pattern (files written in folder; absolute paths as VICE sees them)"""
    os.makedirs(folder, exist_ok=True)
    cmds = ["bank ram"]
    for s, e in RANGES:
        p = os.path.abspath(os.path.join(folder, "pattern%d_%04x.bin" % (variant, s)))
        if not os.path.isfile(p) or os.path.getsize(p) != e - s + 1:
            with open(p + ".tmp", "wb") as f:
                f.write(bytes(pattern(a, variant) for a in range(s, e + 1)))
            os.replace(p + ".tmp", p)
        cmds.append('bl "%s" 0 %04x' % (p, s))
    cmds.append("bank cpu")
    return cmds


def dump_commands(path):
    """monitor commands that save the whole RAM (64 KB, RAM view) to path"""
    return ["bank ram", 'bs "%s" 0 0000 ffff' % os.path.abspath(path), "bank cpu"]


def file_sha1(path):
    return hashlib.sha1(open(path, "rb").read()).hexdigest() if path and os.path.isfile(path) else None


def write_meta(path, tag, disk_sha1, variant=1, session=None, seq=None):
    with open(path + ".json", "w") as f:
        json.dump({"tag": tag, "disk_sha1": disk_sha1, "pattern": variant, "session": session, "seq": seq}, f)


def load(folder, disk_sha1=None, newer_than=None):
    """dumps of folder -> list of {tag, file, written: set of addresses, pattern, ram: the 64 KB, session, seq}; with disk_sha1 only the dumps made with that disk.
    A session with no disk in the drive (program loaded through the monitor) has no disk fingerprint: its dump is used if it is
    newer than newer_than (the time of the newest program of the build).
    Returns (dumps, ignored) where ignored counts the dumps of other disks (test variants, older builds).
    Written bytes: the dump of a session with one dump (or the first of a session) is compared with the fill pattern. (1.6)
    Later dumps of the same session (checkpoints, Vice.probe_checkpoint()) are compared with the PREVIOUS dump of the session:
    a byte is written if it differs from it (this includes the bytes that were still the pattern and are not any more). A byte
    rewritten with the same value between two dumps is missed. Sessions are told apart by the "session" of the meta, the order
    is its "seq"; dumps with no session (older versions) are one session each."""
    found, ignored = [], 0
    if not folder or not os.path.isdir(folder):
        return [], ignored
    for n in sorted(os.listdir(folder)):
        if not n.endswith(".bin") or n.startswith("pattern"):
            continue
        p = os.path.join(folder, n)
        meta = json.load(open(p + ".json")) if os.path.isfile(p + ".json") else {}
        ds = meta.get("disk_sha1")
        if disk_sha1 and ds != disk_sha1 and not (ds is None and newer_than is not None and os.path.getmtime(p) >= newer_than):
            ignored += 1
            continue
        ram = open(p, "rb").read()
        if len(ram) != 0x10000:
            ignored += 1
            continue
        found.append((meta.get("session") or n, meta.get("seq") or 1, n, meta, ram))
    sessions = {}
    for f in found:
        sessions.setdefault(f[0], []).append(f)
    out = []
    for sid in sorted(sessions, key=lambda s: sessions[s][0][2]):
        group = sorted(sessions[sid], key=lambda f: (f[1], f[2]))
        prev = None
        for _, seq, n, meta, ram in group:
            v = meta.get("pattern", 1)
            if prev is None:
                w = {a for s, e in RANGES for a in range(s, e + 1) if ram[a] != pattern(a, v)}
            else:                                                     # since the previous dump of the session
                w = {a for s, e in RANGES for a in range(s, e + 1) if ram[a] != prev[a]}
            tag = meta.get("tag") or n[:-4]
            out.append({"tag": tag + ("#%d" % seq if len(group) > 1 else ""), "file": n, "written": w, "pattern": v, "ram": ram,
                        "session": sid, "seq": seq})
            prev = ram
    return out, ignored
