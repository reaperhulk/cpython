# Results and analysis

Machine: 4-core x86-64 container, GCC 13.3, `./configure` (release, -O3,
no PGO/LTO, no JIT), Linux 6.18. Python 3.16.0a0 (main @ 1034e73),
coverage.py 7.15 with `COVERAGE_CORE=sysmon`.

Method: min over 5 fresh processes; "cold" = first in-process iteration
(pays every one-shot event once — this is what a real coverage run over
fresh code looks like), "steady" = best later iteration (everything
already DISABLEd and de-instrumented). A/A runs put the noise floor at
about ±3% for steady numbers; treat small steady deltas as ≈0.

## Executive summary

* **Steady-state branch coverage overhead was already ≈0-3% on main**
  for loop/call/exception-shaped code — one-shot DISABLE-based coverage
  de-instruments hot code and it re-specializes. The 2% target is
  effectively met *after warmup*, with two big exceptions that were
  fixed on this branch (below).
* **The real overheads are (a) events that coverage.py enables but
  never registers callbacks for, and (b) first-execution (cold) costs**
  — instrumentation setup, one-shot event dispatch, and (dominating
  everything in real coverage.py branch mode) coverage.py's own
  Python-side per-event work.
* Two CPython patches on this branch cut the worst steady-state cases
  from **+26% to ≈2%** (generators) and **+19% to ≈0%** (line coverage
  of call-heavy code), and reduced one-shot event cost by ~35%.
* After these patches, CPython's interpreter machinery is no longer the
  main obstacle to "2% branch coverage" on realistic suites; the
  remaining big lever on the CPython side is a native "record-and-
  disable" mode (no Python callback round-trip), and on the
  coverage.py side a C implementation of its sysmon callbacks and
  cheaper branch-arc analysis.

## Baseline measurements (unpatched main)

Steady-state overhead vs uninstrumented (min of 5 procs; ±3% noise):

| workload | shim-line | shim-branch | cov-line | cov-branch |
| --- | --- | --- | --- | --- |
| hotloops | +2.1% | +2.0% | +2.7% | +2.4% |
| oo_calls | **+9.8%** | +0.1% | **+10.1%** | +1.1% |
| calls | **+19.3%** | +2.8% | **+19.7%** | +3.3% |
| generators | **+26.3%** | **+26.4%** | **+25.8%** | **+25.2%** |
| exceptions | **+9.3%** | +1.7% | +8.1% | +2.6% |
| breadth | +2.0% | +1.3% | +1.4% | +1.6% |

The bold numbers are all one bug: coverage.py enables local events it
registers **no callback** for (`PY_RESUME` always, and `PY_RETURN` in
line mode). Dispatch of an event with no callback is a complete no-op,
but the instruction stays instrumented and fires forever (~9.5 ns per
occurrence): every generator resume and — in line mode — every function
return pays it for the entire run. Note the irony that this made *line*
coverage slower than *branch* coverage on call-heavy code.

Cold overhead (first run of fresh code; breadth = test-suite proxy with
2,250 functions/classes across 50 modules, warm pyc cache, most
functions called ≤13 times):

| workload | shim-line | shim-branch | cov-line | cov-branch |
| --- | --- | --- | --- | --- |
| breadth (cold) | +93% | **+139%** | +302% | **+1155%** |

cov-branch's 8-50x blowup over the CPython floor is coverage.py's
`branch_trails()`: a full dis-based analysis of each code object,
triggered from the *first branch event* of that code object. That is a
coverage.py-side cost and CPython changes cannot help it.

Per-event cost model (micro.py, baseline build):

| operation | cost |
| --- | --- |
| one-shot LINE event (fire → Python callback → DISABLE → de-instrument) | ~170 ns |
| one-shot BRANCH event | ~186 ns |
| LINE dispatch when callback does not disable | ~64 ns |
| enabled event with NO registered callback | ~9.5 ns, every occurrence |
| `set_local_events()`, tiny 2-line code object | ~345 ns |
| first call of fresh code object under global PY_START | ~122 ns |

perf attribution of the `set_local_events` path: 95% is
`force_instrument_lock_held` (56%) + `_Py_GetBaseCodeUnit` (39%) —
i.e. almost all setup time is (re-)decoding bytecode: each instruction
was decoded 6-8 times across the various instrumentation passes.

## CPython changes prototyped on this branch

### 1. Don't instrument events for tools with no registered callback

`mask_toolless_events()` in `Python/instrumentation.c`: (tool, event)
pairs with no callback are masked out of the active monitor set at
instrumentation time. Registering a callback later bumps the global
instrumentation version, so code objects lazily re-instrument with the
new mask (verified: late registration delivers events; per-location
DISABLE state survives unregister/re-register; `restart_events()`
re-delivers). CALL is exempt since its instrumentation also drives the
grouped C_RETURN/C_RAISE events.

### 2. Stop re-decoding bytecode in instrumentation walks

* `force_instrument_lock_held`: decode each instruction once; derive
  length from the base opcode instead of calling
  `_PyInstruction_GetLength` (a second full decode) per instruction.
* line-tools add/remove passes: iterate per code unit and test the
  original-opcode byte directly (cache units store 0).
* `update_instrumentation_data`: compute max line by iterating the
  line table's address ranges instead of stepping instructions (also
  removes a duplicated `_PyCode_InitAddressRange`).
* `initialize_lines`: reuse already-decoded opcodes for lengths.

### Measured effect (patched build)

Micro:

| operation | baseline | patched |
| --- | --- | --- |
| one-shot LINE event | 170 ns | **113 ns** |
| one-shot BRANCH event | 186 ns | 173 ns |
| no-callback residual | 9.5 ns/occurrence forever | **0** (never instrumented) |
| PY_START first call | 122 ns | 97 ns |

Steady-state overhead, patched (all now at or under the target, within
noise):

| workload | shim-line | shim-branch | cov-line | cov-branch |
| --- | --- | --- | --- | --- |
| hotloops | +1.0% | **+0.1%** | +0.5% | +1.8% |
| oo_calls | ≈0% | ≈0% | +0.7% | +1.8% |
| calls | ≈0% | ≈0% | +0.9% | +1.6% |
| generators | +2.9% | +1.9% | +3.8% | +4.3% |
| exceptions | +2.3% | +1.6% | +1.8% | +1.4% |
| breadth | +0.8% | ≈0% | ≈0% | ≈0% |

(generators fluctuated +1.9-4.7% across runs; the A/A noise floor on
this machine is ±3%, so treat it as ≤ a few percent, dramatically down
from +26%.)

Cold breadth (test-suite proxy), patched:

| mode | cold overhead |
| --- | --- |
| shim-line | +82-84% |
| shim-branch | +119-131% |
| shim-branch with C callbacks (`_ccb.c`) | **+57-61%** |
| cov-line | +263-271% |
| cov-branch | still ~+13,000% (`branch_trails`) |

### Decomposition of the remaining cold overhead (breadth, shim-branch)

~46 ms of overhead on a 34 ms baseline, for 43k covered locations and
3,052 traced code objects:

| component | ms | share |
| --- | --- | --- |
| Python callback execution (tool-side: call + dict/set recording) | ~26 | ~57% |
| `set_local_events` instrumentation setup (~3.3 µs/code object) | ~10 | ~21% |
| event dispatch + DISABLE/de-instrument + PY_START machinery | ~10 | ~22% |

Per covered location, all-in: ~1.05 µs with Python callbacks, ~450 ns
with C callbacks. `breadth` is deliberately extreme — it does only
~0.8 µs of real work per covered location. A real test suite doing 50x
more work per covered line would see ~1-2% from the same per-location
cost. In other words: **after these patches, cold overhead is a
per-covered-location constant (~0.5-1 µs); whether that is 2% or 100%
depends on how much work the suite does per location.** The way to
shrink the constant further is below.

## Optimization avenues (ranked by measured impact)

1. **[implemented here] Mask events for tools with no callback.**
   Generators +26% → ≈2%; line mode on call-heavy code +10-19% → ≈0%.
   Semantics-preserving; ~60-line patch. Refinement before upstreaming:
   gate the version bump on "monitoring is (or has been) in use" to
   avoid re-instrument churn for tools that register callbacks but
   never enable events.

2. **[implemented here] Single-decode instrumentation walks.**
   One-shot LINE −34%, PY_START −20%, setup share of cold overhead
   down measurably. More is available: a fused single-pass
   `initialize_lines` (line deltas + jump targets + exception targets
   in one walk) and lazy `line_tools` allocation.

3. **C-level callbacks in the tool** (coverage.py-side; API already
   sufficient). Whole-run breadth overhead halves: +131% → +61%. A C
   `sysmon` core for coverage.py (like its existing C tracer for
   settrace) is the single biggest tool-side win: per-event cost
   16.5 ns hot / 62 ns one-shot vs 61/113 ns with Python callbacks.

4. **coverage.py-side: make branch-arc resolution lazy/cheap.**
   cov-branch cold is ~100x the CPython floor because `branch_trails()`
   disassembles and analyses the whole code object on first branch
   event. Persisting trails across runs, or resolving arcs at
   report time from raw (offset, offset) pairs — which CPython already
   provides, including `code.co_branches()` — would collapse cov-branch
   to shim-branch numbers. Without this, no CPython change matters for
   real-world branch coverage: it is >90% of the gap today.

5. **Native "record-and-disable" mode in sys.monitoring.** For
   coverage-style tools the callback only records (code, offset/line)
   and returns DISABLE. If the interpreter recorded into an internal
   per-code buffer and auto-disabled — no callback invocation at all —
   the per-event cost drops to the de-instrument floor (~30-40 ns,
   estimated from the C-callback floor minus vectorcall overhead), and
   with #6 the per-location constant approaches ~100-150 ns, i.e. ~2%
   even on breadth-shaped suites doing ~5-10 µs of work per location.
   API sketch: a tool flag or `set_local_events(..., record=True)`
   with `sys.monitoring.drain_records(tool_id)`.

6. **Cheaper `set_local_events`.** Still ~3.3 µs per (40-line) code
   object: allocation + multi-pass init + per-offset function calls
   through `MODIFY_BYTECODE`. Fusing passes and batching the per-offset
   add loops should cut most of the remaining ~21%.

7. **Free-threaded build: DISABLE stops the world.** Not measured here
   (no-op under the GIL), but `call_instrumentation_vector` executes
   `_PyEval_StopTheWorld` for *every* DISABLE return — one global
   synchronization per covered location on FT builds. Per-code locking
   (the bytecode is already mutated under `LOCK_CODE` elsewhere) is
   needed before sysmon coverage is viable on free-threaded Python.

8. **Boxing of branch-event offsets.** Each BRANCH_LEFT/RIGHT event
   heap-allocates 1-2 ints (offsets >256). Worth ~10-20 ns/event; only
   relevant after #3/#5.

## Reproducing

```
./python Tools/coverage_benchmark/bench.py --modes all --procs 5 --iters 6
./python Tools/coverage_benchmark/micro.py
(cd Tools/coverage_benchmark && cc -shared -fPIC -O2 -I../../Include -I../.. _ccb.c -o _ccb.so)
perf record -- ./python Tools/coverage_benchmark/profile_oneshot.py setup 2000
```

Correctness: `test_monitoring test_sys_settrace test_sys_setprofile
test_bdb test_trace test_pdb test_dis test_code test_generators
test_coroutines test_profiling.test_tracing_profiler` all pass on the
patched build, plus a dedicated late-registration semantics check
(events enabled before a callback exists are delivered once one is
registered; DISABLE state survives unregister/re-register;
`restart_events()` re-delivers).
