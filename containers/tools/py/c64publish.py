"""Release publishing of a C64 project: out/releases/v<version>/ with manifest.json for the Lab64 viewer. Copyright (c) 2026 - Simone Caporale

One folder per version, the latest N kept (retention by publication date), out/releases/latest = relative link to the newest.
The manifest is the contract with the viewer page (docs/manifest.md).

From the host:  lab64 publish [--version V] [--keep N] [--release] [--extra GROUP:SRC[:DST]] ...   (in lab64-tools)
  without options it publishes what the default build makes: out/work/disk.d64 -> <name>_v<V>.d64 (group disk), the PDFs of
  out/work/manual/ (manual), out/work/memory-map/ (memory-map, with its metrics), the test report if it is newer than the disk
  (tests). Version: --version, C64_VERSION of lab64.env, else "0". Name: C64_NAME. Keep: --keep, C64_KEEP_VERSIONS, else 5.
From a project script (its own groups and measures):
    from c64publish import publish, metric
    publish("1.2", groups={"disk": [("out/work/disk.d64", "game_v1.2.d64")], "music": [("out/work/sid", "music_v1.2")]},
            labels={"disk": "1541 disk", "music": "Music (.sid)"}, kinds={"music_v1.2": "sid"},
            tests="out/work/test_report.json", metrics=[metric("ram_free", "Free RAM", 1234, "B", "up")])

Rules:
- Folders merge: publishing the same version again replaces only the groups given in this call and keeps the others (e.g. the
  manual of an earlier build of the same version). A different identity (source_hash) for the same version empties the folder.
- Every file in the manifest: group, type (file / dir), number of files, bytes, SHA-256 (for a folder: of the sorted list of its
  files with their SHA-256), produced (UTC). Only folders with a manifest.json are ever deleted by the retention.
- Destinations are relative paths inside the version folder (an absolute path or a "../" stops the publishing before anything
  is removed).
- C64_PUBLISH_SID_RENDER=1 (lab64.env, default off): every .sid published with kind "sid" (a file, or the .sid files of a folder) also
  gets a 192 kbit/s MP3 of each subtune next to it, rendered with sidplayfp and the default parameters of containers/tools/py/sidrender.py; SID
  Studio plays it for release tunes while its settings are the defaults. Slow (see docs/sid-rendering.md): hence off by default.
- The first .d64 of the "disk" group (or disk_stats=) gives stats.disk (directory and free blocks)."""
import datetime, glob, hashlib, json, os, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "common", "py"))   # psid, d64, lab64env
import d64  # noqa: E402  (containers/common/py/d64.py)
from lab64env import setting as _setting  # noqa: E402  (containers/common/py/lab64env.py)

MANIFEST = "manifest.json"


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def files_of(path):
    """all the files under path (or path itself if it is a file)"""
    if os.path.isfile(path):
        yield path
    else:
        for d, _, fs in os.walk(path):
            for f in sorted(fs):
                yield os.path.join(d, f)


def tree_sha256(path):
    """fingerprint of a folder: SHA-256 of the sorted list (relative path, SHA-256 of the file)"""
    h = hashlib.sha256()
    for f in sorted(files_of(path)):
        h.update(("%s %s\n" % (os.path.relpath(f, path), sha256(f))).encode())
    return h.hexdigest()


def remove(p):
    if os.path.isdir(p) and not os.path.islink(p):
        shutil.rmtree(p)
    elif os.path.lexists(p):
        os.remove(p)


def metric(mid, label, value, unit="", better=None, hint=""):
    """a project measure in the viewer format: better = "up" (higher is better), "down" or None"""
    return {"id": mid, "label": label, "value": value, "unit": unit, "better": better, "hint": hint}


def render_sids(path):
    """C64_PUBLISH_SID_RENDER=1: renders every subtune of the .sid file (or of the .sid files of a folder) with the default
    parameters of containers/tools/py/sidrender.py (sidplayfp, reSIDfp, 3:00) and writes it as a 192 kbit/s MP3 next to the .sid (sidrender.mp3_name:
    <stem>.mp3, or <stem>-<n>.mp3 when the file has several subtunes). Returns the MP3 paths. A tune that cannot be rendered is
    reported and skipped: it never stops the publishing."""
    import sidrender, psid
    sids = [path] if os.path.isfile(path) else sorted(os.path.join(path, f) for f in os.listdir(path) if f.lower().endswith(".sid"))
    out, audio, took, t0 = [], 0.0, 0.0, time.monotonic()
    for s in sids:
        try:
            with open(s, "rb") as f:
                data = f.read(sidrender.MAX_SID + 1)
            tune = psid.info(data)
            for n in range(1, tune["songs"] + 1):
                r = sidrender.render(data, {"subtune": n})
                mp3 = sidrender.mp3_name(s, n, tune["songs"])
                sidrender.to_mp3(r["path"], mp3, tune["name"], tune["author"])
                out.append(mp3); audio += r["seconds"]; took += r["took"]
        except (ValueError, RuntimeError, OSError) as e:
            print("publish: sid render: %s: %s" % (os.path.basename(s), e), file=sys.stderr)
    if out:
        print("publish: %d MP3 rendered from %d .sid files: %.0f s of audio, %.1f s of emulation (%.0fx real time), %.1f s in all" % (
            len(out), len(sids), audio, took, audio / took if took else 0, time.monotonic() - t0))
    return out


def d64_info(path):
    """free blocks and directory of a .d64 (containers/common/py/d64.py) in the viewer format"""
    return d64.summary(d64.read(path))


def git_info(root, paths=()):
    """commit, subject; dirty = uncommitted changes (in paths, or anywhere)"""
    def g(*a):
        return subprocess.run(["git", "-C", root] + list(a), capture_output=True, text=True, timeout=20).stdout.strip()
    try:
        if not g("rev-parse", "--git-dir"):
            return {}
        return {"commit": g("rev-parse", "--short", "HEAD"), "subject": g("log", "-1", "--format=%s"),
                "dirty": bool(g("status", "--porcelain", "--", *paths))}
    except Exception:
        return {}


def git_branch(root):
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True,
                              timeout=20).stdout.strip() or None
    except Exception:
        return None


def inside(vdir, dst):
    """the destination dst as a path inside the version folder; stops on an absolute path or one that leaves it (../)"""
    n = os.path.normpath(dst or "")
    if not dst or os.path.isabs(dst) or n == "." or n == ".." or n.startswith(".." + os.sep) or n == MANIFEST:
        sys.exit("publish: destination '%s' must be a relative path inside the version folder" % dst)
    return os.path.join(vdir, n)


def publish(version, groups, labels=None, kinds=None, root=".", keep=5, release=False, tests=None, metrics=None, info=None,
            disk_stats=None, build_seconds=None, branch=None, source_hash=None, extra=None, expected=None, git_paths=()):
    """publishes the groups {group: [(source, destination relative to the version folder)]}; returns the version folder.
    tests: path of test_report.json (the results go into the manifest), metrics / info: project measures (replaced when given),
    extra: more manifest fields (dict), expected: groups shown as missing when not published (default: labels)."""
    if keep < 1:
        sys.exit("publish: keep must be >= 1")
    if not version or "/" in version or "\\" in version or version.strip(".") == "":
        sys.exit("publish: version '%s' is not a folder name" % version)
    rel = os.path.join(root, "out", "releases")
    vdir = os.path.join(rel, "v" + version)
    os.makedirs(vdir, exist_ok=True)
    mpath = os.path.join(vdir, MANIFEST)
    man = json.load(open(mpath)) if os.path.isfile(mpath) else {"files": {}}
    if source_hash is not None and man.get("source_hash") not in (None, source_hash):
        for f in list(man["files"]):                 # same version, other sources: the earlier files are no longer valid
            remove(inside(vdir, f))
            for r in man["files"][f].get("renders", []):
                remove(inside(vdir, r))
        man = {"files": {}}
    man.setdefault("built_at", now())
    stamp = now()
    for g, items in groups.items():                   # every destination checked before anything is removed
        for _, dst in items:
            inside(vdir, dst)
    for g, items in groups.items():
        for f in [f for f, m in man["files"].items() if m.get("group") == g]:
            remove(inside(vdir, f))
            for r in man["files"][f].get("renders", []):      # MP3 renders written next to a single .sid file
                remove(inside(vdir, r))
            del man["files"][f]
        for src, dst in items:
            s = os.path.join(root, src)
            if not os.path.exists(s):
                sys.exit("publish: %s missing (group '%s')" % (src, g))
            d = inside(vdir, dst)
            remove(d)
            if os.path.isdir(s):
                shutil.copytree(s, d)
            else:
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
            renders = render_sids(d) if (kinds or {}).get(dst) == "sid" and _setting("C64_PUBLISH_SID_RENDER", "0") == "1" else []
            fs = list(files_of(d))
            man["files"][dst] = {"group": g, "type": "dir" if os.path.isdir(d) else "file", "files": len(fs),
                                 "bytes": sum(os.path.getsize(f) for f in fs),
                                 "sha256": tree_sha256(d) if os.path.isdir(d) else sha256(d), "produced": stamp}
            if (kinds or {}).get(dst):
                man["files"][dst]["kind"] = kinds[dst]
            if renders and os.path.isfile(d):               # next to a single file: listed to be removed with it
                man["files"][dst]["renders"] = sorted(os.path.relpath(r, vdir) for r in renders)
    t = man.get("tests") or {"ran": False}
    if tests:
        r = json.load(open(os.path.join(root, tests)))
        res = [x["result"] for x in r["results"]]
        t = {"ran": True, "suites": r.get("suites"), "total": len(res), "pass": res.count("PASS"), "fail": res.count("FAIL"),
             "skip": res.count("SKIP"), "seconds": r.get("total_s"), "at": stamp}
    stats = man.get("stats") or {}
    if metrics is not None:
        stats["metrics"] = metrics
    if info is not None:
        stats["info"] = info
    dk = disk_stats or next((os.path.join(vdir, f) for f, m in sorted(man["files"].items())
                             if m.get("group") == "disk" and f.lower().endswith(".d64")), None)
    if dk and os.path.isfile(dk):
        stats["disk"] = d64_info(dk)
    if groups:
        stats["git"] = git_info(root, git_paths)
    if build_seconds is not None:
        stats["build_seconds"] = build_seconds
    if tests:
        stats["test_seconds"] = t.get("seconds")
    labels = dict(man.get("groups") or {}, **(labels or {}))
    man.update({"schema": 1, "groups": labels, "stats": stats, "version": version, "branch": branch or git_branch(root),
                "updated_at": stamp, "tests": t, "release": bool(man.get("release") or release),
                "missing": sorted(set(expected or labels) - {m["group"] for m in man["files"].values()})})
    if source_hash is not None:
        man["source_hash"] = source_hash
    man.update(extra or {})
    with open(mpath, "w") as f:
        json.dump(man, f, indent=1, sort_keys=True)
        f.write("\n")
    link = os.path.join(rel, "latest")                # relative link: it works wherever the folder is mounted
    remove(link)
    os.symlink("v" + version, link)
    found = []                                        # retention: the latest N by publication date, the new one always
    for n in os.listdir(rel):
        p = os.path.join(rel, n, MANIFEST)
        if os.path.isfile(p) and not os.path.islink(os.path.join(rel, n)):
            found.append((json.load(open(p)).get("updated_at", ""), n))
    found.sort(reverse=True)
    keepset = {n for _, n in found[:keep]} | {"v" + version}
    gone = [n for _, n in found if n not in keepset]
    for n in gone:
        shutil.rmtree(os.path.join(rel, n))
    tot = sum(os.path.getsize(f) for f in files_of(vdir))
    print("publish: out/releases/v%s (%d entries, %.1f MB; missing: %s)%s" % (
        version, len(man["files"]), tot / 1e6, ", ".join(man["missing"]) or "nothing",
        ("; removed by the retention (%d): %s" % (keep, " ".join(gone))) if gone else ""))
    return vdir


def setting(name, default=None):
    """a setting: environment, then lab64.env of the project (current folder)"""
    return _setting(name, default)


def main(argv):
    """the default publishing (lab64 publish)"""
    import argparse
    ap = argparse.ArgumentParser(prog="lab64 publish", description="publish the build into out/releases/v<version>/")
    ap.add_argument("--version", help="version (default C64_VERSION of lab64.env, else 0)")
    ap.add_argument("--keep", type=int, help="versions to keep (default C64_KEEP_VERSIONS, else 5)")
    ap.add_argument("--release", action="store_true", help="mark the version as a release")
    ap.add_argument("--extra", action="append", default=[], metavar="GROUP:SRC[:DST]",
                    help="one more file or folder (repeatable), e.g. music:out/work/sid:music")
    a = ap.parse_args(argv)
    v = a.version or setting("C64_VERSION", "0")
    name = setting("C64_NAME", "main")
    keep = a.keep or int(setting("C64_KEEP_VERSIONS", "5"))
    w = os.path.join("out", "work")
    groups, labels = {}, {"disk": "Disk", "manual": "Manual (PDF)", "memory-map": "Memory and disk map", "tests": "Test report"}
    disk = os.path.join(w, "disk.d64")
    if os.path.isfile(disk):
        groups["disk"] = [(disk, "%s_v%s.d64" % (name, v))]
    pdfs = sorted(glob.glob(os.path.join(w, "manual", "*.pdf")))
    if pdfs:
        groups["manual"] = [(p, "%s_v%s.pdf" % (os.path.splitext(os.path.basename(p))[0], v)) for p in pdfs]
    mm = os.path.join(w, "memory-map")
    metrics = None
    if os.path.isfile(os.path.join(mm, "index.html")):
        groups["memory-map"] = [(mm, "memory-map")]
        mj = os.path.join(mm, "memmap.json")
        metrics = json.load(open(mj)).get("metrics", []) if os.path.isfile(mj) else None
    tr = os.path.join(w, "test_report.json")
    tests = None
    if os.path.isfile(tr) and (not os.path.isfile(disk) or os.path.getmtime(tr) >= os.path.getmtime(disk)):
        groups["tests"] = [(tr, "test_report.json")] + ([(tr[:-4] + "txt", "test_report.txt")] if os.path.isfile(tr[:-4] + "txt") else [])
        tests = tr
    for e in a.extra:
        g, _, rest = e.partition(":")
        src, _, dst = rest.partition(":")
        groups.setdefault(g, []).append((src, dst or os.path.basename(src.rstrip("/"))))
        labels.setdefault(g, g)
    if not groups:
        sys.exit("publish: nothing to publish (no out/work/disk.d64: lab64 build first)")
    publish(v, groups, labels=labels, keep=keep, release=a.release, tests=tests, metrics=metrics)


if __name__ == "__main__":
    main(sys.argv[1:])
