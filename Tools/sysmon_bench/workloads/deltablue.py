"""DeltaBlue constraint solver (calls, branches, data structures)."""

from . import _deltablue_impl as impl

NAME = "deltablue"
_N = 1500


def run():
    impl.delta_blue(_N)
    return _N
