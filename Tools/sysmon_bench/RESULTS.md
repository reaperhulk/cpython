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

## Negative result: runtime same-line fast path (not landed)

An attempt to make the same-line short-circuit in
`_Py_call_instrumentation_line` cheaper (comparing raw line-delta bytes
before decoding line numbers) measured at noise level (0 to −3%) both solo
and stacked on Opt 1. The cost of a stuck `INSTRUMENTED_LINE` is dominated
by the interpreter-side dispatch (stack sync, adaptive-counter pause,
indirect dispatch) and by blocked specialization of the underlying
instruction (e.g. `FOR_ITER` can never specialize to
`FOR_ITER_GEN`/`FOR_ITER_RANGE` while wrapped), not by the helper's line
decoding. Dropped in favor of Opt 2, which removes the instrumentation
from those locations entirely.

## Opt 2: don't instrument same-line jump targets (label `ab-opt1prune-*`)

`initialize_lines()` marks every jump target as a LINE-event location.
But a transfer whose source and target share a line never produces a LINE
event (the runtime prev-line check suppresses it), so for targets reached
*only* by same-line jumps — loop heads of inlined comprehensions/genexps,
chained comparisons, conditional expressions — the location can never
fire, DISABLE-style tools never get to de-instrument it, and the stuck
`INSTRUMENTED_LINE` both costs a full dispatch every execution and blocks
specialization of the instruction under it.

Now same-line jump targets are not marked, except in
generators/coroutines where a resume point (`RESUME` with oparg > 0)
shares the target's line — the one case where a same-line arrival must
still fire (the `prev == RESUME` special case; sys.settrace shows the
yield line on every genexp resume, verified unchanged).

**Independent of Opt 1** (different functions, no textual or semantic
overlap). Measured stacked on Opt 1 with interleaved A/B rounds
(min of 2 sessions × 3 runs each, `results/ab-opt1{only,prune}-r*.json`;
a prior non-interleaved full-suite run was contaminated by machine noise
and is kept as `opt2-prune-sameline-stacked-noisy.json` for honesty):

| workload/mode | steady Δ | steady overhead before → after |
|---|---:|---|
| nqueens/replica_branch | **−8.4%** | 1.34x → 1.21x |
| nqueens/replica_line | **−8.3%** | 1.34x → 1.22x |
| nqueens/minimal_line | **−7.5%** | 1.21x → 1.11x |
| richards/replica_line | **−5.7%** | 1.13x → 1.09x |
| richards/minimal_line | −2.8% | 1.03x → 1.02x |
| calls, deltablue, hotloop | 0 to −2% | little same-line jump content |
| none modes | ±1.5% | noise floor |

The remaining nqueens residual is in generator code objects where the
loop head shares the yield's line (kept for resume semantics); real
coverage.py enables PY_RESUME, whose instrumented RESUME makes those
locations fire once and get disabled, so this matters less in practice
than the minimal_line numbers suggest.

## Opt 3: don't instrument events with no registered callback (labels `ab3-*`)

Instrumentation now only rewrites bytecode for (tool, event) pairs that
have a callback registered. coverage.py's line mode enables local events
`LINE | PY_RETURN | PY_RESUME` but never registers PY_RETURN/PY_RESUME
callbacks (and arcs mode never registers PY_RESUME), so before this
change every return of traced code executed INSTRUMENTED_RETURN_VALUE
and every generator resume INSTRUMENTED_RESUME just to find a NULL
callback — Opt 1 made that cheaper; this removes it entirely.

If a callback is registered (or unregistered) later, the global
instrumentation version is bumped and executing code objects are
refreshed, so events flow exactly as before — verified with
late-registration probes and the full monitoring test matrix. The CALL
instrumentation is kept when only C_RETURN/C_RAISE callbacks exist
(grouped events). One behavior nuance: unregistering and re-registering
a callback now re-arms locations the tool had DISABLEd, matching the
existing behavior of clearing and re-setting the event set.

**Builds on nothing but subsumes part of Opt 1's win** (Opt 1 still
covers multi-tool partial-NULL dispatch and non-instrumented events).
Measured stacked on Opt 1+2, interleaved A/B (`results/ab3-*.json`),
steady state:

| workload/mode | steady Δ vs Opt1+2 | replica_line overhead vs baseline `none` |
|---|---:|---|
| generators/replica_line | **−19.4%** | 1.35x → **1.01x** |
| generators/replica_branch | **−18.4%** | 1.34x → 1.01x |
| calls/replica_line | **−13.2%** | 1.21x → **1.01x** |
| deltablue/replica_line | **−12.4%** | 1.17x → **1.00x** |
| nqueens/replica_line | **−9.7%** | 1.33x → **1.10x** |
| richards/replica_line | **−8.9%** | 1.14x → **1.00x** |
| codegen/replica_branch (warm) | −4.9% | fewer instrumented opcodes to write/restore |
| minimal_line / none modes | ±1% | unaffected, as expected |

## Cumulative: coverage.py sysmon replica overhead, baseline → Opt 1+2+3

Steady-state overhead vs uninstrumented (`none`), same-session numbers:

| workload | baseline replica_line | after opt 1+2+3 |
|---|---:|---:|
| richards | 1.14x | **1.00x** |
| deltablue | 1.17x | **1.00x** |
| nqueens | 1.33x | **1.10x** |
| calls | 1.21x | **1.01x** |
| generators | 1.35x | **1.01x** |
| pygments_hl | 1.00x | 1.00x |
| hotloop | 1.00x | 1.00x |
