"""Real-world large coverage set: import pygments and highlight source.

Requires third_party/ to be populated first:
    python Tools/sysmon_bench/fetch_third_party.py

Importing pygments plus lexing a large Python source exercises coverage
warmup over a real codebase (hundreds of code objects, thousands of
lines executed once), and steady-state reps then run over the same
already-disabled code.
"""

import os
import sys

NAME = "pygments_hl"

_HERE = os.path.dirname(os.path.abspath(__file__))
_THIRD_PARTY = os.path.join(os.path.dirname(_HERE), "third_party")

_TEXT = None
_lex = None
_lexer = None
_formatter = None


def setup():
    global _TEXT
    pkgdirs = [
        os.path.join(_THIRD_PARTY, d)
        for d in sorted(os.listdir(_THIRD_PARTY))
        if d.startswith("pygments-")
    ]
    if not pkgdirs:
        raise RuntimeError("run fetch_third_party.py first")
    sys.path.insert(0, pkgdirs[-1])
    # A large, diverse chunk of Python source to highlight.
    src_candidates = [
        os.path.join(pkgdirs[-1], "pygments", "lexers", "python.py"),
        os.path.join(pkgdirs[-1], "pygments", "lexer.py"),
    ]
    chunks = []
    for path in src_candidates:
        with open(path, encoding="utf-8") as f:
            chunks.append(f.read())
    _TEXT = "\n".join(chunks)


def run():
    # Imports happen on the first rep, under monitoring, like real usage.
    global _lex, _lexer, _formatter
    if _lex is None:
        from pygments import highlight
        from pygments.lexers import PythonLexer
        from pygments.formatters import HtmlFormatter

        _lex = highlight
        _lexer = PythonLexer()
        _formatter = HtmlFormatter()
    out = _lex(_TEXT, _lexer, _formatter)
    return len(out)
