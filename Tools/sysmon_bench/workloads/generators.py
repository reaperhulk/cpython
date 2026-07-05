"""Steady-state generator residual: PY_RESUME/PY_YIELD instrumented sites.

Like calls.py but for generators: coverage line mode leaves PY_RESUME
enabled with no callback, so every generator resume pays the
instrumentation dispatch.
"""

NAME = "generators"

_N = 600_000


def _gen(n):
    for i in range(n):
        yield i


def run():
    total = 0
    for _ in range(_N // 100):
        for v in _gen(100):
            total += v
    return total
