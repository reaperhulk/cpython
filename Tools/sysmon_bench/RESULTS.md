# sys.monitoring coverage optimization log

Machine: 4-core x86-64 Linux container, GCC 13.3, `./configure -C` (default
`-O3`, no PGO/LTO so that per-commit comparisons are not confounded by PGO
noise). All runs pinned to CPU 0 via `taskset`, `PYTHONHASHSEED=0`, min over
5 fresh subprocess runs. Noise floor on this machine is roughly ±1-2% (up to
±5% on the compile-heavy `codegen` workload).

Raw per-run data lives in `results/*.json`.

## Baseline (commit d8bc256, label `baseline-d8bc256`)

Interpreter overhead of coverage.py-style sysmon tracing vs no monitoring:

| workload | replica_line warm | replica_line steady | minimal_line steady | line_nodisable steady | settrace steady |
|---|---:|---:|---:|---:|---:|
| richards | 1.15x | 1.14x | 1.03x | 7.11x | 17.7x |
| deltablue | 1.24x | 1.17x | 0.99x | 6.66x | 19.8x |
| nqueens | 1.33x | 1.33x | 1.20x | 2.58x | 12.3x |
| codegen | 1.12x | 1.25x | 0.99x | 0.99x | 1.03x |
| calls | 1.24x | 1.21x | 1.00x | 5.59x | 19.9x |
| generators | 1.35x | 1.35x | 1.01x | 15.5x | 44.7x |
| pygments_hl | 1.06x | 1.00x | 1.00x | 3.73x | 6.56x |
| hotloop | 1.00x | 1.00x | 1.01x | 8.35x | 16.7x |

Profiling (callgrind) findings that drove the optimization plan:

1. **NULL-callback residual** (`calls`/`replica_line`): coverage.py line mode
   sets local events `LINE | PY_RETURN | PY_RESUME` but registers callbacks
   only for `LINE`. Every return/resume of traced code dispatches through
   `call_instrumentation_vector`, boxes the instruction offset into a fresh
   `PyLong`, then finds a NULL callback and does nothing — forever (DISABLE
   is never returned because no callback runs). ~13% of all instructions on
   the `calls` workload.
2. **Stuck INSTRUMENTED_LINE on same-line loops** (`nqueens`/`minimal_line`):
   locations reached only by same-line jumps (generator expressions,
   one-line loops, multi-line conditions) never deliver a LINE event
   (same-line arrivals are suppressed), so DISABLE-style tools never get a
   chance to de-instrument them. Every execution pays the full
   `_Py_call_instrumentation_line` call (two line-number decodes etc.) just
   to conclude "no event". This is the entire 20% residual on nqueens.
3. **Warmup walks**: `force_instrument_lock_held` + `initialize_lines` +
   `update_instrumentation_data` make ~5 separate passes over the bytecode,
   calling `_Py_GetBaseCodeUnit` (and `_PyInstruction_GetLength`, which
   calls it again) per instruction per pass.

## Opt 1: lazy offset boxing + NULL-callback skip (label `opt1-lazy-callargs`)

`call_instrumentation_vector` now skips tools whose callback is NULL without
allocating the offset argument, and boxes the offset lazily on the first
tool that actually has a callback. Semantics unchanged: an enabled event
with no callback stays enabled (verified: late-registered callbacks still
receive events).

**Independent of other optimizations.** Measured alone vs baseline:

| workload/mode | steady Δ | warm Δ |
|---|---:|---:|
| generators/replica_line | **−8.6%** (1.35x → 1.23x) | −8.9% |
| generators/replica_branch | **−8.1%** (1.34x → 1.23x) | −8.2% |
| calls/replica_line | **−6.0%** (1.21x → 1.15x) | −6.2% |
| deltablue/replica_line | **−4.6%** (1.17x → 1.14x) | −4.4% |
| codegen/replica_line | −3.3% | −4.8% |
| richards/replica_line | −0.7% | −0.8% |
| others / untouched modes | ±2% (noise) | ±2% |

Branch-events-with-live-callback modes (`branch_nodisable`) show +1-2% on
some workloads, at/near the noise floor; the extra per-tool NULL check and
lazy-boxing branch sit on that path. Coverage-style workloads gain far more
than this costs.
