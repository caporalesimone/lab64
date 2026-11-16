#!/usr/bin/env python3
"""Memory and disk map of a C64 project, AUTOMATIC and with no configuration (14/11). Copyright (c) 2026 - Simone Caporale

Usage (in the lab64-tools container):  python3 /lab64/containers/tools/memmap/c64map.py [--work out/work] [--disk out/work/disk.d64] [--out DIR]
It reads only what the build already produces:
  - the 64tass listings (*.lst, option -L): for every emitted byte the address in the file, the run address (.logical) and the
    source file; the .virtual reservations (.byte ?, .word ?, .fill n); the addresses used by the instructions;
  - the labels (*.lbl, option -l), to name addresses;
  - the .d64 disk: directory, block chains, load address of every PRG.
A listing is a "module" of the program if its output file (-o) is on the disk (same content) or a disk file has its name
(game -> GAME, menu -> MENU1..3: compressed or split files). The other listings (test variants) are listed apart.
Output: DIR/index.html (RAM and disk) and DIR/memmap.json (the same data for other tools, with "metrics" in the format of the
viewer manifest).
PROGRAMS (1.4): a project whose disk holds programs that replace each other in memory (a loader, an intro, the game, a jukebox)
declares them in lab64.env, one line each: C64_MAP_PROGRAM_<NAME>="main file, then the files it loads" (disk file names, sh
wildcards). Then DIR/index.html is an index (one row per program, all of them side by side, files in no program, the disk) and
every program gets its own map, DIR/program-<name>.html, with only its files; memmap.json gets "schema": 2 and "programs".
Probe dumps go to the program whose main file is in the RAM at the end of the session. Section "programs" below.
(1.6) pages 0-3 map, checked ;@free there, scenario area overlaps, Vice.probe_checkpoint() dumps per program change, C64_MAP_METRICS.
--probe DIR (default out/work/memprobe if it exists): RAM dumps of the run-time probe in VICE (containers/tools/memmap/probe.py); only
the dumps made with the same disk are used. They add the memory really written while the scenarios ran.

Limits (static analysis): data copied or unpacked by the program somewhere else, buffers used only through pointers and tables
read with an index past their first byte are not seen; the area of data that becomes free after start-up stays used.
The run-time probe covers part of it (what the scenarios run). Optional comments in the sources add what no analysis can know:
;@map (description of an area, and "free-after" for data needed only at start-up), ;@scenario (modules in memory together);
pairs of labels NAME / NAME_end name areas by themselves. Syntax: section "annotations" below."""
import argparse, fnmatch, glob, hashlib, html, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.getcwd()                                  # the project (run.sh: /work); Lab64 is HERE/../../..
sys.path[:0] = [HERE, os.path.join(os.path.dirname(HERE), "py"), os.path.join(os.path.dirname(os.path.dirname(HERE)), "common", "py")]
import probe  # noqa: E402  (run-time memory probe in VICE: containers/tools/memmap/probe.py)
import d64 as d64mod  # noqa: E402  (containers/common/py/d64.py)
from lab64env import setting, values  # noqa: E402  (containers/common/py/lab64env.py: the one reader of lab64.env)

# ------------------------------------------------------------------ the C64
SYSTEM = [  # (start, end included, name, note)
    (0x0000, 0x0001, "6510 port", "$00 direction, $01 memory banks"),
    (0x0002, 0x00FF, "zero page", "also used by BASIC and KERNAL when active"),
    (0x0100, 0x01FF, "stack", "6510 stack"),
    (0x0200, 0x03FF, "BASIC and KERNAL", "system buffers and vectors"),
    (0x0400, 0x07FF, "default screen", "$0400-$07E7 text, $07F8-$07FF sprite pointers"),
    (0x0800, 0x9FFF, "RAM", "BASIC programs from $0801"),
    (0xA000, 0xBFFF, "BASIC ROM / RAM", "RAM when $01 switches the ROM off"),
    (0xC000, 0xCFFF, "RAM", "4 KB never used by the system"),
    (0xD000, 0xDFFF, "I/O / RAM", "VIC, SID, color RAM, CIA; RAM when $01 switches the I/O off"),
    (0xE000, 0xFFFF, "KERNAL ROM / RAM", "RAM when $01 switches the ROM off"),
]
BANKS = [  # for the free space: (start, end, name)
    (0x0400, 0x9FFF, "RAM $0400-$9FFF"), (0xA000, 0xBFFF, "under the BASIC ROM"), (0xC000, 0xCFFF, "RAM $C000-$CFFF"),
    (0xD000, 0xDFFF, "under the I/O"), (0xE000, 0xFFFF, "under the KERNAL"),
]
IO = [  # registers: (start, end, name)
    (0xD000, 0xD3FF, "VIC-II"), (0xD400, 0xD7FF, "SID"), (0xD800, 0xDBFF, "color RAM"), (0xDC00, 0xDCFF, "CIA 1"),
    (0xDD00, 0xDDFF, "CIA 2"), (0xDE00, 0xDFFF, "I/O 1-2 (cartridges)"),
]
KERNAL = {0xFF81: "CINT", 0xFF84: "IOINIT", 0xFF87: "RAMTAS", 0xFF8A: "RESTOR", 0xFF8D: "VECTOR", 0xFF90: "SETMSG", 0xFF93: "SECOND",
          0xFF96: "TKSA", 0xFF99: "MEMTOP", 0xFF9C: "MEMBOT", 0xFF9F: "SCNKEY", 0xFFA2: "SETTMO", 0xFFA5: "ACPTR", 0xFFA8: "CIOUT",
          0xFFAB: "UNTLK", 0xFFAE: "UNLSN", 0xFFB1: "LISTEN", 0xFFB4: "TALK", 0xFFB7: "READST", 0xFFBA: "SETLFS", 0xFFBD: "SETNAM",
          0xFFC0: "OPEN", 0xFFC3: "CLOSE", 0xFFC6: "CHKIN", 0xFFC9: "CHKOUT", 0xFFCC: "CLRCHN", 0xFFCF: "CHRIN", 0xFFD2: "CHROUT",
          0xFFD5: "LOAD", 0xFFD8: "SAVE", 0xFFDB: "SETTIM", 0xFFDE: "RDTIM", 0xFFE1: "STOP", 0xFFE4: "GETIN", 0xFFE7: "CLALL",
          0xFFEA: "UDTIM", 0xFFED: "SCREEN", 0xFFF0: "PLOT", 0xFFF3: "IOBASE"}
WRITES = {"sta", "stx", "sty", "inc", "dec", "asl", "lsr", "rol", "ror", "sax", "dcp", "isc", "slo", "sre", "rla", "rra", "shy", "shx"}
BRANCH = {"bcc", "bcs", "beq", "bne", "bmi", "bpl", "bvc", "bvs"}


def h4(a):
    return "$%04X" % a


# ------------------------------------------------------------------ ranges (sorted list of [a, b) )
def ranges_of(addrs):
    """addresses -> contiguous ranges [a, b)"""
    out = []
    for a in sorted(set(addrs)):
        if out and out[-1][1] == a:
            out[-1][1] = a + 1
        else:
            out.append([a, a + 1])
    return [tuple(r) for r in out]


# ------------------------------------------------------------------ 64tass listings
HEXF = re.compile(r"^[0-9a-f]{2}( [0-9a-f]{2})*$")
MNEM = re.compile(r"^[a-z]{3}(\s|$)")


def split_line(line):
    """listing line -> (kind '.'|'>', address, pc or None, bytes, instruction, source) or None.
    Columns are separated by tabs but their width changes from listing to listing (with or without the .logical PC column):
    the PC is the field right after the address, the bytes are in the first fields, the source is the last one."""
    if not line or line[0] not in ".>" or len(line) < 5:
        return None
    f = line.split("\t")
    try:
        off = int(f[0][1:], 16)
    except ValueError:
        return None
    pc, i = None, 1
    if len(f) > 1 and re.fullmatch(r"[0-9a-f]{4}", f[1]):
        pc, i = int(f[1], 16), 2
    hx, mon, src = [], "", ""
    rest = f[i:]
    k = 0
    while k < len(rest) and rest[k] == "" and k < 2:
        k += 1
    if k < len(rest) and k <= 1 and HEXF.match(rest[k]):
        hx = rest[k].split(); k += 1
    nonempty = [(j, x) for j, x in enumerate(rest) if x != "" and j >= k]
    if nonempty and MNEM.match(nonempty[0][1]) and hx and len(nonempty) >= 1 and not nonempty[0][1].startswith(" "):
        mon = nonempty[0][1]; nonempty = nonempty[1:]
    if nonempty:
        src = nonempty[-1][1]
    return line[0], off, pc, hx, mon, src


RESERVE = re.compile(r"^\s*(?:[\w@.+-]+:?\s+)?\.(byte|char|word|addr|rta|long|dword|fill|res)\b\s*(.*)$", re.I)


class Module:
    def __init__(self, lst):
        self.lst = lst
        self.name = os.path.splitext(os.path.basename(lst))[0]
        self.output = None
        self.binary = False
        self.bytes = {}          # run address -> source file
        self.image = {}          # address in the loaded file -> run address (only where they differ: .logical)
        self.loaded = set()      # addresses of the loaded file (image) covered by the listing
        self.virtual = []        # (start, size, name, file)
        self.refs = {}           # address -> set of "r" / "w" / "x" / "i" (indexed) / "p" (pointer)
        self.files = {}          # source file -> emitted bytes
        self.val = {}            # run address -> byte value (as listed: the signature of the module in a RAM dump)
        self.labels = {}
        self.opsyms = set()      # (1.6) symbols used as the operand of an instruction that is not immediate, or in .word / .addr
        self.defined = {}        # (1.6) label -> address, for labels defined on a line of the listing (not NAME = value)
        self.disk = []           # names of the linked disk files
        self.link = ""           # how it was linked to the disk


def parse_lst(path, labels=None):
    """a 64tass listing -> Module; labels (of the .lbl of the same build) give the size of ".fill LABEL" reservations"""
    m = Module(path)
    m.labels = labels or {}
    cur = None
    last = None                  # (file address, run address) after the last line of bytes: for "...repeated..."
    pend = []                    # pending reservations: (address, name, directive, argument, file)
    with open(path, encoding="utf-8", errors="replace") as f:
        for n, line in enumerate(f):
            line = line.rstrip("\n")
            if n < 4 and line.startswith("; 64tass") and " -o " in line:
                o = re.search(r"\s-o\s+(\S+)", line)
                m.output = o.group(1) if o else None
                m.binary = bool(re.search(r"\s(-b|--nostart)\b", line))
                continue
            r = re.match(r"^;\s*\.\.\.repeated \d+ times \((\d+) bytes\)", line)
            if r and last:
                n_ = int(r.group(1))
                emit(m, last[0], last[1], n_, cur)
                last = (last[0] + n_, last[1] + n_)
                continue
            if line.startswith(";******"):
                r = re.search(r"(?:Processing input file|Processing file|Return to file):\s*(.+)$", line)
                if r:
                    cur = r.group(1).strip()
                    m.files.setdefault(cur, 0)            # (1.5) also a source with no bytes of its own (annotations)
                continue
            x = split_line(line)
            if not x:
                continue
            kind, off, pc, hb, mon, src = x
            run = pc if pc is not None else off
            symbols(m, src, mon, run)
            if hb:
                emit(m, off, run, len(hb), cur, hb)
                last = (off + len(hb), run + len(hb))
                refs(m, mon)
            elif kind == ">":
                r = RESERVE.match(src)
                if r:
                    lab = src.split()[0] if not src[:1].isspace() else ""
                    pend.append((run, lab.rstrip(":"), r.group(1).lower(), r.group(2).split(";")[0].strip(), cur))
    # size of the reservations: up to the next one if contiguous, otherwise from the directive
    for i, (a, lab, d, arg, fl) in enumerate(pend):
        size = None
        if i + 1 < len(pend) and 0 < pend[i + 1][0] - a <= 4096 and pend[i + 1][4] == fl:
            size = pend[i + 1][0] - a
        if size is None or size > 1024:
            size = reserve_size(d, arg, m)
        m.virtual.append((a, size, lab, fl))
    return m


DEFLABEL = re.compile(r"([A-Za-z_][\w]*):?(?=\s|$)")
INSTR = re.compile(r"\s*[A-Za-z]{3}\b\s*(.*)$")
ADDRDIR = re.compile(r"\s*\.(?:word|addr)\s+(.*)$", re.I)
SYM = re.compile(r"\(?\s*([A-Za-z_][\w.]*)")


def symbols(m, src, mon, run):
    """(1.6) evidence that a label is an ADDRESS, from the source text of a listing line: the label defined on the line (not a
    NAME = value constant) -> m.defined; the first symbol of the operand of an instruction that is not immediate (lda sym,
    sta (sym),y, inc sym+K: the base symbol) and the symbols of .word / .addr -> m.opsyms. Constants used only in immediates,
    in tables of bytes or in arithmetic leave no trace."""
    body = src.split(";")[0].rstrip()
    if not body:
        return
    d = DEFLABEL.match(body) if not body[:1].isspace() else None
    if d:
        m.defined.setdefault(d.group(1), run)
        body = body[d.end():]
    if mon:                                                   # an instruction
        i = INSTR.match(body)
        op = i.group(1).strip() if i else ""
        if op and not op.startswith("#"):
            s = SYM.match(op)
            if s:
                m.opsyms.add(s.group(1))
        return
    w = ADDRDIR.match(body)
    if w:
        for part in w.group(1).split(","):
            s = SYM.match(part.strip())
            if s:
                m.opsyms.add(s.group(1))


def emit(m, off, run, n, cur, hb=None):
    for i in range(n):
        m.bytes[(run + i) & 0xFFFF] = cur
        if hb:
            m.val[(run + i) & 0xFFFF] = int(hb[i], 16)
        m.loaded.add((off + i) & 0xFFFF)
        if run != off:
            m.image[(off + i) & 0xFFFF] = (run + i) & 0xFFFF
    m.files[cur] = m.files.get(cur, 0) + n


def reserve_size(d, arg, m):
    unit = {"byte": 1, "char": 1, "word": 2, "addr": 2, "rta": 2, "long": 3, "dword": 4}.get(d)
    if unit:
        return unit * max(1, arg.count(",") + 1)
    tok = arg.split(",")[0].strip()
    try:
        return int(tok.replace("$", "0x"), 0) if tok else 1
    except ValueError:
        return m.labels.get(tok, 1)


OPER = re.compile(r"^([a-z]{3})\s+(.*)$")


def refs(m, mon):
    """addresses used by an instruction ('Monitor' column of the listing)"""
    x = OPER.match(mon.strip())
    if not x:
        return
    op, arg = x.groups()
    if arg.startswith("#") or op in BRANCH:
        return
    a = re.search(r"\$([0-9a-f]{2,4})", arg)
    if not a:
        return
    addr = int(a.group(1), 16)
    k = "x" if op in ("jsr", "jmp") else "w" if op in WRITES else "r"
    s = m.refs.setdefault(addr, set())
    s.add(k)
    if arg.startswith("("):
        s.add("p")                                          # zero page pointer (or jmp vector)
        if k != "x":
            m.refs.setdefault((addr + 1) & 0xFFFF, set()).add("p")
    elif "," in arg:
        s.add("i")                                          # indexed: a table that starts here


def parse_lbl(path):
    """labels of a 64tass label file (-l): NAME = $hex, and constants written in decimal (NAME = 14)"""
    d = {}
    for l in open(path, encoding="utf-8", errors="replace"):
        x = re.match(r"\s*([A-Za-z_][\w.]*)\s*=\s*(?:\$([0-9a-fA-F]+)|(\d+))\s*$", l)
        if x:
            d[x.group(1)] = int(x.group(2), 16) if x.group(2) else int(x.group(3))
    return d


# ------------------------------------------------------------------ .d64 disk: containers/common/py/d64.py (the one .d64 reader of Lab64)
def d64(path):
    return d64mod.read(path)


# ------------------------------------------------------------------ analysis
def resolve(p, work):
    """path written in the 64tass command line (relative to the folder it was run from)"""
    if os.path.isabs(p):
        return p
    d = work
    for _ in range(6):
        q = os.path.join(d, p)
        if os.path.isfile(q):
            return q
        d = os.path.dirname(d)
    return os.path.join(os.getcwd(), p)


def analyse(work, disk_path):
    work = os.path.abspath(work)
    mods = []
    for p in sorted(glob.glob(os.path.join(work, "*.lst"))):
        lb = os.path.splitext(p)[0] + ".lbl"
        m = parse_lst(p, parse_lbl(lb) if os.path.isfile(lb) else {})   # labels first: ".fill LABEL" needs them
        m.prg = None
        if m.output and os.path.isfile(resolve(m.output, work)):
            raw = open(resolve(m.output, work), "rb").read()
            m.prg = raw
            if not m.binary and len(raw) > 2:            # PRG bytes the listing does not show: filler (* = ..., .align)
                la = raw[0] + 256 * raw[1]
                m.filler = [a & 0xFFFF for a in range(la, la + len(raw) - 2) if (a & 0xFFFF) not in m.loaded]
        m.filler = getattr(m, "filler", [])
        mods.append(m)
    disk = d64(disk_path) if disk_path and os.path.isfile(disk_path) else None
    if disk:
        byhash = {}
        for f in disk["files"]:
            byhash.setdefault(hashlib.sha1(f["data"]).hexdigest(), []).append(f["name"])
        for m in mods:
            if m.prg:
                for cand in ([m.prg] if m.binary else [m.prg, m.prg[2:]]):
                    hit = byhash.get(hashlib.sha1(cand).hexdigest())
                    if hit:
                        m.disk, m.link = hit, "same content"
                        break
            if not m.disk:                                   # compressed or split files: same name, or name + digits
                stem = m.name.lower()
                for s in (stem, stem[:-1] if stem.endswith("z") else None):
                    if not s:
                        continue
                    hit = [f["name"] for f in disk["files"] if f["name"].lower() == s or re.fullmatch(re.escape(s) + r"[-_]?\d+", f["name"].lower())]
                    if hit:
                        m.disk, m.link = hit, "same name"
                        break
        built = {}
        for p in sorted(glob.glob(os.path.join(work, "**", "*.prg"), recursive=True) + glob.glob(os.path.join(work, "**", "*.bin"), recursive=True)):
            built.setdefault(hashlib.sha1(open(p, "rb").read()).hexdigest(), os.path.relpath(p, work))
        for f in disk["files"]:
            f["built"] = built.get(hashlib.sha1(f["data"]).hexdigest())
            f["modules"] = [m.name for m in mods if f["name"] in m.disk]
    used = [m for m in mods if m.disk] if disk else mods
    other = [m for m in mods if m not in used]
    return used, other, disk


# ------------------------------------------------------------------ memory layers
CODE, RES, REF, IMG, LOAD, FILL, DATA = ("code and data", "reserved variables", "used by the code", "image to be moved", "module file",
                                         "filler", "data file")


def layers(used, disk):
    """address -> {kind: set(who)}; kinds: CODE (emitted bytes, at the run address), RES (.virtual), IMG (image of a .logical
    block: in the file at one place, run elsewhere), FILL (PRG bytes with no source), LOAD / DATA (disk file at its load address:
    of a module, e.g. compressed, or data that stays), REF (address used by an instruction and covered by nothing else)"""
    occ = {}
    put = lambda a, k, who: occ.setdefault(a & 0xFFFF, {}).setdefault(k, set()).add(who)
    for m in used:
        for a in m.bytes:
            put(a, CODE, m.name)
        for a, size, _, _ in m.virtual:
            for i in range(size):
                put(a + i, RES, m.name)
        for a in m.image:
            put(a, IMG, m.name)
        for a in m.filler:
            put(a, FILL, m.name)
    if disk:
        for f in disk["files"]:
            if "load" in f:       # module file (e.g. compressed): its listing counts; the other files are data that stays
                for a in range(f["load"], min(f["end"], 0x10000)):
                    put(a, LOAD if f.get("modules") else DATA, f["name"])
    for m in used:
        for a, k in m.refs.items():
            o = occ.get(a, {})
            if a < 2 or CODE in o or RES in o:
                continue
            if io_name(a) or a in KERNAL:
                continue                                      # system registers and routines, not program RAM
            put(a, REF, m.name)
    return occ


def io_name(a):
    for s, e, n in IO:
        if s <= a <= e:
            return n
    return None


def is_free(o, strict):
    if not o:
        return True
    if CODE in o or RES in o or REF in o or DATA in o:
        return False
    return not strict


def free_ranges(occ, strict=False, minsize=1):
    """free space per bank: strict=False = free from the program (images to be moved, fillers and module files, compressed or to be
    copied, count as free after use); strict=True = never used by anything"""
    out = []
    for s, e, bank in BANKS:
        cur = None
        for a in range(s, e + 2):
            if a <= e and is_free(occ.get(a), strict):
                cur = a if cur is None else cur
            elif cur is not None:
                if a - cur >= minsize:
                    out.append((cur, a, bank))
                cur = None
    return out


def segments(addrs):
    return ranges_of(addrs)


def overlaps(used):
    out = []
    for i, a in enumerate(used):
        sa = set(a.bytes) | {x + k for x, s, _, _ in a.virtual for k in range(s)}
        for b in used[i + 1:]:
            sb = set(b.bytes) | {x + k for x, s, _, _ in b.virtual for k in range(s)}
            both = sa & sb
            if both:
                out.append((a.name, b.name, ranges_of(both)))
    return out


# ------------------------------------------------------------------ annotations, label pairs, scenarios (15/11; 1.5)
# Optional comments in the project sources (read from the source files named by the listings; the listings drop comments).
# No space after ";". START / END = label or $hex, END excluded; "START" alone = up to its pair START_end (suffixes:
# C64_MAP_PAIRS); "START+N" = N bytes (decimal or $hex); in START..END both may be LABEL+N or LABEL-N (1.5).
#   ;@map AREA "text" [free-after=WHEN] [scenario=S1,S2] [layout]
#       an area the program uses that the static analysis may not see (a buffer behind a pointer, data copied there): it counts
#       as used. free-after=WHEN: needed only until WHEN (e.g. "start": data copied elsewhere at start-up), it counts as free in
#       "free after start-up". scenario=...: (1.5) only in those scenarios (the same addresses used differently in turn).
#       layout: (1.5) a table of the fields of the area (the labels inside it, sizes, comments of their source lines).
#   ;@free AREA "text" use=code|code-io-off|data
#       (1.5) free memory and what it can hold: any code and data / code that runs with the I/O switched off (RAM under
#       $D000-$DFFF) / data only (e.g. a VIC bank, RAM under a ROM). Checked: the page says if the area is not free.
#   ;@scenario NAME: ITEM ITEM ...  (; after the colon starts a comment)
#       what is in memory TOGETHER: listing names (modules) and (1.5) disk file names with sh wildcards. Files matched by the
#       same pattern are alternatives (one at a time: twn? = one village; "fmap|boss*" = one group of two patterns).
#       Without file names the scenario has every data file of the program (as in 1.4). Also C64_MAP_SCENARIOS in lab64.env ("name=item,item name2=...").
# Label pairs: every pair LABEL / LABEL_end names an area with no annotation.
ANN = re.compile(r';@(map|free)\s+(\S+?)(?:\.\.(\S+))?\s+"([^"]*)"(.*)$')
SCEN = re.compile(r";@scenario\s+([\w.-]+)\s*:\s*(.+)$")
USES = {"code": "any code and data", "code-io-off": "code that runs with the I/O switched off, or data", "data": "data only"}


def env_setting(name, default=""):
    """a setting of the project: environment, then lab64.env (containers/common/py/lab64env.py)"""
    return setting(name, default, root=ROOT)


def label_lines(m):
    """label -> (source file, line, comment, is a field) of the line that defines it in the sources of module m"""
    out = {}
    for src in m.files:
        path = src if os.path.isabs(src) else os.path.join(ROOT, src)
        if not os.path.isfile(path):
            continue
        for n, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
            r = re.match(r"^([A-Za-z_][\w]*)\b:?(.*)$", line)
            if r and r.group(1) in m.labels and r.group(1) not in out:
                rest = r.group(2)
                c = rest.split(";", 1)[1].strip() if ";" in rest and '"' not in rest.split(";", 1)[0] else ""
                out[r.group(1)] = (src, n, c, bool(RESERVE.match(r.group(1) + rest)))
    return out


def layout_fields(m, a, b, lines):
    """fields of the area a..b of module m: [{name, offset, size, text}] (labels inside it, the first one at each address)"""
    at = {}
    for name, x in m.labels.items():
        if a <= x < b and name in lines:
            k = (not lines[name][3], lines[name][1])          # a field (.byte, .word, .fill...) before a bare label
            if x not in at or k < (not lines[at[x]][3], lines[at[x]][1]):
                at[x] = name
    xs = sorted(at)
    return [{"name": at[x], "offset": x - a, "size": (xs[i + 1] if i + 1 < len(xs) else b) - x, "text": lines[at[x]][2]}
            for i, x in enumerate(xs)]


def annotations(used):
    """(areas, free notes, scenarios, problems) from the ;@map / ;@free / ;@scenario comments of the sources and lab64.env"""
    suffixes = env_setting("C64_MAP_PAIRS", "_end").split()
    areas, notes, scen, bad, seen = [], [], {}, [], set()
    def addr(m, t):
        r = re.fullmatch(r"(\$[0-9a-fA-F]+|[A-Za-z_][\w.]*)([+-])(\$[0-9a-fA-F]+|\d+)", t)   # (1.5) LABEL+N, LABEL-N
        if r:
            b = addr(m, r.group(1))
            k = int(r.group(3)[1:], 16) if r.group(3).startswith("$") else int(r.group(3))
            return None if b is None else b + (k if r.group(2) == "+" else -k)
        if t.startswith("$"):
            return int(t[1:], 16)
        return m.labels.get(t)
    for m in used:
        lines = None
        for src in m.files:
            path = src if os.path.isabs(src) else os.path.join(ROOT, src)
            if (m.name, path) in seen or not os.path.isfile(path):
                continue
            seen.add((m.name, path))
            for n, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
                if "@map" not in line and "@scenario" not in line and "@free" not in line:
                    continue
                r = SCEN.search(line)
                if r:
                    items = r.group(2).split(";")[0]          # a ";" after the colon starts a comment
                    scen.setdefault(r.group(1), []).extend(items.replace(",", " ").split())
                    continue
                r = ANN.search(line)
                if not r:
                    if re.search(r";@(map|free)\b", line):
                        bad.append("%s:%d: @%s not understood" % (src, n, re.search(r";@(map|free)", line).group(1)))
                    continue
                kind, st, en, text, rest = r.groups()
                size = None
                if "+" in st and not en:
                    st, _, k = st.partition("+")
                    size = int(k[1:], 16) if k.startswith("$") else int(k)
                a = addr(m, st)
                b = addr(m, en) if en else (a + size if a is not None and size else
                                            next((m.labels[st + x] for x in suffixes if st + x in m.labels), None))
                if a is None or b is None or b <= a:
                    bad.append("%s:%d: @%s %s: %s" % (src, n, kind, st, "label not found in %s.lbl" % m.name if a is None or b is None else "empty area"))
                    continue
                if kind == "free":
                    u = re.search(r"use=(\S+)", rest)
                    if not u or u.group(1) not in USES:
                        bad.append("%s:%d: @free %s: use=%s" % (src, n, st, "|".join(USES)))
                        continue
                    notes.append({"module": m.name, "file": src, "line": n, "from": a, "to": b, "text": text, "use": u.group(1), "name": st})
                    continue
                fa = re.search(r"free-after=(\S+)", rest)
                sc = re.search(r"scenario=(\S+)", rest)
                x = {"module": m.name, "file": src, "line": n, "from": a, "to": b, "text": text,
                     "free_after": fa.group(1) if fa else None, "name": st,
                     "scenarios": sc.group(1).split(",") if sc else None}
                if re.search(r"(^|\s)layout(\s|$)", rest):
                    lines = lines if lines is not None else label_lines(m)
                    x["fields"] = layout_fields(m, a, b, lines)
                areas.append(x)
    for item in env_setting("C64_MAP_SCENARIOS").split():
        k, _, v = item.partition("=")
        if v:
            scen.setdefault(k, []).extend(v.split(","))
    known = set(scen)
    for x in areas:
        for s_ in x["scenarios"] or []:
            if s_ not in known:
                bad.append("%s:%d: @map %s: scenario=%s is declared nowhere" % (x["file"], x["line"], x["name"], s_))
    return areas, notes, scen, bad


def label_pairs(used, areas):
    """areas named by a pair of labels X / X<suffix> with no annotation: [(module, name, from, to)]"""
    suffixes = env_setting("C64_MAP_PAIRS", "_end").split()
    done = {(a["module"], a["from"], a["to"]) for a in areas}
    out = []
    for m in used:
        for name, a in m.labels.items():
            for x in suffixes:
                b = m.labels.get(name + x)
                if b is not None and 0 < b - a <= 0x8000 and (m.name, a, b) not in done:
                    out.append((m.name, name, a, b))
    return sorted(out, key=lambda t: (t[2], t[0]))


def free_after(occ, areas):
    """free ranges when the areas with free-after are counted as free"""
    gone = {a for ar in areas if ar["free_after"] for a in range(ar["from"], ar["to"])}
    occ2 = {a: o for a, o in occ.items() if a not in gone}
    return free_ranges(occ2)


LOW = 0x0400                   # (1.6) pages 0-3 ($0000-$03FF) have their own map: low_map()
AFTER_START = "area, free after start-up"
LOWUSE = {"variable", "code and data", "used by the code", "annotated area", AFTER_START, "written in VICE", "6510 port"}   # = in use


def free_notes(notes, fr, fr_after, low_static=frozenset(), low_after=frozenset()):
    """the ;@free notes checked against the map: bytes free statically / after start-up, used ranges. Above $0400: the free ranges
    fr / fr_after; (1.6) below: the addresses the program's labels, code and the probe show (low_map: low_static, low_after)"""
    st = {a for x, y, _ in fr for a in range(x, y)}
    af = {a for x, y, _ in fr_after for a in range(x, y)}
    out = []
    for x in notes:
        r = range(x["from"], x["to"])
        used_ = [a for a in r if (a not in af if a >= LOW else a in low_after)]
        out.append(dict(x, to=x["to"], size=len(r), free_static=sum(1 for a in r if (a in st if a >= LOW else a not in low_static)),
                        free_after_start=len(r) - len(used_), used=[[p, q - 1] for p, q in ranges_of(used_)]))
    return out


def low_map(used, areas, pr=None):
    """(1.6) map of pages 0-3 ($0000-$03FF) from what the listings and the probe show: rows (merged ranges), the addresses in use
    and the ones in use after start-up (areas with free-after do not count there). Row = {from, to, what: [...], flags, labels:
    [{name, module, file, line}], modules, probe: {probed, written}}. Known facts: $00/$01 (6510 port) and the stack page. Nothing
    is guessed about the KERNAL / BASIC work areas: only labels the code really uses (an instruction with that address, a
    variable, bytes placed there, a ;@map area) and the bytes written in the probe dumps ($033C-$03FB only: the rest is not probed)."""
    cls, flags, names, mods = {}, {}, {}, {}
    def put(a, c, who=None, fl=""):
        if 0 <= a < LOW:
            cls.setdefault(a, set()).add(c)
            if who:
                mods.setdefault(a, set()).add(who)
            if fl:
                flags.setdefault(a, set()).update(fl)
    def name(a, nm, mod, file=None, line=None):
        if 0 <= a < LOW and nm and not any(x["name"] == nm for x in names.setdefault(a, [])):   # one entry per name (modules share labels)
            names[a].append({"name": nm, "module": mod, "file": file, "line": line})
    for m in used:
        lines = None
        for a in m.bytes:
            put(a, "code and data", m.name)
        for a, size, lab, f in m.virtual:
            for i in range(size):
                put(a + i, "variable", m.name)
            if lab and a < LOW:
                lines = lines if lines is not None else label_lines(m)
                name(a, lab, m.name, *(lines[lab][:2] if lab in lines else (f, None)))
        for a, k in m.refs.items():
            put(a, "used by the code", m.name, "".join(sorted(k - {"i", "p"})) + ("*" if "i" in k else "") + ("p" if "p" in k else ""))
        for nm, v in m.labels.items():                    # (1.6) only a label with evidence that it is an ADDRESS (see symbols())
            if 0 <= v < LOW and (nm in m.opsyms or m.defined.get(nm) == v):
                lines = lines if lines is not None else label_lines(m)
                name(v, nm, m.name, *(lines[nm][:2] if nm in lines else (None, None)))
    for x in areas:
        for a in range(x["from"], min(x["to"], LOW)):
            put(a, AFTER_START if x["free_after"] else "annotated area", x["module"])
        name(x["from"], x["name"] + " (;@map)", x["module"], x["file"], x["line"])
    for a in (0, 1):
        put(a, "6510 port")
    for a in range(0x100, 0x200):
        put(a, "stack")
    run = pr.get("run") if pr else None
    if run:
        for a in run:
            if a < LOW and not (cls.get(a, set()) - {"stack"}):
                put(a, "written in VICE")
    static = {a for a, c in cls.items() if c & LOWUSE}
    after = {a for a in static if cls[a] & (LOWUSE - {AFTER_START})}
    rows, cur = [], None
    for a in sorted(cls):
        key = tuple(sorted(cls[a]))
        if cur and a == cur["to"] + 1 and key == cur["key"] and not names.get(a):
            cur["to"] = a
        else:
            cur = {"from": a, "to": a, "key": key}
            rows.append(cur)
        cur["addrs"] = cur.get("addrs", []) + [a]
    out = []
    for r in rows:
        ad = r.pop("addrs")
        r.pop("key")
        r["what"] = sorted({c for a in ad for c in cls[a]})
        r["flags"] = "".join(sorted({f for a in ad for f in flags.get(a, ())}))
        r["labels"] = [n for a in ad for n in names.get(a, [])]
        r["modules"] = sorted({m for a in ad for m in mods.get(a, ())})
        n_probed = sum(1 for a in ad if probe.probed(a))
        r["probe"] = {"probed": n_probed, "written": sum(1 for a in ad if run and a in run)} if run else None
        out.append(r)
    return out, static, after


def area_overlaps(areas):
    """(1.6) ;@map areas that carry scenario= are checked against each other inside the same scenario: [(scenario, a, b, (from, to))]
    (a, b = the two areas, to excluded). Areas without scenario= (in every scenario, or in none) are not compared, as before."""
    out, by = [], {}
    for x in areas:
        for sc in x.get("scenarios") or []:
            by.setdefault(sc, []).append(x)
    for sc in sorted(by):
        xs = by[sc]
        for i, a in enumerate(xs):
            for b in xs[i + 1:]:
                lo, hi = max(a["from"], b["from"]), min(a["to"], b["to"])
                if lo < hi:
                    out.append((sc, a, b, (lo, hi)))
    return out


def scenario_items(items, used, disk):
    """scenario items -> (modules, {pattern: [files]}, unknown names)"""
    by = {m.name: m for m in used}
    names = [f["name"] for f in disk["files"]] if disk else []
    mods, pats, unknown = [], {}, []
    for x in dict.fromkeys(items):
        if x in by:
            mods.append(by[x])
            continue
        hit = [n for n in names if any(fnmatch.fnmatchcase(n.lower(), q.lower()) for q in x.split("|"))]
        if hit:                                           # "a|b*": one group of alternatives
            pats[x] = hit
        else:
            unknown.append(x)
    return mods, pats, unknown


def scenario_data(scen, used, disk, areas=()):
    """per scenario: modules, files, unknown names, free space with only those in memory, conflicts between them, and the
    lanes of its strip (who is where)"""
    out = []
    for name, items in sorted(scen.items()):
        ms, pats, unknown = scenario_items(items, used, disk)
        mn = {m.name for m in ms}
        if pats and disk:                                # (1.5) the files named, plus the files of its modules
            keep = {f for v in pats.values() for f in v} | {f["name"] for f in disk["files"] if set(f.get("modules", [])) & mn}
            sub = dict(disk, files=[f for f in disk["files"] if f["name"] in keep])
        else:
            sub = disk
        occ = layers(ms, sub)
        sa = [x for x in areas if x["module"] in mn and (not x.get("scenarios") or name in x["scenarios"])]
        for x in sa:
            for ad in range(x["from"], x["to"]):
                occ.setdefault(ad & 0xFFFF, {}).setdefault(RES, set()).add(x["module"])
        fr = free_ranges(occ)
        conf = [{"a": a, "b": b, "ranges": [[x, y - 1] for x, y in rs]} for a, b, rs in overlaps(ms)]
        conf += [{"a": "area " + a["name"], "b": "area " + b["name"], "ranges": [[lo, hi - 1]]}      # (1.6) areas of this scenario
                 for sc_, a, b, (lo, hi) in area_overlaps(areas) if sc_ == name and a["module"] in mn and b["module"] in mn]
        span = lambda f: set(range(f["load"], min(f["end"], 0x10000))) if "load" in f else set()
        fby = {f["name"]: f for f in (sub or {}).get("files", [])}
        groups = [(p, [fby[n] for n in v if n in fby]) for p, v in pats.items()]
        for i, (p, fs) in enumerate(groups):             # files of different patterns, and a file against a module
            sp = set().union(*(span(f) for f in fs)) if fs else set()
            for q, gs in groups[i + 1:]:
                both = sp & set().union(*(span(g) for g in gs)) if gs else set()
                if both:
                    conf.append({"a": p, "b": q, "ranges": [[x, y - 1] for x, y in ranges_of(both)]})
            for m in ms:
                both = sp & (set(m.bytes) | {x + k for x, s_, _, _ in m.virtual for k in range(s_)})
                if both:
                    conf.append({"a": p, "b": m.name, "ranges": [[x, y - 1] for x, y in ranges_of(both)]})
        lanes = [{"kind": "module", "name": m.name, "ranges": [[x, y - 1] for x, y in ranges_of(set(m.bytes) | {
                     (x + k) & 0xFFFF for x, s_, _, _ in m.virtual for k in range(s_)})]} for m in ms]
        for p, fs in groups:
            lanes.append({"kind": "files", "name": p, "files": [f["name"] for f in fs],
                          "ranges": [[x, y - 1] for x, y in ranges_of(set().union(*(span(f) for f in fs)) if fs else set())]})
        for mod in dict.fromkeys(x["module"] for x in sa):   # one lane per module: its annotated areas
            xs = sorted((x for x in sa if x["module"] == mod), key=lambda x: x["from"])
            lanes.append({"kind": "areas", "name": mod + " (;@map)", "ranges": [[x["from"], x["to"] - 1] for x in xs],
                          "texts": ["%s: %s" % (x["name"], x["text"]) for x in xs]})
        out.append({"name": name, "modules": [m.name for m in ms], "files": {p: v for p, v in pats.items()}, "unknown": unknown,
                    "free_bytes": sum(b - a for a, b, _ in fr), "largest_free": max((b - a for a, b, _ in fr), default=0),
                    "free_ranges": [[a, b - 1] for a, b, _ in fr], "conflicts": conf, "lanes": lanes})
    return out


def strip_svg(lanes, free, col):
    """one scenario on a 64 KB axis: a row per lane (module, files, annotated area) and the free space"""
    W, LH, X0 = 1200, 16, 190
    sc = lambda a: X0 + a * (W - X0 - 10) / 65536.0
    out, y = [], 18
    for k in range(17):
        x = sc(k * 4096)
        out.append("<line x1='%.1f' y1='12' x2='%.1f' y2='9999' stroke='currentColor' stroke-opacity='.15'/>" % (x, x))
        if k < 16:
            out.append("<text x='%.1f' y='10' fill='currentColor' fill-opacity='.6'>$%X000</text>" % (x + 2, k))
    rows = []
    for l in lanes:
        n = len(l["ranges"])
        tips = l.get("texts") or [" ".join(l["files"]) if l["kind"] == "files" else l["name"]] * n
        c = KCOL[DATA] if l["kind"] == "files" else col.get(l["name"].split(" ")[0], "#888")
        rows.append((l["name"] + (" (%d)" % len(l["files"]) if l["kind"] == "files" else ""), c, l["ranges"], tips, .45 if l["kind"] == "areas" else 1))
    rows.append(("free", "#4f9d45", free, ["free"] * len(free), 1))
    for label, c, rs, tips, op in rows:
        out.append("<text x='4' y='%d' fill='currentColor'>%s</text>" % (y + 10, E(label[:26])))
        for (a, b), tip in zip(rs, tips):
            out.append("<rect x='%.1f' y='%d' width='%.1f' height='%d' fill='%s' fill-opacity='%.2f'><title>%s</title></rect>" % (
                sc(a), y, max(1.0, sc(b + 1) - sc(a)), LH - 4, c, op, E("%s-%s (%d B) %s" % (h4(a), h4(b), b - a + 1, tip))))
        y += LH
    svg = "".join(out).replace("y2='9999'", "y2='%d'" % y)
    return "<div class='wrap'><svg class='tracks' viewBox='0 0 %d %d' style='min-width:900px'>%s</svg></div>" % (W, y + 4, svg)


def annot_html(ann, col):
    areas, scen, bad, pairs, fr_after, fr = ann["areas"], ann["scenarios"], ann["problems"], ann["pairs"], ann["free_after"], ann["free"]
    notes = ann.get("notes", [])
    P = []
    w = P.append
    if areas or bad:
        w("<section><h2>Annotated areas (;@map in the sources)</h2>")
        if any(a["free_after"] for a in areas):
            w("<div class='kv'><div><b>%d B</b><span>free after start-up (areas with free-after counted as free)</span></div>"
              "<div><b>%d B</b><span>of them in annotated areas</span></div></div>"
              % (sum(b - a for a, b, _ in fr_after), sum(b - a for a, b, _ in fr_after) - sum(b - a for a, b, _ in fr)))
        w("<div class='wrap'><table><tr><th>Area</th><th>Size</th><th>Module</th><th>Description</th><th>Free after</th><th>Scenarios</th><th>Source</th></tr>")
        for a in sorted(areas, key=lambda x: x["from"]):
            w("<tr><td><code>$%04X-$%04X</code> %s</td><td>%d B</td><td><i style='background:%s' class='sw'></i>%s</td><td>%s%s</td><td>%s</td><td>%s</td>"
              "<td><code>%s:%d</code></td></tr>" % (a["from"], a["to"] - 1, E(a["name"]), a["to"] - a["from"], col.get(a["module"], "#888"),
                                                   E(a["module"]), E(a["text"]), (" <a href='#layout-%s'>fields</a>" % E(a["name"], True)) if "fields" in a else "",
                                                   E(a["free_after"] or ""), E(", ".join(a["scenarios"] or [])) or "<span class='dim'>all</span>", E(a["file"]), a["line"]))
        w("</table></div>")
        for b in bad:
            w("<p class='note'><b>Not used:</b> %s</p>" % E(b))
        w("</section>")
    if notes:
        w("<section><h2>Free memory, by use (;@free in the sources)</h2><div class='kv'>")
        for u, txt in USES.items():
            n = sum(x["free_after_start"] for x in notes if x["use"] == u)
            w("<div><b>%d B</b><span>%s (use=%s)</span></div>" % (n, E(txt), E(u)))
        w("</div><div class='wrap'><table><tr><th>Area</th><th>Size</th><th>Use</th><th>Description</th><th>Free now</th><th>Source</th></tr>")
        for x in sorted(notes, key=lambda x: x["from"]):
            ok = not x["used"]
            st = ("free" if x["free_static"] == x["size"] else "free after start-up") if ok else \
                "<b style='color:#c8301e'>used: %s</b>" % E(", ".join("$%04X-$%04X" % (p, q) for p, q in x["used"][:4]))
            w("<tr><td><code>$%04X-$%04X</code> %s</td><td>%d B</td><td>%s</td><td>%s</td><td>%s</td><td><code>%s:%d</code></td></tr>" % (
                x["from"], x["to"] - 1, E(x["name"]), x["size"], E(x["use"]), E(x["text"]), st, E(x["file"]), x["line"]))
        w("</table></div><p class='note'>Declared with <code>;@free AREA \"text\" use=code|code-io-off|data</code>: where new code or "
          "data can go. <b>Free now</b> checks it against this map (static analysis, annotated areas, free-after).</p></section>")
    for a in areas:
        if a.get("fields"):
            w("<section id='layout-%s'><h2>Fields of %s ($%04X-$%04X, %d B)</h2><p class='note'>%s</p><div class='wrap'><table>"
              "<tr><th class='n'>Offset</th><th class='n'>Size</th><th>Field</th><th>Comment in the source</th></tr>" % (
                  E(a["name"], True), E(a["name"]), a["from"], a["to"] - 1, a["to"] - a["from"], E(a["text"])))
            for f in a["fields"]:
                w("<tr><td class='n'>%d</td><td class='n'>%d</td><td><code>%s</code></td><td>%s</td></tr>" % (f["offset"], f["size"], E(f["name"]), E(f["text"])))
            w("</table></div><p class='note'>From <code>;@map ... layout</code>: the labels inside the area, their sizes (up to the next "
              "label) and the comment of the line that defines them.</p></section>")
    if scen:
        w("<section><h2>Scenarios (what is in memory together)</h2><table><tr><th>Scenario</th><th>Modules</th><th>Files</th><th>Free</th>"
          "<th>Largest free block</th><th>Conflicts</th></tr>")
        for sc in scen:
            cf = "; ".join("%s / %s: %s" % (c["a"], c["b"], ", ".join("$%04X-$%04X" % (x, y) for x, y in c["ranges"][:4])
                                            + (" ..." if len(c["ranges"]) > 4 else "")) for c in sc["conflicts"])
            fl = " ".join("%s (%d)" % (p, len(v)) for p, v in sc["files"].items()) or "<span class='dim'>every data file</span>"
            w("<tr><td><a href='#scen-%s'><b>%s</b></a></td><td>%s%s</td><td>%s</td><td>%d B</td><td>%d B</td><td>%s</td></tr>" % (
                E(sc["name"], True), E(sc["name"]), E(" ".join(sc["modules"])),
                (" <span class='note'>(unknown: %s)</span>" % E(" ".join(sc["unknown"]))) if sc["unknown"] else "",
                fl, sc["free_bytes"], sc["largest_free"], E(cf) if cf else "none"))
        w("</table><p class='note'>From <code>;@scenario NAME: items</code> in the sources or <code>C64_MAP_SCENARIOS</code> in lab64.env. "
          "Items = modules (listings) and disk files (wildcards: the files of one pattern are alternatives, one at a time). Free = "
          "$0400-$FFFF with only those in memory (and their annotated areas); a conflict = two items at the same addresses.</p>")
        for sc in scen:
            w("<h3 id='scen-%s'>%s</h3>" % (E(sc["name"], True), E(sc["name"])))
            w(strip_svg(sc["lanes"], sc["free_ranges"], col))
        w("</section>")
    if pairs:
        w("<section><details><summary><h2 style='display:inline'>Areas named by label pairs (%d)</h2></summary><table><tr><th>Area</th>"
          "<th>Size</th><th>Name</th><th>Module</th></tr>" % len(pairs))
        for mod, name, a, b in pairs:
            w("<tr><td><code>$%04X-$%04X</code></td><td>%d B</td><td>%s</td><td>%s</td></tr>" % (a, b - 1, b - a, E(name), E(mod)))
        w("</table><p class='note'>Every pair of labels <code>NAME</code> / <code>NAME%s</code> (suffixes: <code>C64_MAP_PAIRS</code>). "
          "A <code>;@map</code> comment adds a description.</p></details></section>" % E(env_setting("C64_MAP_PAIRS", "_end").split()[0]))
    return "".join(P)


# ------------------------------------------------------------------ run-time probe (VICE)
def probe_dumps(folder, disk_path, work=None):
    """(dumps, ignored): the dumps of the probe made with this disk (or, with no disk in the drive, after the newest program of
    the build)"""
    prgs = glob.glob(os.path.join(work, "*.prg")) if work else []
    return probe.load(folder, probe.file_sha1(disk_path) if disk_path else None,
                      max(os.path.getmtime(p) for p in prgs) if prgs else None)


def probe_summary(dumps, ignored):
    """dumps -> dict for the page (or None): written / never written addresses, sessions"""
    if not dumps:
        return {"dumps": 0, "ignored": ignored} if ignored else None
    run = set().union(*(d["written"] for d in dumps))
    never = [a for a in range(0x0400, 0x10000) if probe.probed(a) and a not in run]
    return {"dumps": len(dumps), "ignored": ignored, "run": run, "never": never, "patterns": sorted({d["pattern"] for d in dumps}),
            "scenarios": sorted(((d["tag"], len(d["written"])) for d in dumps), key=lambda x: x[0])}


def probe_data(folder, disk_path, work=None):
    """dumps of the probe made with this disk -> dict for the page, or None"""
    return probe_summary(*probe_dumps(folder, disk_path, work))


def bank_of(a):
    for s, e, bank in BANKS:
        if s <= a <= e:
            return bank
    return None


def probe_ranges(addrs):
    """addresses -> [(a, b, bank)] split at the bank borders (bank None below $0400)"""
    cuts = sorted({x for s, e, _ in BANKS for x in (s, e + 1)})
    out = []
    for a, b in ranges_of(addrs):
        pts = [a] + [c for c in cuts if a < c < b] + [b]
        out += [(x, y, bank_of(x)) for x, y in zip(pts, pts[1:])]
    return out


def probe_html(pr, occ):
    P = []
    w = P.append
    w("<section><h2>Measured in VICE (run-time probe)</h2>")
    if not pr.get("run"):
        w("<p class='note' style='margin-top:0'>%d RAM dumps found, none made with this disk (test variants or an older build): "
          "run the probe again (the project tests with <code>C64_MEMPROBE=1</code>).</p></section>" % pr["ignored"])
        return "".join(P)
    nv = probe_ranges(pr["never"])
    w("<div class='kv'><div><b>%d B</b><span>RAM never written while running ($033C-$03FB, $0400-$07FF, $0803-$FFFF)</span></div>" % len(pr["never"]))
    for s, e, bank in BANKS:
        w("<div><b>%d B</b><span>never written: %s</span></div>" % (sum(b - a for a, b, k in nv if k == bank), E(bank)))
    w("<div><b>%d</b><span>VICE sessions (dumps)%s</span></div>" % (pr["dumps"], (", %d of other disks ignored" % pr["ignored"]) if pr["ignored"] else ""))
    w("<div><b>%s</b><span>fill patterns used (two = second pass done: no false \"never written\" bytes left)</span></div></div>"
      % " + ".join(str(x) for x in pr.get("patterns", [1])))
    w("<p class='note'>Right after the boot the RAM is filled with a known pattern, the scenarios run, then the RAM is saved: a byte "
      "still equal to the pattern was <b>never written</b>. This is the real use while running (data copied or unpacked, buffers, "
      "screen) that the static analysis cannot see, but only for what the scenarios run (the tests of the project).</p>")
    # page grid: share of every page written at run time
    w("<div class='pages' style='margin-top:10px'><div></div>" + "".join("<div class='h'>%X</div>" % c for c in range(16)))
    run = pr["run"]
    for r in range(16):
        w("<div class='rh'>$%X000</div>" % r)
        for c in range(16):
            pg = r * 16 + c
            pa = [a for a in range(pg * 256, pg * 256 + 256) if probe.probed(a)]
            if not pa:
                w("<div class='pg sys' title='$%02X00-$%02XFF  not probed' style='background:transparent'></div>" % (pg, pg)); continue
            n = sum(1 for a in pa if a in run)
            st = sum(1 for a in pa if a not in run and is_free(occ.get(a), False))
            tip = "$%02X00-$%02XFF  %s\nwritten at run time: %d of %d B\nnever written: %d B (%d of them free also for the static analysis)" % (
                pg, pg, sys_name(pg * 256), n, len(pa), len(pa) - n, st)
            w("<div class='pg' title='%s'><i style='flex:%d;background:#8a1c14'></i><i style='flex:%d;background:#4f9d4566'></i></div>" % (
                E(tip, True), n, len(pa) - n))
    w("</div><div class='legend' style='margin-top:6px'><span><i style='background:#8a1c14'></i>written at run time</span>"
      "<span><i style='background:#4f9d4566'></i>never written</span></div>")
    # never written stretches, compared with the static view
    w("<h3>Never written while running</h3><div class='wrap'><table><tr><th>From</th><th>To</th><th class='n'>Bytes</th><th>Bank</th>"
      "<th>Static analysis</th></tr>")
    small = 0
    for a, b, bank in nv:
        if b - a < 16:
            small += b - a; continue
        used = sorted(cover(occ, a, b))
        nfree = sum(1 for x in range(a, b) if is_free(occ.get(x), False))
        st = "free" if nfree == b - a else ("used by: " + ", ".join(used)) if not nfree else "%d B free; used by: %s" % (nfree, ", ".join(used))
        w("<tr><td class='mono'>%s</td><td class='mono'>%s</td><td class='n'>%d</td><td>%s</td><td>%s</td></tr>" % (h4(a), h4(b - 1), b - a, E(bank or ""), E(st)))
    w("</table></div><p class='note'>Stretches of at least 16 bytes; %d more bytes in shorter stretches. \"Used by\" on a never written "
      "stretch = the program declares or loads something there that the scenarios never wrote (code not loaded in the tests, variables "
      "never set, reservations larger than needed): candidates to check, not free memory for sure.</p>" % small)
    # written but statically free
    hid = [a for a in pr["run"] if 0x0400 <= a and is_free(occ.get(a), True)]
    hr = [(a, b) for a, b in ranges_of(hid) if b - a >= 16]
    w("<details><summary>Written at run time where the static analysis sees nothing (%d B)</summary><p class='note'>Buffers behind "
      "pointers, unpacked or copied data, screen and sprite areas, memory cleared at start-up, the test shortcuts.</p>"
      "<div class='wrap'><table><tr><th>From</th><th>To</th><th class='n'>Bytes</th><th>Bank</th></tr>" % len(hid))
    for a, b in hr:
        w("<tr><td class='mono'>%s</td><td class='mono'>%s</td><td class='n'>%d</td><td>%s</td></tr>" % (h4(a), h4(b - 1), b - a, E(bank_of(a) or "")))
    w("</table></div></details>")
    w("<details><summary>Scenarios (%d)</summary><div class='wrap'><table><tr><th>Scenario</th><th class='n'>Bytes written</th></tr>" % len(pr["scenarios"]))
    for t, n in pr["scenarios"]:
        w("<tr><td class='mono'>%s</td><td class='n'>%d</td></tr>" % (E(t), n))
    w("</table></div></details></section>")
    return "".join(P)


# ------------------------------------------------------------------ programs (15/11, Lab64 1.4)
# A PROGRAM is a set of disk files that can be in memory at the same time: the program that runs (its MAIN file, the first one
# declared) and what it loads (overlays, data, saves). Programs replace each other in memory, so each one gets its own map.
# Declared in lab64.env, one line per program (file order = order of the index):
#   C64_MAP_PROGRAM_<NAME>="main file  file  pattern ..."      e.g. C64_MAP_PROGRAM_GAME="game lobby menu? snd* save-*"
# Names are disk file names (without a disk: listing names), case-insensitive, with sh wildcards * ? [..]; the first one is the
# main file (a plain name). A file may be in several programs (data or a module that two programs load). A module (listing) is
# in a program when one of its disk files is. No declaration = one map of everything, as before 1.4.
PROGVAR = re.compile(r"^C64_MAP_PROGRAM_([A-Za-z0-9_]+)$")
MATCH = 0.6                    # share of the main file's bytes found in a RAM dump to say that the dump ended in that program


def declared_programs():
    """[(name, [patterns])]: C64_MAP_PROGRAM_<NAME> of lab64.env (in file order), the environment wins (and may add some)"""
    d = {}
    for k, v in list(values(ROOT).items()) + [(k, v) for k, v in os.environ.items() if v.strip()]:
        r = PROGVAR.match(k)
        if r:
            d[r.group(1).lower()] = v.split()
    return [(k, v) for k, v in d.items() if v]


def resolve_programs(decl, used, disk):
    """declared programs -> ([{name, main, files, modules, patterns}], unassigned file names, warnings); errors stop the map"""
    names = [f["name"] for f in disk["files"]] if disk else [m.name for m in used]
    progs, warns = [], []
    for name, pats in decl:
        files = []
        for i, p in enumerate(pats):
            hit = [n for n in names if fnmatch.fnmatchcase(n.lower(), p.lower())]
            if i == 0 and (any(c in p for c in "*?[") or not hit):
                sys.exit("c64map: C64_MAP_PROGRAM_%s: the first name is the main file of the program: a plain %s name, found %s" % (
                    name.upper(), "disk file" if disk else "listing", "a pattern" if hit else "nothing called '%s'" % p))
            if not hit:
                warns.append("C64_MAP_PROGRAM_%s: '%s' matches no %s" % (name.upper(), p, "disk file" if disk else "listing"))
            files += [n for n in hit if n not in files]
        mods = [m for m in used if set(m.disk if disk else [m.name]) & set(files)]
        progs.append({"name": name, "patterns": pats, "main": files[0], "files": files, "modules": mods})
    claimed = {f for p in progs for f in p["files"]}
    unassigned = [n for n in names if n not in claimed]
    if unassigned:
        warns.append("%d %s in no program: %s" % (len(unassigned), "disk files" if disk else "listings", " ".join(unassigned)))
    return progs, unassigned, warns


def metric_programs(progs, warns):
    """(1.6) the programs that publish metrics: C64_MAP_METRICS="game start" (program names, as in C64_MAP_PROGRAM_<NAME>, any
    case); empty or unset = every program, as before. A name that is no declared program is a warning."""
    want = [x.lower() for x in env_setting("C64_MAP_METRICS").replace(",", " ").split()]
    if not want:
        return progs
    names = {p["name"] for p in progs}
    for x in want:
        if x not in names:
            warns.append("C64_MAP_METRICS: '%s' is no declared program (%s)" % (x, " ".join(sorted(names))))
    return [p for p in progs if p["name"] in want]


def signatures(prog, used, disk):
    """[address -> byte] of the main file as it is in memory: one per module of the main file (its listing, run addresses: a
    file unpacked by a module of its own counts with either), else the file at its load address"""
    sigs = [dict(m.val) for m in prog["modules"] if m.val and prog["main"] in (m.disk if disk else [m.name])]
    if not sigs and disk:
        f = next(f for f in disk["files"] if f["name"] == prog["main"])
        if "load" in f:
            sigs = [{f["load"] + i: b for i, b in enumerate(f["data"][2:]) if f["load"] + i < 0x10000}]
    return sigs


def share(ram, sigs):
    """best share of the bytes of one signature found in a 64 KB RAM image"""
    return max([sum(1 for a, b in sg.items() if ram[a] == b) / float(len(sg)) for sg in sigs if sg] or [0.0])


def assign_dumps(dumps, progs, used, disk):
    """dump -> program whose main file is in the RAM at the end of the session (best share of its bytes, at least MATCH).
    Returns ({program name: [dumps]}, [(dump, best name, best share)] not assigned)"""
    sigs = {p["name"]: signatures(p, used, disk) for p in progs}
    out, left = {p["name"]: [] for p in progs}, []
    for d in dumps:
        sc = sorted(((share(d["ram"], sg), n) for n, sg in sigs.items() if sg), reverse=True)
        if sc and sc[0][0] >= MATCH:
            out[sc[0][1]].append(d)
            d["share"] = sc[0][0]
        else:
            left.append((d, sc[0][1] if sc else "", sc[0][0] if sc else 0.0))
    return out, left


# ------------------------------------------------------------------ HTML page
E = html.escape
PALETTE = ["#c8301e", "#8e5bb0", "#e8762b", "#1f8a8a", "#c2477e", "#b8860b", "#7a4a2a", "#5d8a2f", "#d4622a", "#6a4c93", "#2f9e8f",
           "#a0522d", "#9a3b5f", "#8a7a20", "#4a6a50", "#b5653f"]          # no blue (data files) and no light green (free)
KCOL = {CODE: "#8a1c14", RES: "#e8762b", REF: "#f2c230", DATA: "#2f6db5", IMG: "#7fa7d9", FILL: "#c9b98f", LOAD: "#b9cce6"}
CSS = """
.sw{display:inline-block;width:10px;height:10px;margin-right:5px;vertical-align:baseline}
:root{--paper:#f3ead3;--card:#fbf6e9;--ink:#2a2118;--ink2:#6a5a40;--rule:#d6c8a2;--red:#8a1c14;--night:#14121c;--key:#fffaf0;
--mono:"DejaVu Sans Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
@media (prefers-color-scheme:dark){:root{--paper:#18140f;--card:#221c15;--ink:#efe4c8;--ink2:#b3a37f;--rule:#3b3125;--red:#e2735c;--key:#2e261d}}
*{box-sizing:border-box}html,body{background:var(--paper)}body{margin:0;color:var(--ink);font:14.5px/1.5 var(--sans)}
.top{background:var(--night);color:#f0e6c8;position:relative;overflow:hidden}.top .in{max-width:1240px;margin:0 auto;padding:20px 330px 18px 16px}
.top h1{margin:0;font:700 22px var(--mono);letter-spacing:.04em}.top .proj{font:600 12.5px var(--mono);letter-spacing:.18em;text-transform:uppercase;color:#d9c99e}
.top .sub{font:12.5px var(--mono);color:#c9bd9c;margin-top:6px}
.rainbow{position:absolute;right:-40px;top:0;bottom:0;width:300px;display:flex;transform:skewX(-28deg)}.rainbow i{flex:1}
.stripes{height:12px;display:grid;grid-template-rows:repeat(5,1fr)}
.r1{background:#c8301e}.r2{background:#e8762b}.r3{background:#f2c230}.r4{background:#4f9d45}.r5{background:#2f6db5}
@media (max-width:760px){.top .in{padding-right:16px}.rainbow{width:150px;opacity:.5}}
main{max-width:1240px;margin:0 auto;padding:20px 16px 60px}
section{background:var(--card);border:1px solid var(--rule);border-top:3px solid var(--red);padding:14px 16px 16px;margin:0 0 16px;min-width:0}
h2{display:inline-block;font:600 12.5px var(--mono);letter-spacing:.08em;text-transform:uppercase;background:var(--ink);color:var(--paper);padding:2px 8px;margin:0 0 12px}
h3{font:700 17px var(--mono);margin:14px 0 6px;color:var(--red)}
.kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px 18px;margin:4px 0 6px}
.kv div{border-left:3px solid var(--rule);padding-left:9px}.kv b{display:block;font:700 18px var(--mono)}.kv span{font-size:12.5px;color:var(--ink2)}
table{width:100%;border-collapse:collapse;font-size:13px}th{background:var(--ink);color:var(--paper);text-align:left;padding:4px 8px;font:600 11.5px var(--mono)}
td{border-bottom:1px solid var(--rule);padding:4px 8px;vertical-align:top}td.n,th.n{text-align:right;font-family:var(--mono);white-space:nowrap}
.mono{font-family:var(--mono);font-size:12.5px}.dim{color:var(--ink2)}.note{font-size:13px;color:var(--ink2);margin:8px 0 0}
.wrap{overflow-x:auto}details{margin-top:8px}summary{cursor:pointer;color:var(--red);font:600 13px var(--mono)}
.tag{font:600 11px var(--mono);padding:0 6px;border:1.5px solid currentColor;border-radius:5px;box-shadow:0 2px 0 currentColor;background:var(--key);white-space:nowrap}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:12.5px;margin:6px 0 10px}.legend i{display:inline-block;width:14px;height:10px;margin-right:5px;vertical-align:-1px;border:1px solid rgba(0,0,0,.25)}
.pages{display:grid;grid-template-columns:44px repeat(16,minmax(0,1fr));gap:2px;font:11px var(--mono)}
.pages .h{color:var(--ink2);text-align:center;align-self:end}.pages .rh{color:var(--ink2);text-align:right;padding-right:4px;align-self:center}
.pg{height:30px;display:flex;flex-direction:column;border:1px solid var(--rule);background:#3a8f3a22;cursor:default}.pg i{display:block}
.pg.sys{outline:1px dashed var(--ink2);outline-offset:-3px}
svg.tracks{width:100%;height:auto;display:block;font:11px var(--mono)}
.grid{display:grid;gap:1px;font:9px var(--mono)}.grid .s{height:13px;border:1px solid rgba(0,0,0,.08)}
"""


def low_html(rows, pr):
    """(1.6) section "Pages 0-3": the merged ranges of $0000-$03FF that the listings, the annotations and the probe show"""
    run = bool(pr and pr.get("run"))
    P = []
    w = P.append
    w("<section id='low'><h2>Pages 0-3 ($0000-$03FF)</h2>")
    used_n = sum(r["to"] - r["from"] + 1 for r in rows if set(r["what"]) & LOWUSE)
    w("<div class='kv'><div><b>%d B</b><span>of $0000-$03FF in use by this map's program (labels, code, annotations%s)</span></div>"
      "<div><b>%d</b><span>ranges listed</span></div></div>" % (used_n, ", probe" if run else "", len(rows)))
    w("<div class='wrap'><table><tr><th>Range</th><th class='n'>Bytes</th><th>What</th><th>Labels (source)</th><th>Module</th>%s</tr>" % (
        "<th>VICE probe</th>" if run else ""))
    for r in rows:
        n = r["to"] - r["from"] + 1
        rng = ("$%04X-$%04X" % (r["from"], r["to"])) if n > 1 else "$%04X" % r["from"]
        what = ", ".join(r["what"]) + (" (%s)" % r["flags"] if r["flags"] else "")
        labs = "; ".join("<code>%s</code>%s" % (E(x["name"]), (" <span class='dim'>%s:%d</span>" % (E(x["file"]), x["line"])) if x.get("file") and x.get("line") else
                         (" <span class='dim'>%s</span>" % E(x["file"])) if x.get("file") else "") for x in r["labels"][:8]) + (" ..." if len(r["labels"]) > 8 else "")
        pb = ""
        if run:
            p = r["probe"]
            pb = "<td>%s</td>" % ("not probed" if not p["probed"] else "never written" if not p["written"] else
                                  "written (%d of %d B)" % (p["written"], p["probed"]) if p["written"] < p["probed"] else "written")
        w("<tr><td class='mono'>%s</td><td class='n'>%d</td><td>%s</td><td>%s</td><td>%s</td>%s</tr>" % (
            rng, n, E(what), labs, E(", ".join(r["modules"])), pb))
    w("</table></div><p class='note'>Only what the listings and the annotations show: labels whose value is an address the code uses "
      "(an instruction operand, a variable, bytes placed there, a <code>;@map</code> area), and the facts $00/$01 (6510 port) and the "
      "stack page. The KERNAL and BASIC work areas are <b>not</b> listed unless the program uses them: an unlisted byte is unknown, "
      "not free. A name is listed only if it is defined there or used as the operand of a non-immediate instruction (or .word / .addr): constants used in immediates are not. "
      "<code>(r w x)</code> = read, written, jumped to; <code>p</code> = zero page pointer, <code>*</code> = indexed. %s "
      "<code>;@free</code> notes in this range are checked against it (the stack page is not).</p></section>" % (
          "VICE probe: only $033C-$03FB is probed (the rest of the pages is used by BASIC and the KERNAL at READY.); the test shortcuts "
          "(monitor writes) count as written." if run else "Run the tests with <code>C64_MEMPROBE=1</code> to add what was written in VICE."))
    return "".join(P)


def page_html(used, other, disk, occ, title, pr=None, ann=None, prog=None):
    """the map page; prog (a declared program) = the page of that program: its files only, a link back to the index, no disk"""
    P = []
    w = P.append
    col = {m.name: PALETTE[i % len(PALETTE)] for i, m in enumerate(used)}
    fr = free_ranges(occ)
    frs = free_ranges(occ, strict=True)
    tot = lambda rs: sum(b - a for a, b, _ in rs)
    w("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>%s</title><style>%s</style></head><body>" % (E((title + " · " if title else "") + "Memory map" + (" · " + prog["name"] if prog else "")), CSS))
    w("<div class='top'><div class='rainbow'><i class='r1'></i><i class='r2'></i><i class='r3'></i><i class='r4'></i><i class='r5'></i></div>"
      "<div class='in'><div class='proj'>%s</div><h1>MEMORY MAP%s</h1><div class='sub'>%sgenerated automatically from 64tass listings, "
      "labels and disk (containers/tools/memmap/c64map.py)</div></div></div><div class='stripes'><i class='r1'></i><i class='r2'></i>"
      "<i class='r3'></i><i class='r4'></i><i class='r5'></i></div><main>" % (
          E(title or "C64 project"), (": " + E(prog["name"].upper())) if prog else "",
          ("program %s (main file %s) · <a href='index.html' style='color:#f2c230'>all the programs</a> · " % (
              E(prog["name"]), E(prog["main"]))) if prog else ""))

    # --- summary
    w("<section><h2>Summary</h2><div class='kv'>")
    w("<div><b>%d B</b><span>RAM free from the program ($0400-$FFFF)</span></div>" % tot(fr))
    for s, e, bank in BANKS:
        w("<div><b>%d B</b><span>%s</span></div>" % (sum(b - a for a, b, k in fr if k == bank), E(bank)))
    w("<div><b>%d B</b><span>never used (not even by images, fillers, loaded files)</span></div>" % tot(frs))
    w("<div><b>%d</b><span>modules (listings linked to the disk)</span></div>" % len(used))
    if prog:
        w("<div><b>%d</b><span>disk files of the program: %s</span></div>" % (len(prog["files"]), E(" ".join(prog["files"]))))
    elif disk:
        w("<div><b>%d / %d</b><span>free blocks on the disk</span></div>" % (disk["free"], disk["total"]))
    w("</div><p class='note'><b>Free from the program</b> = no module has code, data, a reserved variable or an address used by an "
      "instruction there, and no data file of the disk is loaded there. Images to be moved (of <code>.logical</code> blocks), PRG fillers "
      "and module files (e.g. compressed, then unpacked elsewhere) count as free after use: <b>never used</b> excludes them too. Modules "
      "loaded in turn (overlays) are added up: every module card also gives the free space with only that module in memory. Static "
      "analysis: the limits are at the bottom of the page.</p></section>")

    if ann:
        w(annot_html(ann, col))

    # --- overview by pages: who uses every page (modules loaded in turn are shown side by side)
    w("<section><h2>Overview (256-byte pages)</h2><div class='legend'>")
    for m in used:
        w("<span><i style='background:%s'></i>%s</span>" % (col[m.name], E(m.name)))
    w("<span><i style='background:%s'></i>data files</span><span><i style='background:%s'></i>only images, fillers, module files</span>"
      "<span><i style='background:#4f9d4566'></i>free</span></div>" % (KCOL[DATA], KCOL[LOAD]))
    w("<div class='pages'><div></div>" + "".join("<div class='h'>%X</div>" % c for c in range(16)))
    for r in range(16):
        w("<div class='rh'>$%X000</div>" % r)
        for c in range(16):
            pg = r * 16 + c
            share, free, data, trans = {}, 0, 0, 0
            for a in range(pg * 256, pg * 256 + 256):
                o = occ.get(a, {})
                who = set()
                for k in (CODE, RES, REF):
                    who |= o.get(k, set())
                if who:
                    for x in who:
                        share[x] = share.get(x, 0) + 1.0 / len(who)
                elif DATA in o:
                    data += 1
                elif o:
                    trans += 1
                else:
                    free += 1
            tip = "$%02X00-$%02XFF  %s" % (pg, pg, sys_name(pg * 256)) + "".join("\n%s: %d B" % (x, round(v)) for x, v in sorted(share.items(), key=lambda kv: -kv[1])) + \
                  ("\ndata files: %d B" % data if data else "") + ("\nimages/fillers/module files: %d B" % trans if trans else "") + ("\nfree: %d B" % free if free else "")
            bars = "".join("<i style='flex:%.2f;background:%s'></i>" % (v, col[x]) for x, v in sorted(share.items()))
            bars += ("<i style='flex:%d;background:%s'></i>" % (data, KCOL[DATA]) if data else "") + ("<i style='flex:%d;background:%s'></i>" % (trans, KCOL[LOAD]) if trans else "")
            bars += "<i style='flex:%d;background:#4f9d4566'></i>" % free if free else ""
            w("<div class='pg%s' title='%s'>%s</div>" % (" sys" if pg < 4 else "", E(tip, True), bars))
    w("</div><p class='note'>Every cell is a page; the bars are proportional to the bytes of every module (code, data, variables, used "
      "addresses). Several colors in one page = modules that use it in turn. Hover a cell for the details. Dashed border: pages 0-3, of the system (section Pages 0-3 below).</p></section>")

    if ann and ann.get("low") is not None:
        w(low_html(ann["low"], pr))

    # --- layers
    w("<section><h2>Layers by module</h2>")
    w(tracks(used, disk, occ, col))
    w("<p class='note'>Horizontal axis: address from $0000 to $FFFF. One row per module (code and data at the run address, reserved "
      "variables, images to be moved), then the disk files at their load address and the space free from the program. Hover a stretch "
      "for the details.</p></section>")

    # --- free space
    w("<section><h2>Space free from the program</h2><div class='wrap'><table><tr><th>From</th><th>To</th><th class='n'>Bytes</th><th>Bank</th>"
      "<th>Never used?</th></tr>")
    strict = {a for x, y, _ in frs for a in range(x, y)}
    for a, b, bank in sorted(fr):
        if b - a < 16:
            continue
        n_s = sum(1 for x in range(a, b) if x in strict)
        w("<tr><td class='mono'>%s</td><td class='mono'>%s</td><td class='n'>%d</td><td>%s</td><td class='mono'>%s</td></tr>" % (
            h4(a), h4(b - 1), b - a, E(bank), "yes" if n_s == b - a else "%d B of %d" % (n_s, b - a) if n_s else "no: " + E(", ".join(sorted(cover(occ, a, b))))))
    small = sum(b - a for a, b, _ in fr if b - a < 16)
    w("</table></div>" "<p class='note'>Stretches of at least 16 bytes; %d more free bytes in shorter stretches.</p></section>" % small)

    # --- run-time probe
    if pr:
        w(probe_html(pr, occ))

    # --- overlaps
    ov = overlaps(used)
    if ov:
        w("<section><h2>Modules in the same memory</h2><p class='note' style='margin-top:0'>Two modules that use the same addresses "
          "cannot be in memory together: normal for modules loaded in turn (overlays); otherwise it is a bug.</p>"
          "<details><summary>%d pairs of modules</summary><div class='wrap'><table><tr><th>Module</th><th>Module</th><th class='n'>Shared bytes</th><th>Areas</th></tr>" % len(ov))
        for a, b, rs in ov:
            w("<tr><td>%s</td><td>%s</td><td class='n'>%d</td><td class='mono'>%s</td></tr>" % (E(a), E(b), sum(y - x for x, y in rs),
              E(", ".join("%s-%s" % (h4(x), h4(y - 1)) for x, y in rs[:6]) + (" ..." if len(rs) > 6 else ""))))
        w("</table></div></details></section>")

    # --- modules
    w("<section><h2>Modules</h2>")
    for m in used:
        w(module_html(m, col[m.name], occ))
    if not used:
        w("<p class='note' style='margin-top:0'>No 64tass listing belongs to this program: only the load addresses of its files "
          "are known (assemble the main file with <code>-L</code> to see its code, data and variables).</p>")
    if other and not prog:
        w("<h3>Other listings</h3><p class='note' style='margin-top:0'>Listings whose file is not on the disk (e.g. test variants): "
          "not counted in the free space. %s</p>" % E(", ".join("%s (%d B)" % (m.name, len(m.bytes)) for m in other)))
    w("</section>")

    # --- disk
    if disk and not prog:
        w(disk_html(disk, used, col))

    others = other_pages() if not prog else []
    if others:
        w("<section><h2>Other pages</h2><p class='note' style='margin-top:0'>In the same folder (written by other tools of the project): %s</p></section>" % ", ".join(
            "<a href='%s'>%s</a>" % (E(x, True), E(x)) for x in others))
    w("<section><h2>Limits</h2><ul class='note' style='margin:0;padding-left:18px'>"
      "<li>This is a <b>static</b> analysis: it sees what the assembler writes, not what the program does while it runs.</li>"
      "<li>Data copied or unpacked elsewhere (e.g. a compressed file) is seen only at its load address.</li>"
      "<li>Data that becomes useless after start-up (e.g. copied elsewhere at start-up) stays used.</li>"
      "<li>Buffers used only through pointers, and tables read with an index past their first byte, are not seen; the screen, unless "
      "it is declared with a reservation, is seen only through the addresses used directly.</li>"
      "<li>An address between $D000 and $DFFF used by the code counts as an I/O register, unless it is inside code or variables of the program.</li>"
      "<li>Run-time probe (if present): it sees only what the scenarios run; the test shortcuts (memory written by the monitor) count "
      "as written; a byte written with the same value as the pattern looks untouched (about 1 in 250 for data that is not $00, $FF, $20).</li>"
      "</ul></section></main></body></html>")
    return "\n".join(P)


def legend():
    items = [(KCOL[CODE], CODE), (KCOL[RES], RES), (KCOL[REF], REF), (KCOL[DATA], DATA + " (at its load address)"),
             (KCOL[IMG], "image to be moved (.logical)"), (KCOL[FILL], "PRG " + FILL), (KCOL[LOAD], LOAD + " (e.g. compressed)"), ("#4f9d4566", "free")]
    return "<div class='legend'>" + "".join("<span><i style='background:%s'></i>%s</span>" % (c, E(t)) for c, t in items) + "</div>"


def sys_name(a):
    for s, e, n, _ in SYSTEM:
        if s <= a <= e:
            return n
    return ""


def cover(occ, a, b):
    out = set()
    for x in range(a, b):
        for k, who in occ.get(x, {}).items():
            out |= {"%s %s" % (k, w_) for w_ in who}
    return out


def tracks(used, disk, occ, col):
    W, LH, X0 = 1200, 18, 150
    rows = []
    sc = lambda a: X0 + a * (W - X0 - 10) / 65536.0

    def bar(y, rs, color, tip_fn, opacity=1.0):
        out = []
        for a, b in rs:
            x0, x1 = sc(a), sc(b)
            out.append("<rect x='%.1f' y='%d' width='%.1f' height='%d' fill='%s' fill-opacity='%.2f'><title>%s</title></rect>" % (
                x0, y, max(1.0, x1 - x0), LH - 4, color, opacity, E(tip_fn(a, b))))
        return "".join(out)

    y = 22
    out = []
    # scale
    for k in range(0, 17):
        x = sc(k * 4096)
        out.append("<line x1='%.1f' y1='14' x2='%.1f' y2='%d' stroke='currentColor' stroke-opacity='.15'/>" % (x, x, 9999))
        if k < 16:
            out.append("<text x='%.1f' y='11' fill='currentColor' fill-opacity='.6'>$%X000</text>" % (x + 2, k))
    # system
    for s, e, n, note in SYSTEM:
        out.append("<rect x='%.1f' y='%d' width='%.1f' height='%d' fill='currentColor' fill-opacity='%s'><title>%s</title></rect>" % (
            sc(s), y, sc(e + 1) - sc(s) - 1, LH - 4, ".10" if "RAM" == n else ".22", E("%s-%s %s: %s" % (h4(s), h4(e), n, note))))
    out.append("<text x='4' y='%d' fill='currentColor'>C64 system</text>" % (y + 11))
    y += LH + 4
    for m in used:
        c = col[m.name]
        segs = ranges_of(m.bytes)
        tip = lambda a, b, m=m: "%s %s-%s (%d B): %s" % (m.name, h4(a), h4(b - 1), b - a, ", ".join(sorted({m.bytes[x] or "?" for x in range(a, b) if x in m.bytes}))[:300])
        out.append("<text x='4' y='%d' fill='currentColor'>%s</text>" % (y + 11, E(m.name[:18])))
        out.append(bar(y, segs, c, tip))
        vr = ranges_of({(a + i) & 0xFFFF for a, s, _, _ in m.virtual for i in range(s)})
        out.append(bar(y + 3, vr, KCOL[RES], lambda a, b, m=m: "%s variables %s-%s (%d B)" % (m.name, h4(a), h4(b - 1), b - a), .9))
        ir = ranges_of(m.image)
        out.append(bar(y + 6, ir, KCOL[IMG], lambda a, b, m=m: "%s image to be moved %s-%s (%d B) -> runs at %s" % (
            m.name, h4(a), h4(b - 1), b - a, h4(m.image.get(a, a))), .9))
        y += LH
    if disk:
        y += 4
        out.append("<text x='4' y='%d' fill='currentColor'>disk files</text>" % (y + 11))
        lanes = []
        for f in disk["files"]:
            if "load" not in f:
                continue
            for i, lane in enumerate(lanes):
                if all(f["load"] >= g["end"] or f["end"] <= g["load"] for g in lane):
                    lane.append(f); break
            else:
                lanes.append([f])
        for lane in lanes:
            for f in lane:
                out.append(bar(y, [(f["load"], min(f["end"], 0x10000))], KCOL[LOAD], lambda a, b, f=f: "%s %s-%s (%d B)%s" % (
                    f["name"], h4(a), h4(b - 1), b - a, (", modules: " + ", ".join(f["modules"])) if f.get("modules") else
                    (", from the build: " + f["built"]) if f.get("built") else "")))
                out.append("<rect x='%.1f' y='%d' width='1' height='%d' fill='currentColor' fill-opacity='.5'/>" % (sc(f["load"]), y, LH - 4))
            y += LH - 6
        y += 6
    rr = ranges_of(a for a, o in occ.items() if REF in o and len(o) == 1)
    out.append("<text x='4' y='%d' fill='currentColor'>used by the code</text>" % (y + 11))
    out.append(bar(y, rr, "#c99a00", lambda a, b: "%s-%s (%d B) used by: %s" % (h4(a), h4(b - 1), b - a, ", ".join(sorted({w for x in range(a, b) for w in occ[x][REF]})))))
    y += LH
    out.append("<text x='4' y='%d' fill='currentColor'>free</text>" % (y + 11))
    out.append(bar(y, [(a, b) for a, b, _ in free_ranges(occ)], "#4f9d45", lambda a, b: "free %s-%s (%d B)" % (h4(a), h4(b - 1), b - a)))
    y += LH + 4
    svg = "".join(out).replace("y2='9999'", "y2='%d'" % y)
    return "<div class='wrap'><svg class='tracks' viewBox='0 0 %d %d' style='min-width:900px'>%s</svg></div>" % (W, y, svg)


def module_html(m, color, occ):
    P = []
    w = P.append
    own = {}
    for a, o in occ.items():                     # only this module and the data files
        k = {x: v for x, v in o.items() if (m.name in v and x in (CODE, RES, REF, IMG, FILL)) or x == DATA}
        if k:
            own[a] = k
    fm = free_ranges(own)
    segs = ranges_of(m.bytes)
    vbytes = sum(s for _, s, _, _ in m.virtual)
    w("<h3><span style='display:inline-block;width:12px;height:12px;background:%s;margin-right:8px'></span>%s</h3>" % (color, E(m.name)))
    w("<div class='mono dim'>listing %s · output %s · on the disk: %s (%s)</div>" % (E(os.path.basename(m.lst)), E(m.output or "?"),
      E(", ".join(m.disk) or "no"), E(m.link)))
    w("<div class='kv' style='margin-top:8px'><div><b>%d B</b><span>code and data</span></div><div><b>%d B</b><span>reserved variables (%d)</span></div>"
      "<div><b>%d</b><span>contiguous stretches</span></div><div><b>%d B</b><span>images to be moved</span></div><div><b>%d B</b><span>filler</span></div>"
      "<div><b>%d B</b><span>free with only this module (and the data files)</span></div></div>" % (
          len(m.bytes), vbytes, len(m.virtual), len(segs), len(m.image), len(m.filler), sum(b - a for a, b, _ in fm)))
    w("<div class='mono'>%s</div>" % E(" · ".join("%s-%s" % (h4(a), h4(b - 1)) for a, b in segs[:16]) + (" ..." if len(segs) > 16 else "")))
    # source files
    per = {}
    for a, f in m.bytes.items():
        per.setdefault(f or "?", []).append(a)
    w("<details><summary>Source files (%d)</summary><div class='wrap'><table><tr><th>File</th><th class='n'>Bytes</th><th>Addresses</th></tr>" % len(per))
    for f, al in sorted(per.items(), key=lambda x: -len(x[1])):
        rs = ranges_of(al)
        w("<tr><td class='mono'>%s</td><td class='n'>%d</td><td class='mono'>%s</td></tr>" % (E(f), len(al),
          E(", ".join("%s-%s" % (h4(a), h4(b - 1)) for a, b in rs[:5]) + (" ..." if len(rs) > 5 else ""))))
    w("</table></div></details>")
    if m.virtual:
        w("<details><summary>Reserved variables (%d, %d B)</summary><div class='wrap'><table><tr><th>Address</th><th>Name</th><th class='n'>Bytes</th><th>File</th></tr>" % (len(m.virtual), vbytes))
        for a, s, lab, f in sorted(m.virtual):
            w("<tr><td class='mono'>%s</td><td class='mono'>%s</td><td class='n'>%d</td><td class='mono dim'>%s</td></tr>" % (h4(a), E(lab), s, E(f or "")))
        w("</table></div></details>")
    # zero page, I/O, KERNAL
    zp = sorted(a for a in m.refs if a < 0x100)
    zpres = {(a + i) for a, s, _, _ in m.virtual for i in range(s) if a < 0x100}
    io = {}
    for a, k in m.refs.items():
        n = io_name(a)
        if n and a not in m.bytes and a not in zpres:
            io.setdefault(n, {}).setdefault(a, set()).update(k)
    ker = sorted(a for a in m.refs if a in KERNAL)
    names = {v: k for k, v in m.labels.items()}
    w("<details><summary>Zero page, I/O, KERNAL</summary>")
    w("<p class='mono' style='margin:6px 0'>zero page used by the code (%d B): %s</p>" % (len(zp), E(", ".join("%s-%s" % ("$%02X" % a, "$%02X" % (b - 1)) if b - a > 1 else "$%02X" % a for a, b in ranges_of(zp)))))
    for chip, regs in sorted(io.items()):
        w("<p class='mono' style='margin:4px 0'>%s: %s</p>" % (E(chip), E(", ".join("%s%s(%s)" % (h4(a), " " + names[a] if a in names else "", "".join(sorted(k - {"i", "p"})) or "r") for a, k in sorted(regs.items())))))
    if ker:
        w("<p class='mono' style='margin:4px 0'>KERNAL: %s</p>" % E(", ".join("%s %s" % (KERNAL[a], h4(a)) for a in ker)))
    w("</details>")
    big = sorted(fm, key=lambda r: -(r[1] - r[0]))[:8]
    w("<details><summary>Free space with only this module</summary><p class='mono' style='margin:6px 0'>%s</p></details>" % E(
        ", ".join("%s-%s %d B (%s)" % (h4(a), h4(b - 1), b - a, k) for a, b, k in sorted(big))))
    return "".join(P)


def disk_html(disk, used, col):
    P = []
    w = P.append
    fcol = {}
    for i, f in enumerate(disk["files"]):
        mm = f.get("modules")
        fcol[i] = col.get(mm[0]) if mm else PALETTE[(i + 7) % len(PALETTE)]
    w("<section><h2>Disk</h2><div class='kv'><div><b>%s</b><span>name, ID %s</span></div><div><b>%d</b><span>files</span></div>"
      "<div><b>%d / %d</b><span>free blocks (BAM)</span></div><div><b>%d</b><span>tracks</span></div></div>" % (
          E(disk["name"]), E(disk["id"]), len(disk["files"]), disk["free"], disk["total"], disk["tracks"]))
    spt = disk["spt"]
    w("<div class='wrap'><div class='grid' style='grid-template-columns:30px repeat(21,minmax(14px,1fr));min-width:520px'>")
    w("<div></div>" + "".join("<div class='dim' style='text-align:center'>%d</div>" % s for s in range(21)))
    for t in range(1, disk["tracks"] + 1):
        w("<div class='dim' style='text-align:right;padding-right:3px'>%d</div>" % t)
        for s in range(21):
            if s >= spt(t):
                w("<div></div>"); continue
            o = disk["owner"].get((t, s))
            if o == "dir":
                c, tip = "#2a2118", "track %d sector %d: directory and BAM" % (t, s)
            elif o is None:
                free = (t, s) in disk["free_bam"]
                c, tip = ("#4f9d4566" if free else "#e0301e"), "track %d sector %d: %s" % (t, s, "free" if free else "used in the BAM but by no file")
            else:
                f = disk["files"][o]
                c, tip = fcol[o], "track %d sector %d: %s (block %d of %d)" % (t, s, f["name"], f["chain"].index((t, s)) + 1, len(f["chain"]))
            w("<div class='s' style='background:%s' title='%s'></div>" % (c, E(tip, True)))
    w("</div></div>")
    w("<h3>Directory</h3><div class='wrap'><table><tr><th>#</th><th>Name</th><th>Type</th><th class='n'>Blocks</th><th>Loaded at</th>"
      "<th>First block</th><th class='n'>Fragments</th><th>Comes from</th></tr>")
    for i, f in enumerate(disk["files"]):
        frag = 1 + sum(1 for (a, b) in zip(f["chain"], f["chain"][1:]) if b[0] != a[0])
        src = ("modules: " + ", ".join(f["modules"])) if f.get("modules") else ("build: " + f["built"]) if f.get("built") else ""
        w("<tr><td class='n'>%d</td><td class='mono'><span style='display:inline-block;width:10px;height:10px;background:%s;margin-right:6px'></span>%s</td>"
          "<td>%s</td><td class='n'>%d</td><td class='mono'>%s</td><td class='mono'>%d/%d</td><td class='n'>%d</td><td class='mono dim'>%s</td></tr>" % (
              i + 1, fcol[i], E(f["name"]), f["type"], f["blocks"], ("%s-%s" % (h4(f["load"]), h4(f["end"] - 1))) if "load" in f else
              ("elsewhere (file says %s)" % h4(f["fake_load"])) if "fake_load" in f else "",
              f["chain"][0][0] if f["chain"] else 0, f["chain"][0][1] if f["chain"] else 0, frag, E(src)))
    w("</table></div><p class='note'>Fragments = stretches on different tracks. \"Comes from\": module with the listing, or build file with "
      "the same content.</p></section>")
    return "".join(P)


OUTDIR = [None]
MAINS = set()                  # (1.5) modules that are the main file of a declared program
PROBLEMS = set()               # (1.5) annotation problems (--strict)


def other_pages():
    """HTML pages in the output folder written by other tools of the project (not the index, not the program pages)"""
    d = OUTDIR[0]
    return sorted(x for x in os.listdir(d) if x.endswith(".html") and x != "index.html" and not x.startswith("program-")) \
        if d and os.path.isdir(d) else []


# ------------------------------------------------------------------ main
def project_title():
    return setting("C64_VIEW_TITLE", "", root=ROOT, env=False)


def map_of(used, other, disk, title, pr, prog=None):
    """the map of a set of modules and disk files (the whole project, or one program): (page html, data, occ)"""
    occ = layers(used, disk)
    areas, notes, scen, bad = annotations(used)
    if prog:                                          # (1.5) a ;@free note of the main module of another program is not about this one
        own = {m.name for m in prog["modules"] if prog["main"] in (m.disk if disk else [m.name])}
        notes = [x for x in notes if x["module"] in own or x["module"] not in MAINS]
    if prog:                                          # a scenario belongs to the programs that have one of its modules
        scen = {k: v for k, v in scen.items() if set(v) & {m.name for m in used}}
    for x in areas:                                   # an annotated area is in use (a buffer behind a pointer, a table...)
        for ad in range(x["from"], x["to"]):
            occ.setdefault(ad & 0xFFFF, {}).setdefault(RES, set()).add(x["module"])
    fr = free_ranges(occ)
    fa = free_after(occ, areas)
    low = low_map(used, areas, pr)                    # (1.6) pages 0-3
    ann = {"areas": areas, "scenarios": scenario_data(scen, used, disk, areas), "problems": bad, "pairs": label_pairs(used, areas),
           "free_after": fa, "free": fr, "low": low[0], "notes": free_notes(notes, fr, fa, low[1], low[2])}
    for sc_, a, b, (lo, hi) in area_overlaps(areas):          # (1.6) ;@map areas of one scenario that overlap
        bad.append("%s:%d: area overlap in scenario %s: %s \"%s\" and %s \"%s\" (%s-%s; the other one: %s:%d)" % (
            a["file"], a["line"], sc_, a["name"], a["text"], b["name"], b["text"], h4(lo), h4(hi - 1), b["file"], b["line"]))
    for x in ann["notes"]:
        if x["used"]:
            bad.append("%s:%d: @free %s: not free: %s" % (x["file"], x["line"], x["name"], ", ".join("$%04X-$%04X" % (p, q) for p, q in x["used"][:4])))
    for b in bad:
        print("c64map: WARNING " + b)
        PROBLEMS.add(b)
    page = page_html(used, other, disk, occ, title, pr, ann, prog)
    sfx, lab = ("_" + prog["name"], ": " + prog["name"]) if prog else ("", "")
    data = {"free_bytes": sum(b - a for a, b, _ in fr),
            "free_by_bank": {bank: sum(y - x for x, y, k in fr if k == bank) for _, _, bank in BANKS},
            "free_ranges": [{"from": a, "to": b - 1, "bank": k} for a, b, k in fr],
            "never_used_bytes": sum(b - a for a, b, _ in free_ranges(occ, strict=True)),
            "modules": [{"name": m.name, "listing": os.path.basename(m.lst), "output": m.output, "disk": m.disk, "link": m.link,
                         "bytes": len(m.bytes), "reserved": sum(s for _, s, _, _ in m.virtual), "segments": [[x, y - 1] for x, y in ranges_of(m.bytes)]}
                        for m in used]}
    data["metrics"] = [{"id": "ram_free_static" + sfx, "label": "RAM free from the program (static)" + lab, "value": data["free_bytes"],
                        "unit": "B", "better": "up", "hint": "Lab64 memmap: $0400-$FFFF with no code, data, variables or data files"}]
    data["areas"] = [dict(x, to=x["to"] - 1) for x in areas]
    data["low_pages"] = ann["low"]
    data["scenarios"] = ann["scenarios"]
    if ann["notes"]:                                  # (1.5) ;@free
        data["free_notes"] = [dict(x, to=x["to"] - 1) for x in ann["notes"]]
        data["free_by_use"] = {u: sum(x["free_after_start"] for x in ann["notes"] if x["use"] == u) for u in USES}
    data["label_pairs"] = [{"module": m, "name": n, "from": x, "to": y - 1} for m, n, x, y in ann["pairs"]]
    if any(x["free_after"] for x in areas):
        data["free_after_start_bytes"] = sum(y - x for x, y, _ in ann["free_after"])
        data["metrics"].append({"id": "ram_free_after_start" + sfx, "label": "RAM free after start-up (annotations)" + lab,
                                "value": data["free_after_start_bytes"], "unit": "B", "better": "up",
                                "hint": "static free space + the areas marked free-after in the sources"})
    if pr and pr.get("run"):
        nv = probe_ranges(pr["never"])
        data["probe"] = {"dumps": pr["dumps"], "ignored": pr["ignored"], "never_written_bytes": len(pr["never"]),
                         "never_written_by_bank": {bank: sum(y - x for x, y, k in nv if k == bank) for _, _, bank in BANKS},
                         "never_written_ranges": [{"from": x, "to": y - 1, "bank": k} for x, y, k in nv],
                         "scenarios": [{"tag": t, "written": n} for t, n in pr["scenarios"]]}
        data["metrics"].append({"id": "ram_never_written" + sfx, "label": "RAM never written in the tests (VICE)" + lab,
                                "value": len(pr["never"]), "unit": "B", "better": "up", "hint": "run-time probe, %d VICE sessions" % pr["dumps"]})
    elif pr:
        data["probe"] = {"dumps": 0, "ignored": pr["ignored"]}
    return page, data, occ


def disk_data(disk):
    return {"name": disk["name"], "id": disk["id"], "blocks_free": disk["free"], "blocks_total": disk["total"],
            "files": [{"name": f["name"], "type": f["type"], "blocks": f["blocks"], "load": f.get("load"),
                       "end": (f["end"] - 1) if "end" in f else None, "modules": f.get("modules", []), "built": f.get("built")}
                      for f in disk["files"]]}


def kind_at(o):
    """what an address is for the overview of the index: used / data / transient / free"""
    if not o:
        return "free"
    if CODE in o or RES in o or REF in o:
        return "used"
    return "data" if DATA in o else "trans"


def index_html(progs, maps, unassigned, warns, left, used, other, disk, title, decl):
    """the index of the programs: one row each (files, free RAM, probe), all of them side by side, files in no program, disk"""
    P = []
    w = P.append
    col = {m.name: PALETTE[i % len(PALETTE)] for i, m in enumerate(used)}
    w("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>")
    w("<title>%s</title><style>%s</style></head><body>" % (E((title + " · " if title else "") + "Memory maps"), CSS))
    w("<div class='top'><div class='rainbow'><i class='r1'></i><i class='r2'></i><i class='r3'></i><i class='r4'></i><i class='r5'></i></div>"
      "<div class='in'><div class='proj'>%s</div><h1>MEMORY MAPS</h1><div class='sub'>%d programs · one map each · generated "
      "automatically from 64tass listings, labels and disk (containers/tools/memmap/c64map.py)</div></div></div><div class='stripes'><i class='r1'></i>"
      "<i class='r2'></i><i class='r3'></i><i class='r4'></i><i class='r5'></i></div><main>" % (E(title or "C64 project"), len(progs)))
    w("<section><h2>Programs</h2><div class='wrap'><table><tr><th>Program</th><th>Main file</th><th>Main file in memory</th>"
      "<th>Files</th><th>Modules</th><th class='n'>RAM free (static)</th><th class='n'>Free after start-up</th>"
      "<th class='n'>Never written (VICE)</th><th>Scenarios</th></tr>")
    for p in progs:
        d = maps[p["name"]]
        mm = [m for m in p["modules"] if p["main"] in (m.disk if disk else [m.name])]
        if mm:
            where = ", ".join("%s-%s" % (h4(x), h4(y - 1)) for x, y in ranges_of(set().union(*(m.bytes for m in mm)))[:3])
        else:
            f = next((f for f in disk["files"] if f["name"] == p["main"]), {}) if disk else {}
            where = "%s-%s (file)" % (h4(f["load"]), h4(f["end"] - 1)) if "load" in f else "?"
        shared = [f for f in p["files"] if sum(1 for q in progs if f in q["files"]) > 1]
        files = E(" ".join(p["files"])) + ("<br><span class='dim'>also in other programs: %s</span>" % E(" ".join(shared)) if shared else "")
        pb = d.get("probe", {})
        nw = "%d B <span class='dim'>(%d sessions)</span>" % (pb["never_written_bytes"], pb["dumps"]) if pb.get("dumps") else "<span class='dim'>none</span>"
        sc = d["scenarios"]
        scs = ", ".join("%s%s" % (E(x["name"]), " <b>conflict</b>" if x["conflicts"] else "") for x in sc) or "<span class='dim'>none</span>"
        w("<tr><td><a href='%s'><b>%s</b></a></td><td class='mono'>%s</td><td class='mono'>%s</td><td class='mono'>%s</td><td class='mono'>%s</td>"
          "<td class='n'><b>%d B</b></td><td class='n'>%s</td><td class='n'>%s</td><td>%s</td></tr>" % (
              E("program-%s.html" % p["name"], True), E(p["name"]), E(p["main"]), E(where), files,
              E(" ".join(m.name for m in p["modules"])) or "<span class='dim'>no listing</span>", d["free_bytes"],
              "%d B" % d["free_after_start_bytes"] if "free_after_start_bytes" in d else "<span class='dim'>-</span>", nw, scs))
    w("</table></div><p class='note'>A <b>program</b> is what can be in memory at the same time: the main file that runs and the files it "
      "loads (overlays, data, saves). Programs replace each other, so every program has its own map and its own free RAM. "
      "<b>RAM free (static)</b> = $0400-$FFFF with no code, data, variable or used address of the program's modules and no data file "
      "of the program loaded there (its overlays are added up: the page of the program shows them one by one). Declared in "
      "<code>lab64.env</code> (below). <b>Never written</b>: VICE sessions of the tests whose RAM, at the end, held the main file of "
      "the program.</p></section>")
    # --- side by side
    W, LH, X0 = 1200, 20, 150
    sc_ = lambda a: X0 + a * (W - X0 - 10) / 65536.0
    KC = {"used": None, "data": KCOL[DATA], "trans": KCOL[LOAD], "free": "#4f9d45"}
    out, y = [], 22
    for k in range(0, 17):
        x = sc_(k * 4096)
        out.append("<line x1='%.1f' y1='14' x2='%.1f' y2='9999' stroke='currentColor' stroke-opacity='.15'/>" % (x, x))
        if k < 16:
            out.append("<text x='%.1f' y='11' fill='currentColor' fill-opacity='.6'>$%X000</text>" % (x + 2, k))
    for s_, e_, n_, note in SYSTEM:
        out.append("<rect x='%.1f' y='%d' width='%.1f' height='%d' fill='currentColor' fill-opacity='%s'><title>%s</title></rect>" % (
            sc_(s_), y, sc_(e_ + 1) - sc_(s_) - 1, LH - 6, ".10" if n_ == "RAM" else ".22", E("%s-%s %s: %s" % (h4(s_), h4(e_), n_, note))))
    out.append("<text x='4' y='%d' fill='currentColor'>C64 system</text>" % (y + 11))
    y += LH + 2
    for i, p in enumerate(progs):
        occ = maps[p["name"]]["_occ"]
        pc = PALETTE[i % len(PALETTE)]
        cur, start = None, 0x0400
        for a in range(0x0400, 0x10001):
            k = kind_at(occ.get(a)) if a < 0x10000 else None
            if k != cur:
                if cur is not None:
                    out.append("<rect x='%.1f' y='%d' width='%.1f' height='%d' fill='%s' fill-opacity='%s'><title>%s</title></rect>" % (
                        sc_(start), y, max(1.0, sc_(a) - sc_(start)), LH - 6, KC[cur] or pc, ".55" if cur == "free" else "1",
                        E("%s %s-%s (%d B): %s" % (p["name"], h4(start), h4(a - 1), a - start, {"used": "code, data, variables",
                          "data": "data files", "trans": "only images, fillers, module files", "free": "free"}[cur]))))
                cur, start = k, a
        out.append("<a href='%s'><text x='4' y='%d' fill='currentColor' style='text-decoration:underline'>%s</text></a>" % (
            E("program-%s.html" % p["name"], True), y + 11, E(p["name"][:18])))
        y += LH
    svg = "".join(out).replace("y2='9999'", "y2='%d'" % y)
    w("<section><h2>Programs side by side</h2><div class='legend'><span><i style='background:%s'></i>code, data, variables (colour of "
      "the program)</span><span><i style='background:%s'></i>data files</span><span><i style='background:%s'></i>only images, fillers, "
      "module files</span><span><i style='background:#4f9d4566'></i>free</span></div><div class='wrap'><svg class='tracks' "
      "viewBox='0 0 %d %d' style='min-width:900px'>%s</svg></div><p class='note'>$0400-$FFFF of every program (below $0400: "
      "system). Hover a stretch for the details; the name opens the map of the program.</p></section>" % (
          PALETTE[0], KCOL[DATA], KCOL[LOAD], W, y, svg))
    # --- problems
    if warns or unassigned or left:
        w("<section><h2>To check</h2>")
        for x in warns:
            w("<p class='note'><b>Warning:</b> %s</p>" % E(x))
        if unassigned and disk:
            w("<h3>Files in no program</h3><div class='wrap'><table><tr><th>File</th><th>Loaded at</th><th>Module</th></tr>")
            for f in disk["files"]:
                if f["name"] in unassigned:
                    w("<tr><td class='mono'>%s</td><td class='mono'>%s</td><td class='mono'>%s</td></tr>" % (
                        E(f["name"]), ("%s-%s" % (h4(f["load"]), h4(f["end"] - 1))) if "load" in f else "elsewhere",
                        E(", ".join(f.get("modules", [])))))
            w("</table></div><p class='note'>Not in any map: add them to the program that loads them.</p>")
        if left:
            w("<h3>VICE sessions in no program</h3><div class='wrap'><table><tr><th>Session</th><th>Closest program</th>"
              "<th class='n'>Its main file found</th></tr>")
            for d, n, x in left:
                w("<tr><td class='mono'>%s</td><td>%s</td><td class='n'>%d%%</td></tr>" % (E(d["tag"]), E(n), round(100 * x)))
            w("</table></div><p class='note'>At the end of these sessions less than %d%% of the main file of any program was in the "
              "RAM (a session that ended in BASIC or in a program with no declaration): not counted in any map.</p>" % round(100 * MATCH))
        w("</section>")
    # --- declaration
    w("<section><h2>Declaration (lab64.env)</h2><pre class='mono' style='white-space:pre-wrap;margin:0'>%s</pre><p class='note'>"
      "<code>C64_MAP_PROGRAM_&lt;NAME&gt;=\"main file, then the other files\"</code>: disk file names, case-insensitive, with the "
      "wildcards <code>*</code> <code>?</code> <code>[..]</code>; the first name is the main file. A file may be in several programs. "
      "Scenarios (<code>;@scenario</code>, <code>C64_MAP_SCENARIOS</code>) are shown in every program that has one of their "
      "modules.</p></section>" % E("\n".join('C64_MAP_PROGRAM_%s="%s"' % (n.upper(), " ".join(v)) for n, v in decl)))
    if disk:
        w(disk_html(disk, used, col))
    if other:
        w("<section><h2>Other listings</h2><p class='note' style='margin-top:0'>Listings whose file is not on the disk (e.g. test "
          "variants): in no map. %s</p></section>" % E(", ".join("%s (%d B)" % (m.name, len(m.bytes)) for m in other)))
    others = other_pages()
    if others:
        w("<section><h2>Other pages</h2><p class='note' style='margin-top:0'>In the same folder (written by other tools of the project): %s</p></section>" % ", ".join(
            "<a href='%s'>%s</a>" % (E(x, True), E(x)) for x in others))
    w("</main></body></html>")
    return "\n".join(P)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default="out/work", help="folder with *.lst, *.lbl, *.prg (default out/work)")
    ap.add_argument("--disk", default="out/work/disk.d64", help=".d64 disk (default out/work/disk.d64)")
    ap.add_argument("--out", default="out/work/memory-map", help="output folder (default out/work/memory-map)")
    ap.add_argument("--title", default=None, help="project name (default: C64_VIEW_TITLE of lab64.env)")
    ap.add_argument("--probe", default=None, help="RAM dumps of the run-time probe in VICE (default out/work/memprobe if it exists)")
    ap.add_argument("--strict", action="store_true", help="(1.5) exit 1 if an annotation is wrong (not understood, label not found, "
                    "a ;@free area that is not free): the pages are written all the same")
    a = ap.parse_args()
    used, other, disk = analyse(a.work, a.disk)
    if not used and not other:
        sys.exit("c64map: no 64tass listing (*.lst, option -L) in %s" % a.work)
    if not used:
        sys.exit("c64map: %d 64tass listings in %s (%s), but none matches a file of the disk %s (same content or same name): "
                 "build the disk from these programs, or --disk" % (len(other), a.work, ", ".join(m.name for m in other), a.disk))
    os.makedirs(a.out, exist_ok=True)
    OUTDIR[0] = a.out
    for x in glob.glob(os.path.join(a.out, "program-*.html")):     # pages of programs no longer declared
        os.remove(x)
    title = a.title if a.title is not None else project_title()
    pdir = a.probe if a.probe is not None else os.path.join(a.work, "memprobe")
    dumps, ignored = probe_dumps(pdir, a.disk if disk else None, a.work)
    decl = declared_programs()
    if not decl:                                      # no programs declared: one map of everything (as before 1.4)
        page, data, _ = map_of(used, other, disk, title, probe_summary(dumps, ignored))
        open(os.path.join(a.out, "index.html"), "w").write(page)
        data = dict({"schema": 1}, **data)
        data["other_listings"] = [m.name for m in other]
        if disk:
            data["disk"] = disk_data(disk)
        json.dump(data, open(os.path.join(a.out, "memmap.json"), "w"), indent=1)
        pb = data.get("probe", {})
        print("c64map: %s (%d modules, %d B free from the program%s%s)" % (os.path.join(a.out, "index.html"), len(used), data["free_bytes"],
              ", disk %d/%d blocks free" % (disk["free"], disk["total"]) if disk else "",
              ", probe: %d B never written in %d VICE sessions" % (pb["never_written_bytes"], pb["dumps"]) if pb.get("dumps") else ""))
        strict_exit(a.strict)
        return
    progs, unassigned, warns = resolve_programs(decl, used, disk)
    mprogs = metric_programs(progs, warns)
    by_prog, left = assign_dumps(dumps, progs, used, disk)
    MAINS.update(m.name for p in progs for m in p["modules"] if p["main"] in (m.disk if disk else [m.name]))
    maps = {}
    for p in progs:
        sub = dict(disk, files=[f for f in disk["files"] if f["name"] in p["files"]]) if disk else None
        pr = probe_summary(by_prog[p["name"]], 0) if dumps else (probe_summary([], ignored) if ignored else None)
        page, d, occ = map_of(p["modules"], [], sub, title, pr, p)
        open(os.path.join(a.out, "program-%s.html" % p["name"]), "w").write(page)
        maps[p["name"]] = dict({"name": p["name"], "main": p["main"], "files": p["files"], "page": "program-%s.html" % p["name"]}, **d)
        maps[p["name"]]["_occ"] = occ
    for x in warns:
        print("c64map: WARNING " + x)
    open(os.path.join(a.out, "index.html"), "w").write(index_html(progs, maps, unassigned, warns, left, used, other, disk, title, decl))
    data = {"schema": 2, "programs": [{k: v for k, v in maps[p["name"]].items() if k not in ("_occ", "metrics")} for p in progs],
            "unassigned_files": unassigned, "warnings": warns, "other_listings": [m.name for m in other],
            "probe": {"dumps": len(dumps), "ignored": ignored, "not_assigned": [{"tag": d["tag"], "closest": n, "share": round(x, 3)}
                                                                                for d, n, x in left]},
            "metrics": [x for p in mprogs for x in maps[p["name"]]["metrics"]]}
    if disk:
        data["disk"] = disk_data(disk)
    json.dump(data, open(os.path.join(a.out, "memmap.json"), "w"), indent=1)
    for p in progs:
        d = maps[p["name"]]
        print("c64map: %-12s %5d B free%s%s" % (p["name"], d["free_bytes"],
              ", %d B after start-up" % d["free_after_start_bytes"] if "free_after_start_bytes" in d else "",
              ", probe: %d B never written in %d sessions" % (d["probe"]["never_written_bytes"], d["probe"]["dumps"])
              if d.get("probe", {}).get("dumps") else ""))
    print("c64map: %s (%d programs%s%s)" % (os.path.join(a.out, "index.html"), len(progs),
          ", disk %d/%d blocks free" % (disk["free"], disk["total"]) if disk else "",
          ", %d probe sessions in no program" % len(left) if left else ""))
    strict_exit(a.strict)


def strict_exit(strict):
    if strict and PROBLEMS:
        sys.exit("c64map: --strict: %d annotation problems (WARNING lines above)" % len(PROBLEMS))


if __name__ == "__main__":
    main()
