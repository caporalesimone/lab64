"""PSID files (14/11). Copyright (c) 2026 - Simone Caporale

A .sid file (PSID v2) is a header (0x7C bytes, big endian) + the C64 program (load address in its first two bytes): the player
calls init once (A = subtune - 1) and play once per frame (50 Hz PAL, VBI timing). Players: VICE vsid, sidplayfp, jsSID in the
Lab64 viewer (sid.html), DeepSID, ...

    from psid import write_psid
    write_psid("out/work/sid/song.sid", prg_bytes, init=0x1000, play=0x1003, name="Song", author="Me", released="2026 Me")
prg_bytes: the program with its 2-byte load address. Strings: at most 32 latin-1 characters."""
import struct


def psid(prg, init, play, name="", author="", released="", songs=1, start=1, pal=True, model="6581"):
    load = prg[0] | prg[1] << 8
    assert load >= 0x07E8, "PSID: load address $%04x below $07E8" % load
    s = lambda t: t.encode("latin-1", "replace")[:32].ljust(32, b"\0")
    flags = (0b01 if pal else 0b10) << 2 | {"6581": 0b01, "8580": 0b10, "any": 0b11}[model] << 4
    head = struct.pack(">4sHHHHHHHI32s32s32sHBBBB", b"PSID", 2, 0x7C, 0, init, play, songs, start, 0,
                       s(name), s(author), s(released), flags, 0, 0, 0, 0)
    assert len(head) == 0x7C
    return head + bytes(prg)


def write_psid(path, prg, init, play, **kw):
    data = psid(prg, init, play, **kw)
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def info(data):
    """header of a PSID / RSID file (bytes) as a dict: magic, version, songs, start, name, author, released, flags (v2+), clock
    ("pal" | "ntsc" | "any" | "unknown"), model ("6581" | "8580" | "any" | "unknown"). ValueError when it is not a SID file."""
    if len(data) < 0x76 or data[:4] not in (b"PSID", b"RSID"):
        raise ValueError("not a SID file")
    ver, off, load, init, play, songs, start = struct.unpack(">HHHHHHH", data[4:18])
    if ver < 1 or ver > 4 or songs < 1 or songs > 256:
        raise ValueError("not a valid SID header (version %d, %d songs)" % (ver, songs))
    s = lambda o: data[o:o + 32].split(b"\0")[0].decode("latin-1")
    flags = struct.unpack(">H", data[0x76:0x78])[0] if ver >= 2 and len(data) >= 0x78 else 0
    return {"magic": data[:4].decode(), "version": ver, "songs": songs, "start": start if 1 <= start <= songs else 1,
            "name": s(0x16), "author": s(0x36), "released": s(0x56), "flags": flags,
            "clock": ["unknown", "pal", "ntsc", "any"][(flags >> 2) & 3], "model": ["unknown", "6581", "8580", "any"][(flags >> 4) & 3]}
