"""Warmup-path stress: many fresh code objects, each line executed once.

Each run() compiles and executes a synthetic module with many small
functions and calls every function once.  Because compile() produces
fresh code objects on every rep, every rep exercises the full coverage
warmup path: PY_START per code object, set_local_events / instrumentation
insertion, one LINE event per line, and the DISABLE/de-instrument path.

The compile() cost itself is identical across monitoring modes, so
overhead ratios remain meaningful.
"""

NAME = "codegen"

_NUM_FUNCS = 600
_SOURCE = None
_COMPILE_ONLY_NS = None


def setup():
    global _SOURCE
    parts = []
    for i in range(_NUM_FUNCS):
        parts.append(f"def f{i}(x):\n")
        # ~14 executable lines per function, with branches and a loop
        parts.append(
            "    total = 0\n"
            "    y = x + 1\n"
            "    z = y * 2\n"
            "    if z > x:\n"
            "        total += z\n"
            "    else:\n"
            "        total -= z\n"
            "    for k in range(3):\n"
            "        total += k\n"
            "        if total & 1:\n"
            "            total += 1\n"
            "    s = str(total)\n"
            "    total += len(s)\n"
            "    return total\n"
        )
    parts.append("RESULT = 0\n")
    for i in range(_NUM_FUNCS):
        parts.append(f"RESULT += f{i}({i})\n")
    _SOURCE = "".join(parts)


_counter = 0


def run():
    global _counter
    _counter += 1
    code = compile(_SOURCE, f"<bench_codegen_{_counter}>", "exec")
    ns = {}
    exec(code, ns)
    return ns["RESULT"]
