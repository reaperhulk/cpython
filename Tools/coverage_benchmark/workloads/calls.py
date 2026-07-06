"""Call-heavy workload: millions of tiny function calls plus recursion.

Stresses per-call paths (RESUME, PY_START one-shot, return events).
"""


def add(a, b):
    return a + b


def mix(a, b):
    if a & 1:
        return add(a, b)
    return add(b, a) + 1


def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def apply_n(fn, n):
    total = 0
    for i in range(n):
        total += fn(i, i + 1)
    return total


def setup():
    pass


def run():
    checksum = 0
    checksum += apply_n(add, 1_500_000)
    checksum += apply_n(mix, 1_500_000)
    checksum += fib(25)
    return checksum
