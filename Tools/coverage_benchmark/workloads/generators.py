"""Generator/iterator pipeline workload.

Generators are interesting under sys.monitoring because coverage.py
enables PY_RESUME (and PY_RETURN) local events on traced code; every
resumption of a generator re-enters the instrumented RESUME instruction.
"""


def naturals(n):
    i = 0
    while i < n:
        yield i
        i += 1


def evens(it):
    for value in it:
        if value % 2 == 0:
            yield value


def scaled(it, factor):
    for value in it:
        yield value * factor


def windowed_sum(it, size):
    window = []
    for value in it:
        window.append(value)
        if len(window) > size:
            window.pop(0)
        yield sum(window)


def pipeline(n):
    total = 0
    for value in windowed_sum(scaled(evens(naturals(n)), 3), 4):
        total += value
    return total


def gen_expr_chain(n):
    squares = (i * i for i in range(n))
    odds = (s for s in squares if s & 1)
    return sum(o % 977 for o in odds)


def setup():
    pass


def run():
    checksum = 0
    checksum += pipeline(400_000)
    checksum += gen_expr_chain(1_000_000)
    return checksum
