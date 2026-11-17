"""Test registry of Lab64 (10/11). Copyright (c) 2026 - Simone Caporale
Every test has an upper-case ID (AREA-NN, e.g. SHOP-01) and a short description.

    from c64test import test, check, Skip          (importable in the Lab64 containers)

    @test("SHOP-01", "buy: gold and pack")
    def shop_buy(ctx): check(cond, "failure reason")

A module (cases.py) may define setup(ctx) / teardown(ctx): they run once before the first and after the last of its
selected tests (e.g. one VICE session for all the game smoke tests). CHAIN = True in the module: the tests are a
sequence (happy path) and after a failure the following ones are skipped with the reason.
script(id, desc, argv): a test that runs an external program (exit 0 = pass). On a failure the reason is made of the output
lines that contain FAIL, error/Error/ERROR or a word of C64_TEST_REASON_WORDS (lab64.env or environment, space separated, e.g.
"WARNING ATTENZIONE" for a program that reports in another language); with no such line, the last lines of the output.
(1.13) the old "slow" argument of test() is gone: nothing read it (remove it from the calls)."""
import os, subprocess, sys, time  # noqa: F401  (time: kept, a project may rely on "from c64test import *")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "common", "py"))   # psid, d64, lab64env
from lab64env import setting  # noqa: E402  (containers/common/py/lab64env.py)

REG = []


class Skip(Exception):
    pass


class Fail(AssertionError):
    pass


def test(tid, desc):
    def deco(f):
        REG.append(dict(id=tid, desc=desc, fn=f, module=f.__module__))
        return f
    return deco


def check(cond, reason):
    if not cond:
        raise Fail(reason)


def script(tid, desc, argv, timeout=900, cwd=None):
    def run(ctx):
        t = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, cwd=cwd, text=True)
        if t.returncode != 0:
            out = [l.strip() for l in t.stdout.splitlines() if l.strip()]
            words = ["FAIL", "rror", "ERROR"] + setting("C64_TEST_REASON_WORDS", "").split()
            lines = [l for l in out if any(w in l for w in words)]
            msg = "; ".join((lines or out[-3:] or ["exit %d" % t.returncode])[-4:])
            raise Fail("".join(ch if ch.isprintable() else " " for ch in msg)[:400])
    run.__name__ = "script_" + tid.replace("-", "_")
    REG.append(dict(id=tid, desc=desc, fn=run, module=sys._getframe(1).f_globals["__name__"]))
