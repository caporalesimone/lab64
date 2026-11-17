"""VICE remote monitor library of Lab64 (10/11). Copyright (c) 2026 - Simone Caporale

x64sc with the remote monitor (1.13: a free port per VICE, Vice().port; free_port() for project tools), started with factory settings and ALL the ROMs of Lab64 roms/ (no user
configuration, nothing from VICE's data folder): a fast client (no fixed delays: it waits for the prompt or the stop),
program labels and listings of the 64tass build (out/work/<name>.lbl / .lst), memory access, routine calls, screenshots,
and the run-time memory probe (C64_MEMPROBE=1, or 2 for the second pass with another pattern; containers/tools/memmap/probe.py).

Protocol: the VICE remote monitor runs one command per line and answers with the prompt "(C:$xxxx) "; several lines in one
send are not all executed, so every command waits for its prompt. "x" (continue) answers only at the next stop ("Stop on ..."):
the stop line holds the C64 cycle counter, used to measure frame durations.

Use (in lab64-tools, project in /work; the Lab64 library is importable there):  from vicemon import Vice, labels
ROM folders for project tools: ROMS_C64 (Kernal, Basic, chargen), ROMS (drives), ROMS_ALL.
Project folder: C64_ROOT, or the current folder. Display: a virtual display per VICE (xvfb-run), or the shared viewer screen with
C64_VIEW=1 and DISPLAY (lab64 view)."""
import glob, os, re, shutil, signal, socket, subprocess, sys, time

ROOT = os.environ.get("C64_ROOT") or os.getcwd()             # the project
OUT = os.path.join(ROOT, "out", "work")
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # containers/tools
ROMS_ALL = os.path.join(os.environ.get("C64_ROMS", "/opt/roms"), "vice-roms")   # the copy inside the image (made at build time from Lab64 roms/); subfolders as in VICE: C64/ and DRIVES/
ROMS_C64 = os.path.join(ROMS_ALL, "C64")
ROMS_DRIVES = ROMS = os.path.join(ROMS_ALL, "DRIVES")
ROM_ARGS = ["-default",
            "-kernal", ROMS_C64 + "/kernal-901227-03.bin", "-basic", ROMS_C64 + "/basic-901226-01.bin",
            "-chargen", ROMS_C64 + "/chargen-901225-01.bin",
            "-dos1541", ROMS_DRIVES + "/dos1541-325302-01+901229-05.bin", "-dos1541II", ROMS_DRIVES + "/dos1541ii-251968-03.bin",
            "-dos1570", ROMS_DRIVES + "/dos1570-315090-01.bin", "-dos1571", ROMS_DRIVES + "/dos1571-310654-05.bin"]
# display: a virtual display per VICE (xvfb-run), or the shared viewer screen (C64_VIEW=1 with DISPLAY)
XRUN = [] if os.environ.get("C64_VIEW") == "1" and os.environ.get("DISPLAY") else ["xvfb-run", "-a"]
sys.path.insert(0, os.path.join(TOOLS, "memmap"))
import probe as memprobe  # noqa: E402  (run-time memory probe)

# Boot wait (14/11). VICE opens the remote monitor port BEFORE the C64 has finished starting: on a cold machine ~7 s pass between
# the two. A program started before the KERNAL has set the IRQ vectors ($0314/5) runs the C64 into nothing and the breakpoint
# never comes. No fixed time: the C64 is watched. Ready = IRQ vectors at the standard value ($EA31) AND "READY." on the screen
# (row 5, $04C8).
_READY = [0x12, 0x05, 0x01, 0x04, 0x19, 0x2E]                  # screen codes of "READY."


def _mem(s, a, n, tmax=5):
    """n bytes from a, through the remote monitor (the machine stops in the monitor); None if no answer within tmax seconds"""
    s.settimeout(0.05)
    try:                                                          # leftovers of earlier answers
        while s.recv(65536): pass
    except OSError:
        pass
    s.sendall(("m %04x %04x\n" % (a, a + n - 1)).encode())
    buf, t0 = "", time.time()
    while time.time() - t0 < tmax:
        try:
            d = s.recv(65536)
            if d: buf += d.decode(errors="ignore")
        except socket.timeout:
            pass
        if PROMPT.search(buf):
            m = re.search(r">C:%04x\s+((?:[0-9a-f]{2}\s+){%d})" % (a, n), buf)
            if m: return [int(x, 16) for x in m.group(1).split()]
    return None


def wait_boot(s, tmax=30):
    """waits until the C64 behind the remote monitor (socket s) is ready (see above); leaves it running.
    Raises RuntimeError after tmax seconds."""
    t0 = time.time()
    while True:
        vec, scr = _mem(s, 0x0314, 2), _mem(s, 0x04C8, len(_READY))
        if vec == [0x31, 0xEA] and scr == _READY:
            s.sendall(b"x\n")                                     # go on (the first mem stopped it in the monitor)
            return
        if time.time() - t0 > tmax:
            raise RuntimeError("VICE: the C64 is not ready after %d s (IRQ vectors %s, screen %s)" % (tmax, vec, scr))
        s.sendall(b"x\n")                                         # still starting: let it run and try again
        time.sleep(0.15)


PROMPT = re.compile(r"\(C:\$[0-9a-f]{4}\) $")
PROMPT_ANY = re.compile(r"\(C:\$[0-9a-f]{4}\) ")           # every prompt (the monitor entry of a running machine prints one more)
BARE_RESUME = re.compile(r"^(x|exit|g(\s+\S+)?)$")           # commands that let the C64 run (no answer until a stop)
STOP = re.compile(r"Stop on[^\n]*\n[^\n]*?(\d+)\s*\n", re.S)
FRAME = 19656                                     # cycles of a PAL frame
PROBE_DIR = os.path.join(OUT, "memprobe")         # C64_MEMPROBE=1: RAM dumps of every VICE session (set by the project build or by hand)


def labels(name="main"):
    """labels and constants of out/work/<name>.lbl ($hex and decimal); (1.13) default "main", the file of the default build"""
    t = open(os.path.join(OUT, name + ".lbl")).read()
    d = {m.group(1): int(m.group(2), 16) for m in re.finditer(r"^(\w+)\s*=\s*\$([0-9a-f]+)", t, re.M)}
    d.update({m.group(1): int(m.group(2)) for m in re.finditer(r"^(\w+)\s*=\s*(\d+)\s*$", t, re.M)})
    return d


def listing(name="main"):
    return open(os.path.join(OUT, name + ".lst")).read()


def addr_after(lst, label, pattern):
    """address of the first listing line after 'label:' whose instruction text matches pattern"""
    i = lst.index("\n" + label + ":") if ("\n" + label + ":") in lst else lst.index(label + ":")
    for ln in lst[i:].splitlines():
        m = re.match(r"^\.([0-9a-f]{4})\s+(?:[0-9a-f]{2}\s){1,3}\s*(.*)$", ln)
        if m and re.search(pattern, m.group(2)):
            return int(m.group(1), 16)
    raise KeyError("%s: %s not found" % (label, pattern))


class MonitorError(RuntimeError):
    pass


def drain(s, wait=0.0):
    """discard what is waiting on the socket, with a very short wait for late lines (a stop prints its register line a
    moment after "Stop on": without the wait a late prompt would be taken as the answer to the next command)"""
    if wait: s.settimeout(wait)
    else: s.setblocking(False)
    try:
        while s.recv(65536): pass
    except (socket.timeout, BlockingIOError, OSError):
        pass
    finally:
        s.settimeout(0.02)


def sync(s, c, tmax=20):
    """for scripts with their own socket: one command and its answer up to the prompt (no fixed delays).
    "" = drain without sending (an empty line would repeat the last command); "l ..." waits for "Loading"."""
    s.settimeout(0.02)
    if c == "":
        return settle(s, 0)
    drain(s, 0.02)                                  # leftovers of a previous answer (prompt after "Stop on"; the scripts read
                                                    # "Stop on" themselves and leave the rest of the stop text behind)
    s.sendall((c + "\n").encode())
    buf, t0 = "", time.time()
    load, mem = c.startswith("l "), c.startswith("m ")
    while time.time() - t0 < tmax:
        try:
            d = s.recv(65536)
            if d: buf += d.decode(errors="ignore")
        except socket.timeout:
            pass
        if PROMPT.search(buf) and (not load or "Loading" in buf) and (not mem or ">C:" in buf): return buf
    raise MonitorError("monitor: no answer to '%s'" % c)


def settle(s, boot=1.0, gap=0.1):
    """wait for the C64 boot (warp), then for the monitor to be silent"""
    time.sleep(boot)
    s.settimeout(0.02)
    buf, last = "", time.time()
    while time.time() - last < gap:
        try:
            d = s.recv(65536).decode(errors="ignore")
            if d: buf += d; last = time.time()
        except Exception:
            pass
    return buf


def free_port():
    """(1.13, TODO L21) a free TCP port on 127.0.0.1 for one VICE remote monitor: the commands of a project share the lab64-tools
    container (lab64 up), so a fixed port (6510) let two VICE sessions answer each other. Pass it to x64sc with
    -remotemonitor -remotemonitoraddress ip4://127.0.0.1:<port> (vice_env.sh: VMON, VMON_PORT)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Vice:
    """x64sc in warp with the remote monitor. disk: d64 mounted in drive 8 (a copy, so the original is untouched)."""
    _probe_n = 0
    _probe_sessions = 0

    def __init__(self, disk=None, extra=(), inplace=False, warp=True, show=False, boot_tmax=30, boot_wait=None):
        """inplace=True: the disk is mounted as is (writes persist: needed by save tests across sessions).
        warp=False: real speed; show=True: a visible VICE window (no xvfb-run).
        (14/11, TODO I11) it waits for the C64 itself to be ready (IRQ vectors and READY. on the screen, wait_boot),
        not for a fixed time: the monitor port opens ~7 s before the boot ends on a cold machine. Then the machine is
        stopped in the monitor (15/11): "x" (go) lets it run.
        boot_wait=<seconds>: the old fixed wait, only for VICE started with -autostart (no READY. on the screen then)."""
        self.disk, self.probing, self.running = None, False, False   # running: see resume()
        args = ([] if show else XRUN) + [
                "x64sc", "-silent", "-sounddev", "dummy"] + ROM_ARGS + (["-warp"] if warp else [])
        if disk and inplace:
            args += ["-8", disk]
        elif disk:
            self.disk = os.path.join(OUT, "test_%d.d64" % os.getpid())
            shutil.copy(disk, self.disk)
            args += ["-8", self.disk]
        self.port = free_port()
        args += list(extra) + ["-remotemonitor", "-remotemonitoraddress", "ip4://127.0.0.1:%d" % self.port]
        self.p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)   # own group: close() kills xvfb-run AND x64sc
        self.s = None
        t0 = time.time()
        while time.time() - t0 < 20:
            try:
                self.s = socket.create_connection(("127.0.0.1", self.port)); break
            except OSError:
                time.sleep(0.05)
        try:
            if not self.s:
                raise MonitorError("VICE: remote monitor not reachable")
            if boot_wait is None:
                try:
                    wait_boot(self.s, boot_tmax)        # the C64 reaches READY. (warp)
                except RuntimeError as e:
                    raise MonitorError(str(e))
            else:
                time.sleep(boot_wait)
                self.running = True                     # the program is left running (see resume())
            self.s.settimeout(0.02)
            self.quiet()
            if boot_wait is None:
                # (15/11) wait_boot leaves the C64 RUNNING. The first command sent to a running machine gets the prompt of the
                # monitor entry FIRST, then its own output and prompt: when that first prompt arrives alone, cmd() returns on
                # it and every later answer comes one command late (and a command can then reach VICE in the same read as
                # the one before: VICE runs only the first line of a read). One command whose answer is recognised by its
                # content (">C:" of "m", up to its own prompt) stops the machine in the monitor: Vice() hands over a STOPPED
                # machine with commands and answers in step. Not with -autostart (boot_wait): that program is left running.
                self.running = True                     # (16/11) the flag does what the content check did: cmd() skips the entry prompt
                self.mem(0x0314, 2)
                self.quiet(0.05)
            # (14/11, TODO T1) run-time memory probe: RAM filled with a known pattern right after the boot, saved by close().
            # Not with -autostart (boot_wait): the program is already loading, the fill would overwrite it.
            if os.environ.get("C64_MEMPROBE") in ("1", "2") and boot_wait is None:   # 2 = second pattern (second pass)
                self.probe_variant = int(os.environ["C64_MEMPROBE"])
                for c in memprobe.fill_commands(PROBE_DIR, self.probe_variant):
                    self.cmd(c)
                Vice._probe_sessions += 1
                self.probe_session, self.probe_seq = "%d_%d" % (os.getpid(), Vice._probe_sessions), 0   # (1.6) dumps of one session
                self.probing, self.probe_disk = True, memprobe.file_sha1(disk)
        except Exception:
            self.close()                                # no VICE left running
            raise

    # ---- protocol
    def quiet(self, gap=0.15, tmax=5):
        """read and discard until the monitor is silent for 'gap' seconds"""
        buf, last, t0 = "", time.time(), time.time()
        while time.time() - last < gap and time.time() - t0 < tmax:
            try:
                d = self.s.recv(65536).decode(errors="ignore")
                if d: buf += d; last = time.time()
            except Exception:
                pass
        return buf

    def _read(self, done, tmax, what):
        buf, t0 = "", time.time()
        while time.time() - t0 < tmax:
            try:
                d = self.s.recv(65536)
                if d: buf += d.decode(errors="ignore")
            except socket.timeout:
                pass
            except Exception as e:
                raise MonitorError("monitor: connection lost during '%s' (%s)" % (what, e))
            if done(buf): return buf
        raise MonitorError("monitor: no answer to '%s' in %d s (got: %r)" % (what, tmax, buf[-160:]))

    def resume(self):
        """(16/11, TODO L32) let the C64 run and return at once (a bare "x"); it stays running until the next stop (go()) or
        the next command. The first command sent to a running machine makes VICE re-enter the monitor: its answer is
        preceded by one extra prompt. The flag `running` makes cmd() expect it, so the answers stay in step."""
        self.s.sendall(b"x\n")
        self.running = True

    def _stopped_meanwhile(self):
        """running machine: has it stopped by itself (a breakpoint)? Then the monitor already printed its stop and prompt, and
        the next command gets no extra prompt"""
        if self.running and PROMPT.search(self.quiet(0.03)):
            self.running = False
        return not self.running

    def cmd(self, c, tmax=20):
        if BARE_RESUME.match(c.strip()):             # "x", "exit", "g [addr]": nothing to wait for (a stop comes later)
            self.s.sendall((c + "\n").encode())
            self.running = True
            return ""
        self._stopped_meanwhile()
        extra = 1 if self.running else 0             # prompt of the monitor entry, before the answer (see resume())
        self.s.sendall((c + "\n").encode())          # (no drain: "m" answers need ">C:" lines, "x" needs "Stop on")
        m = c.startswith("m ")
        b = self._read(lambda b: len(PROMPT_ANY.findall(b)) > extra and PROMPT.search(b) and (not m or ">C:" in b), tmax, c)
        self.running = False
        return PROMPT_ANY.sub("", b, count=1) if extra else b      # the entry prompt is not part of the answer

    def go(self, tmax=30):
        """continue up to the next stop; returns the cycle counter at the stop (the machine is then stopped: `running` is
        cleared, also when a resume() came before)"""
        self.s.sendall(b"x\n")
        b = self._read(lambda b: "Stop on" in b and PROMPT.search(b), tmax, "x")
        self.running = False
        m = STOP.search(b)
        return int(m.group(1)) if m else None

    def load(self, prg):
        self._stopped_meanwhile()
        self.s.sendall(('l "%s" 0\n' % prg).encode())
        self._read(lambda b: "Loading" in b and PROMPT.search(b), 20, "load " + prg)
        self.running = False
        self.quiet(0.05)

    # ---- memory
    def mem(self, a, n):
        got = {}
        for _ in range(3):                          # (a late stop line can cut an answer: ask again)
            for m in re.finditer(r">C:([0-9a-f]{4})\s+((?:[0-9a-f]{2}\s+)+)", self.cmd("m %04x %04x" % (a, a + n - 1))):
                for i, x in enumerate(m.group(2).split()): got[int(m.group(1), 16) + i] = int(x, 16)
            if all(a + i in got for i in range(n)): break
        return [got[a + i] for i in range(n)]

    def b(self, a): return self.mem(a, 1)[0]
    def w16(self, a): m = self.mem(a, 2); return m[0] + 256 * m[1]
    def poke(self, a, *v): self.cmd("> %04x %s" % (a, " ".join("%02x" % (x & 255) for x in v)))
    def poke16(self, a, v): self.poke(a, v & 255, v >> 8)
    def fill(self, a, e, v=0): self.cmd("f %04x %04x %02x" % (a, e, v))
    def brk(self, a): self.cmd("break %04x" % a)
    def delbrk(self): self.cmd("del")
    def pc(self, a): self.cmd("r pc=%04x" % a)

    def regs(self):
        """registers at the current stop: dict pc, a, x, y, sp"""
        m = re.search(r"\.;([0-9a-f]{4}) ([0-9a-f]{2}) ([0-9a-f]{2}) ([0-9a-f]{2}) ([0-9a-f]{2}) [0-9a-f]{2} [0-9a-f]{2} ([01]{8})", self.cmd("r"))
        r = dict(zip(("pc", "a", "x", "y", "sp"), (int(v, 16) for v in m.groups()[:5])))
        r["c"], r["z"] = int(m.group(6)[7]), int(m.group(6)[6])          # flags NV-BDIZC
        return r

    def call(self, a, tmax=30, stub=0x0340, regs=""):
        """call routine a (sei; jsr a; nop) and stop when it returns; regs = e.g. 'a=01'"""
        self.poke(stub, 0x78, 0x20, a & 255, a >> 8, 0xea)
        self.brk(stub + 4); self.pc(stub)
        if regs: self.cmd("r " + regs)
        c = self.go(tmax); self.delbrk()
        return c

    def screenshot(self, path):
        self.cmd('screenshot "%s" 2' % path)

    def _probe_dump(self):
        """saves the whole RAM of the session (memory probe, containers/tools/memmap/probe.py): file and meta (tag, disk, pattern, session id, sequence
        number). Raises if the file is not complete after 5 s."""
        Vice._probe_n += 1
        self.probe_seq += 1
        tag = os.environ.get("C64_MEMPROBE_TAG", "vice")
        p = os.path.join(PROBE_DIR, "%s_p%d_%d_%d.bin" % (re.sub(r"\W+", "_", tag), self.probe_variant, os.getpid(), Vice._probe_n))
        for c in memprobe.dump_commands(p):
            self.cmd(c)
        t0 = time.time()                                # the save must be complete before "quit" / before the machine goes on
        while time.time() - t0 < 5 and (not os.path.isfile(p) or os.path.getsize(p) < 0x10000):
            time.sleep(0.02)
        if not os.path.isfile(p) or os.path.getsize(p) < 0x10000:
            raise MonitorError("memory probe: the dump %s was not written" % p)
        memprobe.write_meta(p, tag, self.probe_disk, self.probe_variant, self.probe_session, self.probe_seq)

    def probe_checkpoint(self):
        """(1.6, TODO L33) memory probe: save a dump in the middle of the session; nothing when the probe is off. Call it just
        before the C64 switches to another program (e.g. before the key that makes a loader start the game): the dump is
        attributed by lab64 map to the program in RAM now, and the next dump of the session (the next checkpoint, or close())
        counts only what changed since. The machine is left as it was (stopped, or running again after a resume())."""
        if not self.probing:
            return
        was_running = self.running
        self._probe_dump()
        if was_running:
            self.resume()

    def close(self):
        if self.probing:
            try:                                        # memory probe: the whole RAM of this session (Lab64 containers/tools/memmap/probe.py)
                self._probe_dump()
            except Exception:
                pass
            self.probing = False
        try:
            self.s.sendall(b"quit\n")
        except Exception:
            pass
        try:
            self.p.wait(2)
        except Exception:
            pass
        try:
            os.killpg(self.p.pid, signal.SIGKILL)       # whatever is left of the group (x64sc that ignored quit, Xvfb)
        except Exception:
            pass
        try:
            self.p.wait(2)
        except Exception:
            pass
        if self.disk and os.path.exists(self.disk):
            os.remove(self.disk)
