# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""S-10 spike, Windows check: Job Object termination of a child process tree, and the replay scenarios on Windows.

Run:  uv run --script spikes/S-10-replay/windows_check.py        (the root CI does this in its Windows job)

Windows only. On any other platform it prints SKIPPED and exits 0 after the structure-size check; a SKIPPED run is
not a Windows result. Nothing in this file had run on Windows when it was written: the report says "pending".

Part A: for each way of starting a server, a stand-in "engine" process starts a stand-in "server" process that starts
two grandchildren; the engine then ends (exit, or TerminateProcess from outside); this script asserts which
processes are gone. Cases:
  none          control: no job. The tree must survive (proves the test can see a survivor).
  assign_after  Popen, then AssignProcessToJobObject. Must work for a slow starter; the race is measured separately.
  suspended     Popen with CREATE_SUSPENDED, assign, resume (jobobject.popen_in_job).
  self_assign   the engine puts itself in the job first; children inherit it. No window at all.
  late          deliberately late assignment (2 s): the grandchildren created before it must ESCAPE (documents the
                race rule: a process is in the job only if created after its parent joined, or assigned itself).
  nested        engine in an outer job, each server in its own inner job (Windows 8 and later): terminating one
                inner job kills only that server's tree; the engine ending kills the rest.
Then a race loop counts how often a plain Popen-then-assign lets a child's immediate grandchild escape, and asserts that
the suspended start never does.

Part B (skip with --no-replay): runs check.run_all() (the replay scenarios) and a short journal overhead
measurement on this Windows runner, for the numbers the Linux report cannot give.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SELF = str(Path(__file__).resolve())
# The base interpreter, not a venv launcher: a venv python.exe on Windows can itself start the real interpreter as a
# child, which would blur what this test measures. (The report lists this as a hazard for Python-based servers.)
PY = getattr(sys, "_base_executable", sys.executable)

import jobobject as jo  # noqa: E402


# --------------------------------------------------------------------------------------------------------------
# Roles (this file starts itself as engine, child, spawner and sleeper)
# --------------------------------------------------------------------------------------------------------------


def report(state: str, obj: dict[str, Any]) -> None:
    with open(state, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")
        f.flush()


def read_reports(state: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        text = Path(state).read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass  # a line still being written
    return out


def wait_report(state: str, pred: Any, timeout: float, proc: "subprocess.Popen[Any] | None" = None) -> dict[str, Any]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        for r in read_reports(state):
            if pred(r):
                return r
        if proc is not None and proc.poll() is not None:
            for r in read_reports(state):
                if pred(r):
                    return r
            raise RuntimeError(f"process ended with code {proc.returncode} before the expected report")
        time.sleep(0.05)
    raise RuntimeError("timed out waiting for a report")


def role_sleeper() -> None:
    time.sleep(600)


def role_child(state: str, tag: str) -> None:
    """The stand-in server: starts two grandchildren at once, reports, then waits."""
    grands = [subprocess.Popen([PY, SELF, "sleeper"]).pid for _ in range(2)]
    report(state, {"event": "child_up", "tag": tag, "pid": os.getpid(), "grand": grands})
    time.sleep(600)


def role_spawner() -> None:
    """For the race loop: the very first act is to start a grandchild."""
    g = subprocess.Popen([PY, SELF, "sleeper"])
    print(json.dumps({"grand": g.pid}), flush=True)
    time.sleep(600)


def role_engine(variant: str, mode: str, state: str) -> None:
    """The stand-in engine. Starts the stand-in server(s) the way `variant` says, then ends or waits to be killed."""
    outer = jo.JobObject() if variant in ("assign_after", "suspended", "self_assign", "late", "nested") else None
    if variant in ("self_assign", "nested"):
        assert outer is not None
        outer.assign_current_process()
    tags = ["A", "B"] if variant == "nested" else ["A"]
    inner: dict[str, jo.JobObject] = {}
    for tag in tags:
        argv = [PY, SELF, "child", state, tag]
        if variant == "none" or variant == "self_assign":
            p = subprocess.Popen(argv)
        elif variant == "assign_after":
            assert outer is not None
            p = subprocess.Popen(argv)
            outer.assign_pid(p.pid)
        elif variant == "suspended":
            assert outer is not None
            p = jo.popen_in_job(outer, argv)
        elif variant == "late":
            assert outer is not None
            p = subprocess.Popen(argv)
            time.sleep(2.0)
            outer.assign_pid(p.pid)
        elif variant == "nested":
            inner[tag] = jo.JobObject()
            p = jo.popen_in_job(inner[tag], argv)
        else:
            raise SystemExit(f"unknown variant {variant}")
        report(state, {"event": "spawned", "tag": tag, "popen_pid": p.pid})
    for tag in tags:
        wait_report(state, lambda r, t=tag: r.get("event") == "child_up" and r.get("tag") == t, 30)
    if variant == "nested":
        inner["A"].terminate()
        report(state, {"event": "terminated_a"})
    else:
        report(state, {"event": "ready"})
    if mode == "exit":
        os._exit(0)  # the job handle closes with the process
    time.sleep(600)  # mode "kill": the checker ends this process from outside


# --------------------------------------------------------------------------------------------------------------
# Part A: the checks
# --------------------------------------------------------------------------------------------------------------

Handles = dict[str, dict[int, int]]  # tag -> pid -> waitable handle


def collect(state: str) -> Handles:
    pids: dict[str, set[int]] = {}
    for r in read_reports(state):
        tag = r.get("tag")
        if tag is None:
            continue
        s = pids.setdefault(tag, set())
        if r["event"] == "spawned":
            s.add(r["popen_pid"])
        if r["event"] == "child_up":
            s.add(r["pid"])
            s.update(r["grand"])
    out: Handles = {}
    for tag, s in pids.items():
        out[tag] = {}
        for pid in s:
            try:
                out[tag][pid] = jo.open_waitable(pid)
            except OSError:
                pass  # already gone
    return out


def alive(handles: dict[int, int], within: float) -> list[int]:
    """Pids still running after waiting up to `within` seconds for each."""
    return [pid for pid, h in handles.items() if not jo.wait_dead(h, within)]


def cleanup(handles: Handles) -> None:
    for group in handles.values():
        for h in group.values():
            jo.terminate_handle(h)
            jo.close_handle(h)


def run_case(variant: str, mode: str, expect: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="s10-job-") as d:
        state = str(Path(d) / "state.jsonl")
        eng = subprocess.Popen([PY, SELF, "engine", variant, mode, state])
        handles: Handles = {}
        try:
            first = "terminated_a" if variant == "nested" else "ready"
            wait_report(state, lambda r: r.get("event") == first, 60, eng)
            handles = collect(state)
            total = sum(len(g) for g in handles.values())
            if variant == "nested":
                a_alive = alive(handles["A"], 10)
                b_alive = alive(handles["B"], 0)
                if a_alive or len(b_alive) != len(handles["B"]):
                    return False, f"after TerminateJobObject(inner A): A alive={a_alive}, B alive={len(b_alive)}/{len(handles['B'])}"
            if mode == "kill":
                eng.kill()
            eng.wait(timeout=30)
            if expect == "dead":
                left = {t: alive(g, 10) for t, g in handles.items()}
                left = {t: v for t, v in left.items() if v}
                return (not left), f"{total} processes tracked; still alive after the engine ended: {left or 'none'}"
            if expect == "nested":
                left = alive(handles["B"], 10)
                return (not left), f"inner A tree gone, then B tree after the engine ended; B still alive: {left or 'none'}"
            time.sleep(3.0)
            if expect == "survive":
                gone = [pid for g in handles.values() for pid, h in g.items() if jo.wait_dead(h, 0)]
                return (not gone), f"{total} processes tracked; gone without a job: {gone or 'none'} (all should survive)"
            if expect == "escape":
                child_gone = all(jo.wait_dead(h, 10) for pid, h in handles["A"].items() if pid in _child_pids(state))
                grands_alive = [pid for pid in _grand_pids(state) if pid in handles["A"] and not jo.wait_dead(handles['A'][pid], 0)]
                return (child_gone and len(grands_alive) == 2), (
                    f"late assignment: server gone={child_gone}, grandchildren that escaped={len(grands_alive)} (expected 2)"
                )
            raise SystemExit(f"bad expectation {expect}")
        finally:
            if eng.poll() is None:
                eng.kill()
            cleanup(handles)


def _child_pids(state: str) -> set[int]:
    return {r["pid"] for r in read_reports(state) if r.get("event") == "child_up"}


def _grand_pids(state: str) -> list[int]:
    return [g for r in read_reports(state) if r.get("event") == "child_up" for g in r["grand"]]


def race_loop(strategy: str, n: int) -> tuple[int, int]:
    """How many of n servers had their immediate grandchild end up outside the job."""
    leaked: list[int] = []
    with jo.JobObject() as job:
        for _ in range(n):
            argv = [PY, SELF, "spawner"]
            if strategy == "assign_after":
                p = subprocess.Popen(argv, stdout=subprocess.PIPE, text=True)
                job.assign_pid(p.pid)
            else:
                p = jo.popen_in_job(job, argv, stdout=subprocess.PIPE, text=True)
            assert p.stdout is not None
            gpid = int(json.loads(p.stdout.readline())["grand"])
            if gpid not in job.process_ids():
                leaked.append(gpid)
        # leaving the with-block closes the only handle: everything in the job is killed
    for pid in leaked:
        try:
            h = jo.open_waitable(pid)
            jo.terminate_handle(h)
            jo.close_handle(h)
        except OSError:
            pass
    return len(leaked), n


CASES = [
    ("none", "exit", "survive"),
    ("assign_after", "exit", "dead"),
    ("assign_after", "kill", "dead"),
    ("suspended", "exit", "dead"),
    ("suspended", "kill", "dead"),
    ("self_assign", "exit", "dead"),
    ("self_assign", "kill", "dead"),
    ("late", "exit", "escape"),
    ("nested", "kill", "nested"),
]


def part_a() -> bool:
    ok = True
    print(f"Part A: Job Objects. python {sys.version.split()[0]}, base interpreter {PY}")
    print(f"  this process is already inside a job: {jo.current_process_in_any_job()}")
    for variant, mode, expect in CASES:
        try:
            passed, detail = run_case(variant, mode, expect)
        except Exception as exc:  # report, keep going
            passed, detail = False, f"error: {type(exc).__name__}: {exc}"
        print(f"  [{'PASS' if passed else 'FAIL'}] {variant:12s} engine {mode:4s} expect {expect:8s} {detail}")
        ok &= passed
    leaks, n = race_loop("assign_after", 40)
    print(f"  [INFO] plain Popen then assign: {leaks} of {n} immediate grandchildren escaped (Python start-up is slow;"
          " a native launcher is faster, so 0 does not prove safety)")
    leaks, n = race_loop("suspended", 40)
    passed = leaks == 0
    print(f"  [{'PASS' if passed else 'FAIL'}] suspended start: {leaks} of {n} grandchildren escaped (must be 0)")
    return ok and passed


def part_b() -> bool:
    import bench
    import check

    print("Part B: replay scenarios and journal overhead on this Windows runner")
    ok = check.run_all()
    with tempfile.TemporaryDirectory(prefix="s10-bench-") as d:
        print(bench.report(Path(d), 500, ["full", "mixed", "normal"]))
    return ok


def main() -> int:
    args = sys.argv[1:]
    roles = {
        "sleeper": lambda: role_sleeper(),
        "child": lambda: role_child(args[1], args[2]),
        "spawner": lambda: role_spawner(),
        "engine": lambda: role_engine(args[1], args[2], args[3]),
    }
    if args and args[0] in roles:
        roles[args[0]]()
        return 0
    if args and args[0] != "--no-replay":
        raise SystemExit(f"unknown argument {args[0]}")
    problems = jo.layout_selftest()
    if problems:
        print("structure layout problems:", problems)
        return 1
    if sys.platform != "win32":
        print("SKIPPED: windows_check.py runs on Windows only. This is NOT a Windows result.")
        return 0
    ok = part_a()
    if "--no-replay" not in sys.argv:
        ok = part_b() and ok
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
