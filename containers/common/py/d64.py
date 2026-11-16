""".d64 disk images (1541, 35 or 40 tracks): directory, block chains, file contents, BAM (15/11). Copyright (c) 2026 - Simone Caporale

The one reader of .d64 files in Lab64 (memory map, release publishing).
    from d64 import read, summary
    disk = read("out/work/disk.d64")     # name, id, tracks, files [{name, type, blocks, chain, data, load/end or fake_load}], owner,
                                         # free_bam, free, total, spt
    summary(disk)                        # {blocks_total, blocks_free, blocks_used, files: [{name, type, blocks}]} (viewer manifest)
Free blocks and the total are counted on the 35 standard tracks without track 18 (directory), as the 1541 does."""

TYPES = ["DEL", "SEQ", "PRG", "USR", "REL"]


def spt(t):
    """sectors of track t"""
    return 21 if t <= 17 else 19 if t <= 24 else 18 if t <= 30 else 17


def petscii(bs):
    """PETSCII name -> text: $41-$5A (upper case on the C64) as lower case, $C1-$DA as upper case; the $A0 padding is dropped"""
    return "".join(chr(c + 32) if 0x41 <= c <= 0x5A else chr(c - 128) if 0xC1 <= c <= 0xDA else chr(c) if 32 <= c < 127 else "?"
                   for c in bytes(bs).rstrip(b"\xa0"))


def read(path):
    img = open(path, "rb").read()
    tracks = 40 if len(img) >= 196608 else 35
    off, o = {}, 0
    for t in range(1, tracks + 1):
        for s in range(spt(t)):
            off[(t, s)] = o
            o += 256
    blk = lambda t, s: img[off[(t, s)]:off[(t, s)] + 256]

    def chain(t, s):
        out, seen = [], set()
        while t and (t, s) in off and (t, s) not in seen:
            seen.add((t, s)); out.append((t, s))
            b = blk(t, s); t, s = b[0], b[1]
        return out

    def data(ch):
        d = b""
        for t, s in ch:
            b = blk(t, s)
            d += b[2:] if b[0] else b[2:b[1] + 1]
        return d

    bam = blk(18, 0)
    files = []
    for t, s in chain(18, 1):
        b = blk(t, s)
        for e in range(8):
            x = b[e * 32:(e + 1) * 32]
            if not x[2] & 7:
                continue
            ch = chain(x[3], x[4])
            body = data(ch)
            f = {"name": petscii(x[5:21]), "type": TYPES[x[2] & 7] if (x[2] & 7) < 5 else "?",
                 "blocks": x[30] + 256 * x[31], "chain": ch, "data": body}
            if f["type"] == "PRG" and len(body) >= 2:
                la = body[0] + 256 * body[1]
                if la >= 0x0200:                               # below $0200 (e.g. $0000): fake address, the program loads it elsewhere
                    f["load"] = la
                    f["end"] = la + len(body) - 2              # excluded
                else:
                    f["fake_load"] = la
            files.append(f)
    owner = {}
    for i, f in enumerate(files):
        for ts in f["chain"]:
            owner[ts] = i
    for ts in chain(18, 0):
        owner.setdefault(ts, "dir")
    free_bam = {(t, s) for t in range(1, 36) for s in range(spt(t)) if bam[4 * t + 1 + s // 8] >> (s % 8) & 1}
    return {"name": petscii(bam[0x90:0xA0]), "id": petscii(bam[0xA2:0xA4]), "tracks": tracks, "spt": spt, "files": files,
            "owner": owner, "free_bam": free_bam, "free": sum(bam[4 * t] for t in range(1, 36) if t != 18),
            "total": sum(spt(t) for t in range(1, 36) if t != 18)}


def summary(disk):
    """the disk statistics of the viewer manifest (stats.disk)"""
    return {"blocks_total": disk["total"], "blocks_free": disk["free"], "blocks_used": disk["total"] - disk["free"],
            "files": [{"name": f["name"], "type": f["type"], "blocks": f["blocks"]} for f in disk["files"]]}
