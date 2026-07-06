"""Test-suite-like breadth workload.

Real-world coverage runs are usually test suites: thousands of distinct
functions across many modules, most of which execute only a handful of
times.  With one-shot coverage the cost is dominated by first-execution
events (instrumentation, callback dispatch, de-instrumentation), which this
workload maximises relative to steady-state loop time.

Modules are generated as real files on disk (so real coverage.py can parse
them for branch analysis) and imported *while tracing is active*, as they
would be in a test run.
"""

import os
import shutil
import sys
import tempfile

NUM_MODULES = 50
FUNCS_PER_MODULE = 40
CLASSES_PER_MODULE = 5

_dir = None
_modules = None

FUNC_TEMPLATE = '''
def func_{i}(x):
    total = x
    for j in range({loop}):
        if j & 1:
            total += j
        elif j % 3 == 0:
            total -= 1
        else:
            total ^= j
    if x % 7 == {rem}:
        total += 100
    elif x % 5 == 1:
        total += 50
    else:
        total += 1
    try:
        if total % 13 == 0:
            raise ValueError(total)
        total += 2
    except ValueError:
        total -= 3
    while total > 10_000:
        total //= 3
    return total
'''

CLASS_TEMPLATE = '''
class Klass_{i}:
    def __init__(self, seed):
        self.seed = seed
        if seed & 1:
            self.mode = "odd"
        else:
            self.mode = "even"

    def work(self, n):
        acc = self.seed
        for k in range(n):
            if self.mode == "odd":
                acc += k
            else:
                acc -= k
        return acc

    def finish(self):
        if self.seed % 3 == 0:
            return self.seed * 2
        return self.seed + 1
'''


def _module_source(mod_index):
    parts = ['"""Generated module for the breadth workload."""\n']
    for i in range(FUNCS_PER_MODULE):
        parts.append(
            FUNC_TEMPLATE.format(i=i, loop=20 + (i % 30), rem=i % 7)
        )
    for i in range(CLASSES_PER_MODULE):
        parts.append(CLASS_TEMPLATE.format(i=i))
    return "".join(parts)


def setup():
    global _dir
    _dir = tempfile.mkdtemp(prefix="covbench_breadth_")
    for m in range(NUM_MODULES):
        path = os.path.join(_dir, f"breadth_mod_{m}.py")
        with open(path, "w") as f:
            f.write(_module_source(m))
    # Precompile to .pyc (untimed), as in a normal dev/CI environment with a
    # warm bytecode cache; the timed import still executes module code under
    # tracing but does not pay the parser.
    import compileall

    compileall.compile_dir(_dir, quiet=2)
    sys.path.insert(0, _dir)
    return _dir


def trace_prefix():
    return _dir


def _import_all():
    global _modules
    import importlib

    _modules = []
    for m in range(NUM_MODULES):
        _modules.append(importlib.import_module(f"breadth_mod_{m}"))


def run():
    if _modules is None:
        _import_all()
    checksum = 0
    for mod_index, mod in enumerate(_modules):
        for i in range(FUNCS_PER_MODULE):
            fn = getattr(mod, f"func_{i}")
            # Most functions run only a few times, like tests do.
            calls = 1 + (mod_index * 7 + i * 3) % 13
            for c in range(calls):
                checksum += fn(c + i)
        for i in range(CLASSES_PER_MODULE):
            cls = getattr(mod, f"Klass_{i}")
            for seed in range(4):
                obj = cls(seed + i)
                checksum += obj.work(30)
                checksum += obj.finish()
    return checksum % 1_000_000_007


def teardown():
    if _dir and os.path.isdir(_dir):
        shutil.rmtree(_dir, ignore_errors=True)
