#!/usr/bin/env python3
"""Viewer player (14/11; in py/ since 15/11): starts VICE on the shared viewer screen when the index page asks, and renders .sid files
for SID Studio (1.8). Copyright (c) 2026 - Simone Caporale

It runs in the lab64-player container (lab64-tools image, project in /work = current folder), started by lab64 view (compose service
"player") ALWAYS since 1.8: "render" needs no project setting. "play" and "basic" need C64_VIEW_PLAYER in lab64.env (the command that
starts VICE on a .d64, e.g. tools/vice/play.sh). The viewer has NO Docker socket (= root on the host): it talks to this process
through a Unix socket in the shared lab64-x11 volume. The container has no network (network_mode: none).

Protocol: one JSON line per request, one JSON line per answer.
  {"cmd": "status"}                                        -> {"ok": true, "running": bool, "disk": ..., "since": ...}
  {"cmd": "play", "disk": "releases/v1.244/x_1541.d64"}    -> starts VICE on out/<disk> (closes the previous one)
  {"cmd": "basic"}                                         -> runs the command with --bare (VICE with no disk, for manual tries)
  {"cmd": "stop"}                                          -> closes VICE
  {"cmd": "render", "src": "releases/v1/x.sid" | "sid_b64": "<base64 of a .sid>", "params": {...}}
        -> {"ok": true, "file": "cache/sidrender/<sha256>.wav", "seconds": 180.0, "took": 14.2, "cached": false, "params": {...},
            "tune": {...}} | {"ok": false, "error": "...", "code": "invalid" | "busy" | "failed"}
      renders with containers/tools/py/sidrender.py (sidplayfp): params are validated again there (whitelist / ranges); src is a path relative to out/
      (same rules as the disk: no ../, no links outside out/, must end in .sid), sid_b64 a file of at most 65 KB + header; ONE render
      at a time (a second request while one runs answers "busy"), at most RENDER_TIMEOUT seconds; "status", "play" and "stop" are
      not blocked by a render (one thread per connection)
The disk is a path relative to out/ that must exist, end in .d64/.g64/.prg/.t64/.crt and stay inside out/ (no ../, no links
pointing outside)."""
import base64, binascii, json, os, re, shlex, signal, socket, subprocess, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "common", "py"))   # psid, d64, lab64env

ROOT = os.getcwd()                                  # the project (run.sh: /work)
OUT = os.path.realpath(os.path.join(ROOT, "out"))
SOCK = os.environ.get("C64_PLAYER_SOCK", "/tmp/.X11-unix/lab64-player.sock")
CMD = shlex.split(os.environ.get("C64_VIEW_PLAYER", ""))
DISK_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}\.(d64|g64|prg|t64|crt)$", re.I)
SID_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}\.sid$", re.I)
MAX_LINE = 160000                                   # one request line: a render with a 65 KB .sid in base64 is about 88 KB
RENDER_TIMEOUT = 300
cur = {"p": None, "disk": None, "since": None}
vice_lock = threading.Lock()                        # play / basic / stop / status: one at a time
render_lock = threading.Lock()                      # one render at a time


def alive():
    return cur["p"] is not None and cur["p"].poll() is None


def stop():
    if alive():
        try:
            os.killpg(cur["p"].pid, signal.SIGTERM)
            cur["p"].wait(5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(cur["p"].pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    cur.update(p=None, disk=None, since=None)


SCREEN_SOCK = "/tmp/.X11-unix/X99"                 # exists only while the remote screen of the viewer is on (1.12)


def launch(args, label):
    if not os.path.exists(SCREEN_SOCK):
        return {"ok": False, "error": "the remote screen is off: turn it on first (lab64 screen on, or the switch in the page)", "code": "screen-off"}
    stop()
    cur["p"] = subprocess.Popen(CMD + args, cwd=ROOT, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cur.update(disk=label, since=int(time.time()))
    time.sleep(0.5)                # a command that exits at once (disk refused, VICE not starting) already shows in the status
    return status() if alive() else {"ok": False, "error": "the command ended at once (exit %s)" % cur["p"].returncode}


def play(disk):
    if not CMD:
        return {"ok": False, "error": "C64_VIEW_PLAYER not defined (project lab64.env)"}
    if disk is None:
        return launch(["--bare"], None)
    if not isinstance(disk, str) or not DISK_RE.match(disk) or ".." in disk.split("/"):
        return {"ok": False, "error": "invalid disk"}
    real = os.path.realpath(os.path.join(OUT, disk))
    if not real.startswith(OUT + os.sep) or not os.path.isfile(real):
        return {"ok": False, "error": "disk not found in out/"}
    return launch([os.path.relpath(real, ROOT)], disk)


def status():
    if not alive():
        cur.update(p=None, disk=None, since=None)
    return {"ok": True, "running": alive(), "disk": cur["disk"], "bare": alive() and cur["disk"] is None, "since": cur["since"]}


def render(req):
    """the render command (see the module doc): every field is checked here, whatever the viewer already checked"""
    import sidrender                                # next to this file
    bad = lambda m: {"ok": False, "error": m, "code": "invalid"}
    src, b64, params = req.get("src"), req.get("sid_b64"), req.get("params")
    if (src is None) == (b64 is None):
        return bad("give src or sid_b64 (one of them)")
    if params is not None and not isinstance(params, dict):
        return bad("params must be an object")
    if src is not None:
        if not isinstance(src, str) or not SID_RE.match(src) or src.startswith("/") or ".." in src.split("/"):
            return bad("invalid src")
        real = os.path.realpath(os.path.join(OUT, src))
        if not real.startswith(OUT + os.sep) or not os.path.isfile(real):
            return bad("file not found in out/")
        if os.path.getsize(real) > sidrender.MAX_SID:
            return bad("the .sid is too large")
        with open(real, "rb") as f:
            data = f.read(sidrender.MAX_SID + 1)
    else:
        if not isinstance(b64, str) or len(b64) > (sidrender.MAX_SID + 2) // 3 * 4 + 4:
            return bad("the .sid is too large or not a string")
        try:
            data = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            return bad("sid_b64 is not valid base64")
    if not render_lock.acquire(blocking=False):
        return {"ok": False, "error": "a render is already running: try again in a moment", "code": "busy"}
    try:
        r = sidrender.render(data, params, root=ROOT, timeout=RENDER_TIMEOUT)
    except sidrender.SidRenderError as e:
        return bad(str(e))
    except RuntimeError as e:
        return {"ok": False, "error": str(e), "code": "failed"}
    finally:
        render_lock.release()
    t = r["tune"]
    return {"ok": True, "file": "cache/sidrender/" + r["file"], "seconds": r["seconds"], "took": r["took"], "cached": r["cached"],
            "params": r["params"], "rate": r["rate"], "channels": r["channels"], "bits": r["bits"],
            "tune": {k: t[k] for k in ("name", "author", "released", "songs", "start", "clock", "model")}}


def handle(line):
    try:
        req = json.loads(line)
        c = req.get("cmd")
    except (ValueError, AttributeError):
        return {"ok": False, "error": "invalid request", "code": "invalid"}
    if c == "render":
        return render(req)
    with vice_lock:
        if c == "status":
            return status()
        if c == "play":
            return play(req.get("disk") or "")
        if c == "basic":
            return play(None)
        if c == "stop":
            stop()
            return status()
    return {"ok": False, "error": "unknown command", "code": "invalid"}


def serve(c):
    """one connection: one request line, one answer line"""
    with c:
        c.settimeout(5)
        try:
            data = b""
            while b"\n" not in data and len(data) <= MAX_LINE:
                b = c.recv(65536)
                if not b:
                    break
                data += b
            if len(data) > MAX_LINE:
                ans = {"ok": False, "error": "request too large", "code": "invalid"}
            else:
                ans = handle(data.decode("utf-8", "replace").strip())
            c.settimeout(30)
            c.sendall((json.dumps(ans) + "\n").encode())
        except OSError:
            pass


def main():
    if os.path.exists(SOCK):
        os.remove(SOCK)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(SOCK)
    os.chmod(SOCK, 0o666)          # the viewer server runs as another user; only our containers mount the lab64-x11 volume
    s.listen(4)
    signal.signal(signal.SIGTERM, lambda *_: (stop(), sys.exit(0)))
    print("player ready: %s (%s)" % (SOCK, " ".join(CMD) or "no command"), flush=True)
    while True:
        c, _ = s.accept()
        threading.Thread(target=serve, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
