"""Richards benchmark (OO-heavy, many calls/returns and branches)."""

from . import _richards_impl as impl

NAME = "richards"
_ITERATIONS = 2


def run():
    r = impl.Richards()
    ok = r.run(_ITERATIONS)
    assert ok
    return _ITERATIONS
