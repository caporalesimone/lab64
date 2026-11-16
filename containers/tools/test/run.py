#!/usr/bin/env python3
"""Test engine of Lab64 (10/11). Copyright (c) 2026 - Simone Caporale

Three suites in three folders of the project tests/ (C64_TESTS, default <current folder>/tests):
  smoke/       a few fast tests on the happy path of the main features
  sanity/      the tests of the feature in development; when the feature is done they move to smoke or regression
  regression/  all the corner cases, as close as possible to the real program (slow ones too)
In every suite one folder per feature; its cases.py registers the tests with containers/tools/py/c64test.py (ID, description); the other files of
the folder are scripts and data of that feature. The project tests/ folder is on sys.path (its lib/ package is importable).
Usage:  lab64 test [smoke|sanity|regression|all ...] [-k ID|prefix ...] [--list] [--md]     (host or lab64-tools, from the project)
  no suite: smoke, or every suite with -k. Exit codes: 0 all passed, 1 a failure or a time cap, 2 usage error (unknown argument
  or suite, duplicate IDs) or NO test selected (the reports are not touched).
Duration caps (optional, project lab64.env or environment): C64_TEST_CAPS="test=10 smoke=20 smoke+sanity=35" (seconds): one
smoke / sanity test, the smoke suite alone, smoke + sanity; over a cap: exit 1 with "TIME CAP" lines. TEST_CAP_SCALE scales them.
Report: on screen and in out/work/test_report.txt / out/work/test_report.json (ID, suite, result, time, reason).
Live status (for the viewer page): out/tmp/tests.json, rewritten after every test (state running, then ok / fail, or aborted
after Ctrl-C or an error of the engine)."""
import glob, importlib.util, json, os, re, sys, time, traceback

HERE = os.environ.get("C64_TESTS") or os.path.join(os.getcwd(), "tests")     # the project tests/ folder
PROJ = os.path.dirname(os.path.abspath(HERE))
_T = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))                  # containers/tools
sys.path[:0] = [HERE, os.path.join(_T, "py"), os.path.join(os.path.dirname(_T), "common", "py")]
os.environ.setdefault("C64_ROOT", PROJ)
import c64test as R  # noqa: E402
from lab64env import setting  # noqa: E402  (containers/common/py/lab64env.py: the one reader of lab64.env)

SUITES = ["smoke", "sanity", "regression"]
def caps():
    """duration caps of the project: C64_TEST_CAPS in the environment or in the project lab64.env; {} = no cap"""
    v = setting("C64_TEST_CAPS", "", root=PROJ)
    try:
        return {k: float(x) for k, x in (i.split("=") for i in v.split())}
    except ValueError:
        sys.exit("C64_TEST_CAPS: '%s' is not a list of name=seconds (e.g. test=10 smoke=20 smoke+sanity=35)" % v)


CAPS = caps()


def load(suite):
    mods = []
    for f in sorted(glob.glob(os.path.join(HERE, suite, "**", "cases.py"), recursive=True)):
        name = "%s.%s" % (suite, os.path.relpath(f, os.path.join(HERE, suite))[:-3].replace(os.sep, "."))
        n0 = len(R.REG)
        spec = importlib.util.spec_from_file_location(name, f)
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
        for t in R.REG[n0:]:
            t["suite"] = suite; t["module"] = name
        mods.append(m)
    return mods


def lock():
    """one test run at a time: VICE's remote monitor port (6510) is shared, two runs would talk to each other's VICE"""
    import fcntl
    os.makedirs(os.path.join(PROJ, "out", "tmp"), exist_ok=True)
    f = open(os.path.join(PROJ, "out", "tmp", ".test.lock"), "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another test run is active: waiting for it"); fcntl.flock(f, fcntl.LOCK_EX)
    return f


LIVE = os.path.join(PROJ, "out", "tmp", "tests.json")
ST = {}


def live(**kw):
    """live status for the viewer page: atomic rewrite of out/tmp/tests.json (never fails the run)"""
    ST.update(kw, updated=round(time.time(), 1))
    try:
        with open(LIVE + ".tmp", "w") as f:
            json.dump(ST, f)
        os.replace(LIVE + ".tmp", LIVE)
    except OSError:
        pass


def check_caps(res, suites, filtered):
    """duration caps: one smoke / sanity test, the smoke suite, smoke + sanity (only for runs without -k; the order of the suites
    on the command line does not matter)"""
    sc = float(os.environ.get("TEST_CAP_SCALE", "1"))
    err = []
    for r in res:
        if "test" in CAPS and r["suite"] in ("smoke", "sanity") and r["time"] > CAPS["test"] * sc:
            err.append("%s took %.1f s (cap %.1f s per test)" % (r["id"], r["time"], CAPS["test"] * sc))
    if filtered: return err
    tm = lambda *s: sum(r["time"] for r in res if r["suite"] in s)
    sel = set(suites)
    if sel == {"smoke"} and "smoke" in CAPS and tm("smoke") > CAPS["smoke"] * sc:
        err.append("smoke %.1f s (cap %.1f s)" % (tm("smoke"), CAPS["smoke"] * sc))
    if sel == {"smoke", "sanity"} and "smoke+sanity" in CAPS and tm("smoke", "sanity") > CAPS["smoke+sanity"] * sc:
        err.append("smoke + sanity %.1f s (cap %.1f s)" % (tm("smoke", "sanity"), CAPS["smoke+sanity"] * sc))
    return err


def usage(msg):
    print("lab64 test: %s\nusage: lab64 test [smoke|sanity|regression|all ...] [-k ID|prefix ...] [--list] [--md]" % msg,
          file=sys.stderr)
    sys.exit(2)


def parse(args):
    """(suites, keys, flags); exit 2 on an unknown argument or suite"""
    suites, keys, flags, i = [], [], set(), 0
    while i < len(args):
        a = args[i]
        if a == "-k":
            if i + 1 >= len(args) or args[i + 1].startswith("-"):
                usage("-k needs an ID or a prefix")
            keys.append(args[i + 1].upper()); i += 2; continue
        if a in ("--list", "--md"):
            flags.add(a)
        elif a in SUITES or a == "all":
            suites.append(a)
        else:
            usage("unknown %s '%s'" % ("option" if a.startswith("-") else "suite", a))
        i += 1
    if "all" in suites or (keys and not suites):        # -k without a suite looks in every suite
        suites = list(SUITES)
    suites = [s for s in SUITES if s in suites] if suites else ["smoke"]
    return suites, keys, flags


def main():
    suites, keys, flags = parse(sys.argv[1:])
    args = flags
    mods = {}
    for s in suites:
        for m in load(s): mods[m.__name__] = m
    tests = [t for t in R.REG if not keys or any(t["id"] == k or t["id"].startswith(k) for k in keys)]
    ids = [t["id"] for t in R.REG]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        print("duplicate IDs: " + ", ".join(dup), file=sys.stderr); sys.exit(2)
    if not tests:                                   # a filter or a suite that selects nothing is not a green run
        print("lab64 test: no test selected (suites: %s%s); the reports are not changed" % (
            "+".join(suites), "; -k " + " ".join(keys) if keys else ""), file=sys.stderr)
        sys.exit(2)
    if "--list" in args:
        for t in tests: print("%-14s %-10s %s" % (t["id"], t["suite"], t["desc"]))
        return
    if "--md" in args:                              # the list as Markdown, one table per suite
        for su in SUITES:
            tl = [t for t in tests if t["suite"] == su]
            if not tl: continue
            print("### %s (%d)\n\n| ID | Test |\n|---|---|" % (su, len(tl)))
            for t in tl: print("| `%s` | %s |" % (t["id"], t["desc"]))
            print()
        return
    _lk = lock()  # noqa: F841  (only real runs: listing needs no VICE, no lock)
    res, t_all = [], time.time()
    live(state="running", suites=suites, filter=keys, total=len(tests), started=round(t_all, 1), current=None, results=res)
    try:
        run(tests, mods, res)
    except BaseException as e:                      # Ctrl-C, or an error of the engine: the viewer must not wait for ever
        live(state="aborted", current=None, seconds=round(time.time() - t_all, 1),
             error="interrupted" if isinstance(e, KeyboardInterrupt) else "%s: %s" % (type(e).__name__, e))
        if isinstance(e, KeyboardInterrupt):
            print("\nlab64 test: interrupted", file=sys.stderr); sys.exit(130)
        raise
    finish(res, suites, keys, t_all)


def run(tests, mods, res):
    """runs the selected tests module by module (setup, tests, teardown), appending the results to res"""
    by_mod = {}
    for t in tests: by_mod.setdefault(t["module"], []).append(t)
    for mname, tl in by_mod.items():
        m, ctx = mods[mname], {}
        os.environ["C64_MEMPROBE_TAG"] = re.sub(r"\.cases$", "", mname)   # memory probe (C64_MEMPROBE=1): scenario name of the RAM dumps
        chain = getattr(m, "CHAIN", False)
        broken = None
        t0 = time.time()
        try:
            if hasattr(m, "setup"): m.setup(ctx)
            setup_err = setup_skip = None
        except R.Skip as e:                         # (14/11) a setup that cannot run (e.g. no vc64web daemon): SKIP, not FAIL
            setup_err, setup_skip = None, str(e)
        except Exception as e:
            setup_skip = None
            setup_err = "setup: %s" % (e,)
            if os.environ.get("TESTDEBUG"): traceback.print_exc()
        t_setup = time.time() - t0
        for i, t in enumerate(tl):
            r = dict(id=t["id"], suite=t["suite"], desc=t["desc"], module=mname)
            live(current=dict(id=t["id"], suite=t["suite"], desc=t["desc"], since=round(time.time(), 1)))
            t0 = time.time()
            if setup_skip:
                r.update(result="SKIP", reason="setup: " + setup_skip)
            elif setup_err:
                r.update(result="FAIL", reason=setup_err)
            elif broken:
                r.update(result="SKIP", reason="after the failure of %s" % broken)
            else:
                try:
                    t["fn"](ctx); r.update(result="PASS", reason="")
                except R.Skip as e:
                    r.update(result="SKIP", reason=str(e))
                except AssertionError as e:
                    r.update(result="FAIL", reason=str(e))
                except Exception as e:
                    r.update(result="FAIL", reason="%s: %s" % (type(e).__name__, e))
                    if os.environ.get("TESTDEBUG"): traceback.print_exc()
                if r["result"] == "FAIL" and chain: broken = t["id"]
            r["time"] = round(time.time() - t0 + (t_setup if i == 0 else 0), 2)
            res.append(r)
            live(results=res)
            print("  %-4s %-14s %6.2f s  %s%s" % (r["result"], r["id"], r["time"], r["desc"],
                                                 ("  -> " + r["reason"]) if r["reason"] else ""), flush=True)
        try:
            if hasattr(m, "teardown"): m.teardown(ctx)
        except Exception:
            pass


def finish(res, suites, keys, t_all):
    """summary, time caps, reports, live status; exit 0 / 1"""
    tot = time.time() - t_all
    cap_err = check_caps(res, suites, filtered=bool(keys))
    n = {k: sum(1 for r in res if r["result"] == k) for k in ("PASS", "FAIL", "SKIP")}
    summary = "%s: %d test, %d PASS, %d FAIL, %d SKIP, %.1f s" % ("+".join(suites), len(res), n["PASS"], n["FAIL"], n["SKIP"], tot)
    print(summary)
    for e in cap_err: print("TIME CAP: " + e)
    live(state="fail" if n["FAIL"] or cap_err else "ok", current=None, seconds=round(tot, 1), caps=cap_err)
    out = os.path.join(PROJ, "out", "work")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "test_report.txt"), "w") as f:
        f.write("%-14s %-10s %-5s %8s  %s\n" % ("ID", "SUITE", "RESULT", "TIME", "DESCRIPTION / REASON"))
        for r in res:
            f.write("%-14s %-10s %-5s %7.2fs  %s%s\n" % (r["id"], r["suite"], r["result"], r["time"], r["desc"],
                                                        ("\n%40s-> %s" % ("", r["reason"])) if r["reason"] else ""))
        f.write(summary + "\n")
    json.dump(dict(suites=suites, total_s=round(tot, 1), results=res), open(os.path.join(out, "test_report.json"), "w"), indent=1)
    sys.exit(1 if n["FAIL"] or cap_err else 0)


if __name__ == "__main__":
    main()
