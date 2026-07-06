"""Workload registry for the coverage benchmark.

Each workload module exposes:
    setup()  -- untimed preparation (generation, priming data structures)
    run()    -- one timed iteration; returns a checksum for verification

Workloads are chosen to represent the shapes of real code that people run
under coverage:

    hotloops     -- numeric/branchy tight loops (steady-state dominated)
    oo_calls     -- richards-style OO method dispatch and polymorphism
    calls        -- huge numbers of small function calls and recursion
    generators   -- generator/iterator pipelines (PY_RESUME/PY_YIELD heavy)
    exceptions   -- try/except control flow
    breadth      -- test-suite-like: thousands of functions, most executed
                    only a handful of times, imported under tracing
"""

WORKLOADS = [
    "hotloops",
    "oo_calls",
    "calls",
    "generators",
    "exceptions",
    "breadth",
]


def load(name):
    if name not in WORKLOADS:
        raise ValueError(f"unknown workload: {name}")
    import importlib

    return importlib.import_module(f"workloads.{name}")
