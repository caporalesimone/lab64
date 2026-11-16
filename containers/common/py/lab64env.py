"""Reader of a project's lab64.env for the Lab64 Python code (15/11). Copyright (c) 2026 - Simone Caporale

lab64.env is a sh file (cli/lab64 sources it). This module reads the same assignments WITHOUT running anything:
    NAME="value"     NAME='value'     NAME=value     export NAME=...      (a "# comment" may follow, after a space)
Double-quoted values keep their text as it is, with the sh escapes \\" \\\\ \\$ \\` undone; $VARIABLES and $( ) are NOT expanded
(Lab64 settings are plain values). Lines that are not simple assignments (commands, if, multi-line values) are ignored.

    from lab64env import setting, values
    setting("C64_NAME", "main")          # environment first (when set and not empty), then lab64.env, then the default
    values()                             # every assignment of lab64.env as a dict (the file only)
An empty value counts as not set (the default is returned). Project folder: root=, else C64_PROJECT, else the current folder."""
import os, re

_ASSIGN = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_cache = {}


def _value(s):
    """the value at the start of s (sh word: quoted parts and plain characters); None if the rest of the line is not a comment"""
    out, i, n = [], 0, len(s)
    while i < n and not s[i].isspace():
        c = s[i]
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                return None                                   # value on more lines: not supported
            out.append(s[i + 1:j]); i = j + 1
        elif c == '"':
            i += 1
            while i < n and s[i] != '"':
                if s[i] == "\\" and i + 1 < n and s[i + 1] in '"\\$`':
                    i += 1
                out.append(s[i]); i += 1
            if i >= n:
                return None
            i += 1
        elif c == "\\" and i + 1 < n:
            out.append(s[i + 1]); i += 2
        else:
            out.append(c); i += 1
    rest = s[i:].strip()
    if rest and not rest.startswith("#"):
        return None                                           # "A=b command": not a setting
    return "".join(out)


def parse(text):
    """{name: value} of the simple assignments in a lab64.env text (the last one wins, as in sh)"""
    d = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _ASSIGN.match(line)
        if m:
            v = _value(m.group(2))
            if v is not None:
                d[m.group(1)] = v
    return d


def project(root=None):
    return os.path.abspath(root or os.environ.get("C64_PROJECT") or os.getcwd())


def values(root=None):
    """every assignment of <project>/lab64.env ({} without the file); read again when the file changes"""
    p = os.path.join(project(root), "lab64.env")
    try:
        st = os.stat(p)
    except OSError:
        return {}
    key = (p, st.st_mtime_ns, st.st_size)
    if key not in _cache:
        with open(p, encoding="utf-8", errors="replace") as f:
            _cache[key] = parse(f.read())
    return _cache[key]


def setting(name, default=None, root=None, env=True):
    """a project setting: the environment (if env and set, not empty), then lab64.env, then default"""
    if env and os.environ.get(name):
        return os.environ[name]
    v = values(root).get(name)
    return v if v else default
