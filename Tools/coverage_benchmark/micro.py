"""Microbenchmarks: per-event / per-code-object cost model for
coverage-style sys.monitoring usage.

Measures, in isolation:

1. per-line one-shot cost      -- LINE event fired once then DISABLEd
2. per-branch one-shot cost    -- BRANCH_LEFT/RIGHT fired once then DISABLEd
3. per-event dispatch cost     -- LINE events that are never disabled
4. no-callback residual cost   -- local event enabled with no registered
                                  callback (what coverage.py does with
                                  PY_RESUME / PY_RETURN), per generator resume
5. instrumentation setup cost  -- set_local_events() on fresh code objects
6. PY_START scan cost          -- first call of a fresh, untraced code object
                                  while a global PY_START event is active
                                  (version-bump + RESUME instrumentation walk)

Run:  ./python Tools/coverage_benchmark/micro.py
"""

import sys
import time

monitoring = sys.monitoring
E = monitoring.events
TOOL = monitoring.COVERAGE_ID


def timeit(fn, *args):
    t0 = time.perf_counter()
    result = fn(*args)
    t1 = time.perf_counter()
    return t1 - t0, result


def make_flat_function(n_lines):
    """A function with n_lines simple statements, each on its own line."""
    body = "\n".join(f"    x{i} = {i}" for i in range(n_lines))
    src = f"def flat():\n{body}\n    return x0\n"
    ns = {}
    exec(compile(src, f"<flat{n_lines}>", "exec"), ns)
    return ns["flat"]


def make_branchy_function(n_branches):
    """A function with n_branches if/else pairs, both sides visited."""
    lines = ["def branchy(flip):", "    total = 0"]
    for i in range(n_branches):
        lines.append(f"    if (flip + {i}) % 2:")
        lines.append(f"        total += {i}")
        lines.append("    else:")
        lines.append("        total -= 1")
    lines.append("    return total")
    src = "\n".join(lines) + "\n"
    ns = {}
    exec(compile(src, f"<branchy{n_branches}>", "exec"), ns)
    return ns["branchy"]


def make_many_functions(count):
    src_lines = []
    for i in range(count):
        src_lines.append(f"def f{i}(x):")
        src_lines.append(f"    return x + {i}")
    ns = {}
    exec(compile("\n".join(src_lines) + "\n", "<many>", "exec"), ns)
    return [ns[f"f{i}"] for i in range(count)]


def noop_disable(*args):
    return monitoring.DISABLE


def noop_keep(*args):
    return None


def with_tool(fn):
    monitoring.use_tool_id(TOOL, "micro")
    try:
        return fn()
    finally:
        monitoring.set_events(TOOL, 0)
        monitoring.free_tool_id(TOOL)


def bench_one_shot_lines():
    """Cost of a one-shot LINE event (fire once, DISABLE, de-instrument)."""
    n = 4000
    reps = 5
    flat = make_flat_function(n)
    flat()  # warm/specialize uninstrumented

    base, _ = min(timeit(flat) for _ in range(5))

    def run():
        total = 0.0
        for _ in range(reps):
            monitoring.register_callback(TOOL, E.LINE, noop_disable)
            monitoring.set_local_events(TOOL, flat.__code__, E.LINE)
            monitoring.restart_events()
            t, _ = timeit(flat)
            total += t
        return total / reps

    cold = with_tool(run)
    per_line = (cold - base) / n
    print(f"one-shot LINE:            {per_line * 1e9:8.1f} ns/event "
          f"(cold {cold * 1e3:.2f} ms vs base {base * 1e3:.2f} ms, {n} lines)")
    return per_line


def bench_one_shot_branches():
    n = 2000
    reps = 5
    branchy = make_branchy_function(n)
    branchy(0), branchy(1)

    base, _ = min(timeit(lambda: (branchy(0), branchy(1))) for _ in range(5))

    def run():
        total = 0.0
        for _ in range(reps):
            monitoring.register_callback(TOOL, E.BRANCH_LEFT, noop_disable)
            monitoring.register_callback(TOOL, E.BRANCH_RIGHT, noop_disable)
            monitoring.set_local_events(
                TOOL, branchy.__code__, E.BRANCH_LEFT | E.BRANCH_RIGHT)
            monitoring.restart_events()
            t, _ = timeit(lambda: (branchy(0), branchy(1)))
            total += t
        return total / reps

    cold = with_tool(run)
    # each if/else contributes 2 branch events (left+right across both calls)
    per_branch = (cold - base) / (n * 2)
    print(f"one-shot BRANCH:          {per_branch * 1e9:8.1f} ns/event "
          f"(cold {cold * 1e3:.2f} ms vs base {base * 1e3:.2f} ms, {n * 2} events)")
    return per_branch


def bench_dispatch_no_disable():
    """Per-event cost when the callback does not DISABLE (hot dispatch)."""
    n = 400
    calls = 200
    flat = make_flat_function(n)
    flat()

    base, _ = min(timeit(lambda: [flat() for _ in range(calls)]) for _ in range(3))

    def run():
        monitoring.register_callback(TOOL, E.LINE, noop_keep)
        monitoring.set_local_events(TOOL, flat.__code__, E.LINE)
        monitoring.restart_events()
        t, _ = min(timeit(lambda: [flat() for _ in range(calls)]) for _ in range(3))
        return t

    hot = with_tool(run)
    per_event = (hot - base) / (n * calls)
    print(f"LINE dispatch (no disable):{per_event * 1e9:7.1f} ns/event")
    return per_event


def bench_no_callback_residual():
    """Local event enabled, no callback registered (coverage's PY_RESUME)."""

    def gen(n):
        i = 0
        while i < n:
            yield i
            i += 1

    n = 300_000

    def consume():
        total = 0
        for v in gen(n):
            total += v
        return total

    consume()
    base, _ = min(timeit(consume) for _ in range(3))

    gen_code = gen.__code__

    def run():
        # No callback registered for PY_RESUME, like coverage.py.
        monitoring.set_local_events(TOOL, gen_code, E.PY_RESUME)
        monitoring.restart_events()
        t, _ = min(timeit(consume) for _ in range(3))
        return t

    resid = with_tool(run)
    per_event = (resid - base) / n
    print(f"no-callback PY_RESUME:    {per_event * 1e9:8.1f} ns/resume "
          f"(steady {resid * 1e3:.2f} ms vs base {base * 1e3:.2f} ms)")
    return per_event


def bench_set_local_events():
    count = 2000
    funcs = make_many_functions(count)

    def run():
        monitoring.register_callback(TOOL, E.LINE, noop_disable)
        monitoring.register_callback(TOOL, E.BRANCH_LEFT, noop_disable)
        monitoring.register_callback(TOOL, E.BRANCH_RIGHT, noop_disable)
        ev = E.LINE | E.BRANCH_LEFT | E.BRANCH_RIGHT | E.PY_RETURN | E.PY_RESUME
        t0 = time.perf_counter()
        for fn in funcs:
            monitoring.set_local_events(TOOL, fn.__code__, ev)
        t1 = time.perf_counter()
        return t1 - t0

    total = with_tool(run)
    per_code = total / count
    print(f"set_local_events:         {per_code * 1e9:8.1f} ns/code object "
          f"(tiny 2-line functions)")
    return per_code


def bench_py_start_scan():
    """First execution of fresh untraced code objects under global PY_START."""
    count = 2000

    def base_run():
        funcs = make_many_functions(count)
        t0 = time.perf_counter()
        for fn in funcs:
            fn(1)
        t1 = time.perf_counter()
        return t1 - t0

    base = base_run()

    def run():
        funcs = make_many_functions(count)
        monitoring.register_callback(TOOL, E.PY_START, noop_disable)
        monitoring.set_events(TOOL, E.PY_START)
        monitoring.restart_events()
        t0 = time.perf_counter()
        for fn in funcs:
            fn(1)
        t1 = time.perf_counter()
        return t1 - t0

    traced = with_tool(run)
    per_code = (traced - base) / count
    print(f"PY_START first call:      {per_code * 1e9:8.1f} ns/code object "
          f"(instrument walk + event + DISABLE; tiny functions)")
    return per_code


def bench_c_callback():
    """Repeat the one-shot LINE and hot-dispatch measurements with a
    C-implemented callback (built from _ccb.c), isolating CPython's event
    dispatch cost from the cost of calling a Python function."""
    import os

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import _ccb
    except ImportError:
        print("C callback:               [_ccb.so not built, skipping]")
        return

    c_disable = _ccb.make_recorder(monitoring.DISABLE)
    c_keep = _ccb.make_recorder(None)

    n = 4000
    reps = 5
    flat = make_flat_function(n)
    flat()
    base, _ = min(timeit(flat) for _ in range(5))

    def run_oneshot():
        total = 0.0
        for _ in range(reps):
            monitoring.register_callback(TOOL, E.LINE, c_disable)
            monitoring.set_local_events(TOOL, flat.__code__, E.LINE)
            monitoring.restart_events()
            t, _ = timeit(flat)
            total += t
        return total / reps

    cold = with_tool(run_oneshot)
    print(f"one-shot LINE (C cb):     {(cold - base) / n * 1e9:8.1f} ns/event")

    n2 = 400
    calls = 200
    flat2 = make_flat_function(n2)
    flat2()
    base2, _ = min(timeit(lambda: [flat2() for _ in range(calls)]) for _ in range(3))

    def run_keep():
        monitoring.register_callback(TOOL, E.LINE, c_keep)
        monitoring.set_local_events(TOOL, flat2.__code__, E.LINE)
        monitoring.restart_events()
        t, _ = min(timeit(lambda: [flat2() for _ in range(calls)]) for _ in range(3))
        return t

    hot = with_tool(run_keep)
    print(f"LINE dispatch (C cb):     {(hot - base2) / (n2 * calls) * 1e9:8.1f} ns/event")


def main():
    print(f"python: {sys.version}")
    bench_one_shot_lines()
    bench_one_shot_branches()
    bench_dispatch_no_disable()
    bench_no_callback_residual()
    bench_set_local_events()
    bench_py_start_scan()
    bench_c_callback()


if __name__ == "__main__":
    main()
