"""Exception-flavoured control flow."""


class AppError(Exception):
    pass


def might_fail(i):
    if i % 5 == 0:
        raise AppError(i)
    if i % 11 == 0:
        raise ValueError(i)
    return i


def guarded(i):
    try:
        return might_fail(i) + 1
    except AppError:
        return 0
    except ValueError:
        return -1
    finally:
        if i % 1000 == 0:
            pass


def lookup_chain(d, keys):
    total = 0
    for key in keys:
        try:
            total += d[key]
        except KeyError:
            total -= 1
    return total


def setup():
    pass


def run():
    checksum = 0
    for i in range(500_000):
        checksum += guarded(i)
    d = {i: i for i in range(0, 1000, 3)}
    checksum += lookup_chain(d, list(range(2000)) * 120)
    return checksum
