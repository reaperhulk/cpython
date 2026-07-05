"""Steady-state stress: a hot loop executing few distinct lines many times.

With DISABLE-style coverage the first iteration disables everything and
the remaining cost should be ~zero.  With *_nodisable modes this measures
raw per-LINE-event (or per-BRANCH-event) dispatch cost.
"""

NAME = "hotloop"

_N = 200_000


def _work(n):
    total = 0
    for i in range(n):
        a = i & 7
        b = i >> 3
        if a > b:
            total += a
        else:
            total += b
        total ^= i
    return total


def run():
    return _work(_N)
