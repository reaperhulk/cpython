"""N-Queens solver (generators, loops)."""

from . import _nqueens_impl as impl

NAME = "nqueens"
_QUEENS = 8


def run():
    return len(list(impl.n_queens(_QUEENS)))
