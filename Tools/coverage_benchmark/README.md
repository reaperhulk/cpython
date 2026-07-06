# Coverage benchmark for `sys.monitoring`

A benchmark harness that models how coverage.py measures **line** and
**branch** coverage on Python 3.14+ via `sys.monitoring` (PEP 669), plus
microbenchmarks and profiling helpers used to find optimization
opportunities in CPython's instrumentation machinery.

Goal: understand where the overhead of branch coverage comes from and what
CPython changes would bring it down to ~2% on real-world workloads.

## How coverage.py uses sys.monitoring (3.14+, `COVERAGE_CORE=sysmon`)

* One **global** event: `PY_START`. Its callback decides per code object
  whether the file should be traced. It always returns
  `sys.monitoring.DISABLE`, so it fires **once per code object**.
* For traced code objects it enables **local** events:
  * line mode: `PY_RETURN | PY_RESUME | LINE`
  * branch mode: `PY_RETURN | PY_RESUME | LINE | BRANCH_LEFT | BRANCH_RIGHT`
* The `LINE` / `BRANCH_*` callbacks record the hit and return `DISABLE`,
  making each event **one-shot per code location**: the interpreter removes
  the tool from that location and, when no tools remain, restores the
  original (specializable) bytecode.
* Note: coverage.py registers **no callback** for `PY_RESUME` (nor, in line
  mode, for `PY_RETURN`), but still enables those events. Events without a
  callback are dispatched by the interpreter, do nothing, and are never
  disabled — they keep firing for the whole run.

Consequently, in steady state the bytecode of hot loops is fully restored
and overhead should approach zero; the real-world cost concentrates in:

1. **Breadth**: every executed code object pays instrumentation setup, one
   `PY_START` round trip, and one event per line/branch location — the
   dominant cost in test-suite-shaped runs.
2. **Residual events**: enabled-but-callback-less events (`PY_RESUME`,
   `PY_RETURN` in line mode) that fire forever.
3. **Re-specialization**: de-instrumented instructions restart with cold
   adaptive counters.

## Layout

| file | purpose |
| --- | --- |
| `bench.py` | driver: runs (workload × mode) matrix in fresh subprocesses |
| `child.py` | one measurement in one process |
| `tracers.py` | tracer implementations (see below) |
| `workloads/` | benchmark workloads (see below) |
| `micro.py` | per-event / per-code-object cost model microbenchmarks |
| `profile_oneshot.py` | stress one-shot event paths for `perf record` |
| `_ccb.c` | optional C-implemented callback, isolates dispatch cost |
| `RESULTS.md` | measured results and analysis |

## Tracer modes

| mode | what it is |
| --- | --- |
| `none` | no tracing (baseline) |
| `shim-line` / `shim-branch` | faithful replica of coverage.py's sysmon core with minimal Python callbacks — the CPython-imposed floor for this tool design |
| `shim-line-min` / `shim-branch-min` | same but only enables events that have callbacks (drops coverage.py's callback-less `PY_RESUME`/`PY_RETURN`) |
| `shim-line-keep` / `shim-branch-keep` | callbacks never return DISABLE — per-event dispatch cost, what non-one-shot tools pay |
| `cov-line` / `cov-branch` | the real installed coverage.py on its sysmon core |
| `settrace` | legacy `sys.settrace` line tracer for comparison |

## Workloads

| workload | shape |
| --- | --- |
| `hotloops` | tight numeric/branchy loops (steady-state dominated) |
| `oo_calls` | richards-style polymorphic dispatch, state machines |
| `calls` | millions of tiny function calls + recursion |
| `generators` | generator pipelines (`PY_RESUME`-heavy) |
| `exceptions` | try/except control flow |
| `breadth` | test-suite proxy: 50 modules / ~2200 functions generated on disk, imported under tracing, most functions called only a few times |

Each (workload, mode) runs in fresh processes. Two numbers are reported:

* **cold** — first in-process iteration: pays every one-shot event once,
  exactly like a real coverage run over fresh code. This is the number that
  models "run my test suite under coverage".
* **steady** — best later iteration: everything already disabled and
  de-instrumented; models long-running loops after warmup.

## Running

```
./python Tools/coverage_benchmark/bench.py                 # default modes
./python Tools/coverage_benchmark/bench.py --modes all --procs 5 --iters 6
./python Tools/coverage_benchmark/micro.py                 # cost model
(cd Tools/coverage_benchmark && cc -shared -fPIC -O2 -I../../Include -I../.. _ccb.c -o _ccb.so)
```

`cov-*` modes need `pip install coverage`.

See `RESULTS.md` for measured numbers and the optimization analysis.
