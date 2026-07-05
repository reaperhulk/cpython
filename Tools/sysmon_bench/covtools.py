"""Coverage-style sys.monitoring tools for benchmarking.

The "replica_*" tools mirror the behavior of coverage.py's sysmon core
(coverage/sysmon.py in coverage 7.10): a global PY_START event decides,
once per code object, whether the file is traced.  For traced code it
computes a byte->line map and enables local events, then every callback
returns sys.monitoring.DISABLE after recording, so each event location
fires exactly once.

Notably, coverage.py's line mode sets local events LINE | PY_RETURN |
PY_RESUME but only registers callbacks for PY_RETURN / PY_RESUME in
branch ("arcs") mode, so in line mode every return from traced code goes
through the instrumentation machinery only to find a NULL callback.  The
replica reproduces that.

The "minimal_*" tools are the leanest possible sysmon coverage tools,
to isolate the interpreter-side floor.  The "*_nodisable" tools never
return DISABLE, standing in for tools that cannot disable events
(e.g. coverage dynamic contexts, debuggers).
"""

import os
import sys

WORKLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workloads")
THIRD_PARTY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "third_party")

E = sys.monitoring.events
DISABLE = sys.monitoring.DISABLE
TOOL_ID = sys.monitoring.COVERAGE_ID


def _should_trace(filename):
    return (
        filename.startswith(WORKLOAD_DIR)
        or filename.startswith(THIRD_PARTY_DIR)
        or filename.startswith("<bench_codegen")
    )


def _bytes_to_lines(code):
    """coverage.py sysmon.py bytes_to_lines()"""
    b2l = {}
    for bstart, bend, lineno in code.co_lines():
        if lineno is not None:
            for boffset in range(bstart, bend, 2):
                b2l[boffset] = lineno
    return b2l


class _Base:
    name = None

    def __init__(self):
        self.data = {}

    def start(self):
        pass

    def stop(self):
        pass

    def summary(self):
        return {
            "files": len(self.data),
            "points": sum(len(v) for v in self.data.values()),
        }


class NoTool(_Base):
    name = "none"


class ReplicaLine(_Base):
    """Port of coverage.py SysMonitor, line mode."""

    name = "replica_line"

    def __init__(self):
        super().__init__()
        self.code_infos = {}     # id(code) -> [tracing, file_data, b2l]
        self.code_objects = []
        self.should_trace_cache = {}

    def start(self):
        mon = sys.monitoring
        mon.use_tool_id(TOOL_ID, "bench-coverage")
        mon.register_callback(TOOL_ID, E.PY_START, self.py_start)
        mon.register_callback(TOOL_ID, E.LINE, self.line)
        mon.set_events(TOOL_ID, E.PY_START)
        mon.restart_events()

    def stop(self):
        sys.monitoring.set_events(TOOL_ID, 0)
        sys.monitoring.free_tool_id(TOOL_ID)

    LOCAL_EVENTS = E.PY_RETURN | E.PY_RESUME | E.LINE

    def py_start(self, code, instruction_offset):
        code_info = self.code_infos.get(id(code))
        if code_info is None:
            filename = code.co_filename
            tracing = self.should_trace_cache.get(filename)
            if tracing is None:
                tracing = _should_trace(filename)
                self.should_trace_cache[filename] = tracing
            if tracing:
                file_data = self.data.setdefault(filename, set())
                b2l = _bytes_to_lines(code)
            else:
                file_data = None
                b2l = None
            self.code_infos[id(code)] = (tracing, file_data, b2l)
            self.code_objects.append(code)
            if tracing:
                sys.monitoring.set_local_events(TOOL_ID, code, self.LOCAL_EVENTS)
        return DISABLE

    def line(self, code, line_number):
        code_info = self.code_infos.get(id(code))
        if code_info is not None and code_info[1] is not None:
            code_info[1].add(line_number)
        return DISABLE


class ReplicaBranch(ReplicaLine):
    """Port of coverage.py SysMonitor, branch ("arcs") mode.

    The BRANCH_LEFT/BRANCH_RIGHT handling is simplified relative to
    coverage.py (no branch_trails computation), but the event pattern
    and DISABLE behavior are identical, as are the byte->line lookups.
    """

    name = "replica_branch"

    LOCAL_EVENTS = (
        E.PY_RETURN | E.PY_RESUME | E.LINE | E.BRANCH_RIGHT | E.BRANCH_LEFT
    )

    def start(self):
        mon = sys.monitoring
        mon.use_tool_id(TOOL_ID, "bench-coverage")
        mon.register_callback(TOOL_ID, E.PY_START, self.py_start)
        mon.register_callback(TOOL_ID, E.PY_RETURN, self.py_return)
        mon.register_callback(TOOL_ID, E.LINE, self.line_arcs)
        mon.register_callback(TOOL_ID, E.BRANCH_RIGHT, self.branch_either)
        mon.register_callback(TOOL_ID, E.BRANCH_LEFT, self.branch_either)
        mon.set_events(TOOL_ID, E.PY_START)
        mon.restart_events()

    def py_return(self, code, instruction_offset, retval):
        code_info = self.code_infos.get(id(code))
        last_line = code_info[2].get(instruction_offset)
        if last_line is not None:
            code_info[1].add((last_line, -code.co_firstlineno))
        return DISABLE

    def line_arcs(self, code, line_number):
        code_info = self.code_infos[id(code)]
        code_info[1].add((line_number, line_number))
        return DISABLE

    def branch_either(self, code, instruction_offset, destination_offset):
        code_info = self.code_infos[id(code)]
        b2l = code_info[2]
        l1 = b2l.get(instruction_offset)
        l2 = b2l.get(destination_offset)
        if l2 is not None and l1 != l2:
            code_info[1].add((l1, l2))
        return DISABLE


class MinimalLine(_Base):
    """Leanest possible sysmon line coverage: only LINE local events."""

    name = "minimal_line"

    LOCAL_EVENTS = E.LINE
    RETURN_DISABLE = True

    def __init__(self):
        super().__init__()
        self.seen_codes = set()

    def start(self):
        mon = sys.monitoring
        mon.use_tool_id(TOOL_ID, "bench-coverage")
        mon.register_callback(TOOL_ID, E.PY_START, self.py_start)
        mon.register_callback(TOOL_ID, E.LINE, self.line)
        mon.set_events(TOOL_ID, E.PY_START)
        mon.restart_events()

    def stop(self):
        sys.monitoring.set_events(TOOL_ID, 0)
        sys.monitoring.free_tool_id(TOOL_ID)

    def py_start(self, code, instruction_offset):
        if id(code) not in self.seen_codes:
            self.seen_codes.add(id(code))
            if _should_trace(code.co_filename):
                self.data.setdefault(code.co_filename, set())
                sys.monitoring.set_local_events(TOOL_ID, code, self.LOCAL_EVENTS)
        return DISABLE

    def line(self, code, line_number):
        data = self.data.get(code.co_filename)
        if data is not None:
            data.add(line_number)
        if self.RETURN_DISABLE:
            return DISABLE
        return None


class LineNoDisable(MinimalLine):
    """LINE events that are never disabled (dynamic contexts, debuggers)."""

    name = "line_nodisable"
    RETURN_DISABLE = False


class BranchNoDisable(MinimalLine):
    """BRANCH events that are never disabled."""

    name = "branch_nodisable"
    LOCAL_EVENTS = E.BRANCH_RIGHT | E.BRANCH_LEFT

    def start(self):
        mon = sys.monitoring
        mon.use_tool_id(TOOL_ID, "bench-coverage")
        mon.register_callback(TOOL_ID, E.PY_START, self.py_start)
        mon.register_callback(TOOL_ID, E.BRANCH_RIGHT, self.branch)
        mon.register_callback(TOOL_ID, E.BRANCH_LEFT, self.branch)
        mon.set_events(TOOL_ID, E.PY_START)
        mon.restart_events()

    def branch(self, code, instruction_offset, destination_offset):
        data = self.data.get(code.co_filename)
        if data is not None:
            data.add((instruction_offset, destination_offset))
        return None


class SetTrace(_Base):
    """Legacy sys.settrace line coverage, for comparison."""

    name = "settrace"

    def start(self):
        sys.settrace(self._trace)

    def stop(self):
        sys.settrace(None)

    def _trace(self, frame, event, arg):
        if event == "call":
            filename = frame.f_code.co_filename
            if not _should_trace(filename):
                return None
            return self._trace
        if event == "line":
            filename = frame.f_code.co_filename
            data = self.data.get(filename)
            if data is None:
                data = self.data.setdefault(filename, set())
            data.add(frame.f_lineno)
        return self._trace


TOOLS = {
    cls.name: cls
    for cls in (
        NoTool,
        ReplicaLine,
        ReplicaBranch,
        MinimalLine,
        LineNoDisable,
        BranchNoDisable,
        SetTrace,
    )
}
