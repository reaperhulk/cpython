"""Tight numeric and branchy loops.

Represents long-running loop-heavy code (simulations, data crunching).
With one-shot (DISABLE-based) coverage, overhead here should approach zero
after the first pass through each line/branch.
"""


def branchy_sum(n):
    total = 0.0
    for i in range(n):
        if i & 1:
            total += i * 0.5
        else:
            total -= i * 0.25
        if i % 7 == 0:
            total *= 1.0001
        elif i % 11 == 0:
            total *= 0.9999
    return total


def collatz_steps(limit):
    steps = 0
    for start in range(1, limit):
        n = start
        while n != 1:
            if n & 1:
                n = 3 * n + 1
            else:
                n >>= 2 if n % 4 == 0 else 1
            steps += 1
    return steps


def matmul(size):
    a = [[float(i * size + j) for j in range(size)] for i in range(size)]
    b = [[float(j * size + i) for j in range(size)] for i in range(size)]
    result = [[0.0] * size for _ in range(size)]
    for i in range(size):
        row_a = a[i]
        row_r = result[i]
        for k in range(size):
            aik = row_a[k]
            row_b = b[k]
            for j in range(size):
                row_r[j] += aik * row_b[j]
    return result[size // 2][size // 2]


def string_churn(n):
    parts = []
    for i in range(n):
        if i % 3 == 0:
            parts.append(f"a{i}")
        elif i % 3 == 1:
            parts.append(f"bb{i}")
        else:
            parts.append(f"ccc{i}")
    text = ",".join(parts)
    count = 0
    for chunk in text.split(","):
        if chunk.startswith("a"):
            count += 1
        elif chunk.endswith("9"):
            count += 2
    return count


def setup():
    pass


def run():
    checksum = 0.0
    checksum += branchy_sum(1_200_000)
    checksum += collatz_steps(12_000)
    checksum += matmul(96)
    checksum += string_churn(300_000)
    return checksum
