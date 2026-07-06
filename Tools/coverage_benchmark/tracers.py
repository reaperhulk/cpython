"""Coverage tracer implementations for the sys.monitoring benchmark.

The "shim" tracers replicate the *interpreter-facing* behaviour of
coverage.py's sys.monitoring core (coverage/sysmon.py) while doing the
absolute minimum of Python-side work in the callbacks.  They therefore
measure the floor that CPython's sys.monitoring implementation imposes on
any coverage-style tool:

* One global PY_START event.  The callback decides whether the code object
  should be traced (by filename prefix), enables local events on it if so,
  and always returns DISABLE.
* Local events on traced code objects, exactly as coverage.py sets them:
      line mode:    PY_RETURN | PY_RESUME | LINE
      branch mode:  PY_RETURN | PY_RESUME | LINE | BRANCH_LEFT | BRANCH_RIGHT
  Note that coverage.py registers *no callback* for PY_RESUME (and, in line
  mode, none for PY_RETURN either); the events keep firing into the C
  dispatch with nothing to call and are never disabled.  The shims replicate
  that faithfully; the "-min" variants only enable events that have
  callbacks, to quantify the cost of that behaviour.
* LINE and BRANCH_* callbacks record into a set and return DISABLE, making
  every event one-shot per code location, like coverage.py.

The "cov" tracers run the real, installed coverage.py with the sysmon core,
giving the true end-to-end real-world overhead (CPython + coverage.py's own
Python-side bookkeeping).
"""

import os
import sys

monitoring = sys.monitoring
TOOL_ID = monitoring.COVERAGE_ID


class ShimTracer:
    """Minimal replica of coverage.py's sysmon core."""

    def __init__(self, prefixes, branch, faithful=True, disable=True):
        self.prefixes = tuple(prefixes)
        self.branch = branch
        # faithful=True enables the same local event set as coverage.py,
        # including events that have no registered callback.
        self.faithful = faithful
        # disable=False makes callbacks *not* return DISABLE, so every
        # execution of every location fires an event.  This measures the
        # per-event dispatch cost (an upper bound, and what non-one-shot
        # tools like debuggers pay).
        self.disable = disable
        self.data = {}            # filename -> set of lines / branch pairs
        self.file_should_trace = {}  # filename -> bool
        self.code_data = {}       # id(code) -> per-file data set
        self.code_objects = []    # keep code objects alive so ids are stable

    # -- callbacks ---------------------------------------------------------

    def py_start(self, code, instruction_offset):
        fn = code.co_filename
        trace = self.file_should_trace.get(fn)
        if trace is None:
            trace = fn.startswith(self.prefixes)
            self.file_should_trace[fn] = trace
            if trace:
                self.data[fn] = set()
        if trace:
            events = monitoring.events
            if self.faithful:
                local = events.PY_RETURN | events.PY_RESUME | events.LINE
            else:
                local = events.LINE
            if self.branch:
                local |= events.BRANCH_LEFT | events.BRANCH_RIGHT
            monitoring.set_local_events(TOOL_ID, code, local)
            self.code_data[id(code)] = self.data[fn]
            self.code_objects.append(code)
        return monitoring.DISABLE

    def line(self, code, line_number):
        data = self.code_data.get(id(code))
        if data is not None:
            data.add(line_number)
        if self.disable:
            return monitoring.DISABLE
        return None

    def branch_event(self, code, instruction_offset, destination_offset):
        data = self.code_data.get(id(code))
        if data is not None:
            data.add((instruction_offset, destination_offset))
        if self.disable:
            return monitoring.DISABLE
        return None

    def py_return(self, code, instruction_offset, retval):
        data = self.code_data.get(id(code))
        if data is not None:
            data.add((-1, instruction_offset))
        return monitoring.DISABLE

    # -- lifecycle ---------------------------------------------------------

    def start(self):
        monitoring.use_tool_id(TOOL_ID, "bench-shim")
        events = monitoring.events
        register = monitoring.register_callback
        register(TOOL_ID, events.PY_START, self.py_start)
        if self.branch:
            register(TOOL_ID, events.PY_RETURN, self.py_return)
            register(TOOL_ID, events.LINE, self.line)
            register(TOOL_ID, events.BRANCH_RIGHT, self.branch_event)
            register(TOOL_ID, events.BRANCH_LEFT, self.branch_event)
        else:
            register(TOOL_ID, events.LINE, self.line)
        monitoring.set_events(TOOL_ID, events.PY_START)
        monitoring.restart_events()

    def stop(self):
        monitoring.set_events(TOOL_ID, 0)
        monitoring.free_tool_id(TOOL_ID)

    def stats(self):
        points = sum(len(v) for v in self.data.values())
        return {"files": len(self.data), "points": points}


class RealCoverage:
    """The installed coverage.py, forced onto the sysmon core."""

    def __init__(self, prefixes, branch):
        os.environ["COVERAGE_CORE"] = "sysmon"
        import coverage

        self.cov = coverage.Coverage(
            data_file=None,
            branch=branch,
            include=[os.path.join(p, "*") for p in prefixes],
        )

    def start(self):
        self.cov.start()

    def stop(self):
        self.cov.stop()

    def stats(self):
        data = self.cov.get_data()
        files = data.measured_files()
        points = 0
        for f in files:
            if data.has_arcs():
                points += len(data.arcs(f) or ())
            else:
                points += len(data.lines(f) or ())
        return {"files": len(files), "points": points}


class SetTraceTracer:
    """Legacy sys.settrace line tracer, for comparison."""

    def __init__(self, prefixes):
        self.prefixes = tuple(prefixes)
        self.data = {}
        self.file_should_trace = {}

    def _local(self, frame, event, arg):
        if event == "line":
            self.data[frame.f_code.co_filename].add(frame.f_lineno)
        return self._local

    def _global(self, frame, event, arg):
        if event != "call":
            return None
        fn = frame.f_code.co_filename
        trace = self.file_should_trace.get(fn)
        if trace is None:
            trace = fn.startswith(self.prefixes)
            self.file_should_trace[fn] = trace
            if trace:
                self.data.setdefault(fn, set())
        if trace:
            return self._local
        return None

    def start(self):
        sys.settrace(self._global)

    def stop(self):
        sys.settrace(None)

    def stats(self):
        points = sum(len(v) for v in self.data.values())
        return {"files": len(self.data), "points": points}


class NullTracer:
    def start(self):
        pass

    def stop(self):
        pass

    def stats(self):
        return {}


def make_tracer(mode, prefixes):
    if mode == "none":
        return NullTracer()
    if mode == "shim-line":
        return ShimTracer(prefixes, branch=False)
    if mode == "shim-branch":
        return ShimTracer(prefixes, branch=True)
    if mode == "shim-line-min":
        return ShimTracer(prefixes, branch=False, faithful=False)
    if mode == "shim-branch-min":
        return ShimTracer(prefixes, branch=True, faithful=False)
    if mode == "shim-line-keep":
        return ShimTracer(prefixes, branch=False, disable=False)
    if mode == "shim-branch-keep":
        return ShimTracer(prefixes, branch=True, disable=False)
    if mode == "cov-line":
        return RealCoverage(prefixes, branch=False)
    if mode == "cov-branch":
        return RealCoverage(prefixes, branch=True)
    if mode == "settrace":
        return SetTraceTracer(prefixes)
    raise ValueError(f"unknown mode: {mode}")


ALL_MODES = [
    "none",
    "shim-line",
    "shim-branch",
    "shim-line-min",
    "shim-branch-min",
    "shim-line-keep",
    "shim-branch-keep",
    "cov-line",
    "cov-branch",
    "settrace",
]

DEFAULT_MODES = [
    "none",
    "shim-line",
    "shim-branch",
    "cov-line",
    "cov-branch",
]
