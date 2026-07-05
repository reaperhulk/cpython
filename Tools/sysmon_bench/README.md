# sys.monitoring coverage benchmark (sysmon)

Benchmarks the interpreter-side cost of coverage measurement built on
`sys.monitoring` (PEP 669), the mechanism coverage.py calls "sysmon"
(its default core on Python 3.14+).

## What is measured

Two phases matter for coverage tools:

- **warm**: the first pass over the code. This includes, per code object:
  the `PY_START` event and callback, `set_local_events()` (allocating
  monitoring data and rewriting bytecode to instrumented opcodes), one
  `LINE`/`BRANCH` event per location, and the `DISABLE` path that
  de-instruments each location after its first hit.
- **steady**: everything after that. For DISABLE-style coverage this is
  the residual overhead that remains once all events have been disabled.

## Modes

| mode | description |
|---|---|
| `none` | no monitoring (baseline) |
| `replica_line` | faithful port of coverage.py's sysmon core, line mode (local events `LINE\|PY_RETURN\|PY_RESUME`, DISABLE after first hit; PY_RETURN/PY_RESUME have **no callback**, mirroring coverage.py) |
| `replica_branch` | coverage.py sysmon branch mode event pattern (adds `BRANCH_LEFT`/`BRANCH_RIGHT` + `PY_RETURN` callback) |
| `minimal_line` | leanest possible sysmon line coverage (local events `LINE` only) |
| `line_nodisable` | LINE events never disabled (dynamic contexts / debugger-style; measures raw per-event dispatch) |
| `branch_nodisable` | BRANCH events never disabled |
| `settrace` | legacy `sys.settrace` line coverage, for comparison |

## Workloads

- `richards`, `deltablue`, `nqueens`: classic pure-Python macro
  benchmarks (vendored from pyperformance) — steady-state realistic code.
- `codegen`: compiles+executes a fresh synthetic module of 600 functions
  every rep, so *every* rep exercises the full warmup path
  (instrumentation insertion, first-hit LINE events, DISABLE).
- `hotloop`, `calls`, `generators`: micro workloads isolating per-event
  dispatch, per-return residual, and generator-resume residual.
- `pygments_hl`: real-world large coverage set — imports pygments and
  highlights a large source file. Run `python fetch_third_party.py` once
  first (downloads the pygments sdist from PyPI into `third_party/`).

## Running

```sh
./python Tools/sysmon_bench/fetch_third_party.py   # once
./python Tools/sysmon_bench/harness.py --label my-experiment
```

Results are printed as a markdown table and saved to `results/<label>.json`.
Subprocesses are pinned with `taskset` (CPU 0 by default, `--cpu -1` to
disable) and run with `PYTHONHASHSEED=0`.  `warm` is the min over runs of
(import + first rep); `steady` is the min over runs of the mean of the
remaining reps.

See `RESULTS.md` for the benchmark log of this branch's optimization work.
