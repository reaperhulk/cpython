"""Steady-state per-call residual: many calls to tiny traced functions.

After coverage warmup, PY_START is disabled and LINE events are disabled,
but coverage.py's line mode leaves PY_RETURN | PY_RESUME local events set
with no registered callback, so every return still goes through the
instrumentation call machinery.  This workload measures that residual.
"""

NAME = "calls"

_N = 150_000


def _leaf(x):
    return x + 1


def _mid(x):
    return _leaf(x) + _leaf(x + 1)


def run():
    total = 0
    for i in range(_N):
        total += _mid(i)
    return total
