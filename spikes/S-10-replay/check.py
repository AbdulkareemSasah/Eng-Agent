# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""S-10 spike check: the replay scenarios end to end. Exits non-zero on any failure.

    uv run --script spikes/S-10-replay/check.py [--keep DIR]

Crashes are real process deaths: a worker process is ended with os._exit at a chosen step and point (nothing flushed
or closed, as after SIGKILL), or killed from outside while a step runs. The fake host is a non-idempotent writer, so a
write that ran twice shows up as a duplicate in its ledger. See REPORT.md for what each scenario shows.
"""

import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bench  # noqa: E402
import jobobject  # noqa: E402
from engine import (  # noqa: E402
    Engine,
    RunLocked,
    ResolveError,
    ToolSpec,
    read_events,
    resolve_approval,
    resolve_in_flight,
)
from scenarios import BLOCKS, FOOTING_INPUT, VERSION, FakeHost  # noqa: E402

WORKER = str(HERE / "worker.py")
# The base interpreter, so that a killed worker is the interpreter itself and not a venv launcher in front of it.
PY = getattr(sys, "_base_executable", sys.executable)
STATE: dict[str, Any] = {}  # filled by the baseline scenario, used by later ones
EXPECTED_FRAMES = sorted(["F1", "F2", "P1", "P2", "F3"])
READ_TOOLS = ("read_model", "slow_read", "fail_read")


# --------------------------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------------------------


def worker(run_dir: Path, *args: str, env: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    e = dict(os.environ)
    e.update(env or {})
    p = subprocess.run([PY, WORKER, str(run_dir), *args], capture_output=True, text=True, timeout=120, env=e)
    out: dict[str, Any] = {}
    for line in reversed(p.stdout.splitlines()):
        if line.startswith("{"):
            out = json.loads(line)
            break
    if p.returncode not in (0, 10, 11, 12, 13, 86):
        raise AssertionError(f"worker exited {p.returncode}\nstdout: {p.stdout}\nstderr: {p.stderr}")
    return p.returncode, out


def drive(run_dir: Path, crash: str = "", crash_phase: int = 0, block: str = "footing", extra: tuple[str, ...] = ()) -> tuple[list[int], dict[str, Any]]:
    """Launch workers until the run completes: resolve approvals as the engineer would, crash once as asked."""
    codes: list[int] = []
    crashed = not crash
    pauses = 0
    out: dict[str, Any] = {}
    for _ in range(12):
        arm = (not crashed) and pauses == crash_phase
        args = list(extra) + ["--block", block] + (["--crash", crash] if arm else [])
        code, out = worker(run_dir, *args)
        codes.append(code)
        if code == 86:
            crashed = True
        elif code == 10:
            pauses += 1
            for p in out["pending"]:
                resolve_approval(run_dir, p["path"], True, p["shown_hash"])
        elif code == 0:
            return codes, out
        else:
            raise AssertionError(f"unexpected exit {code}: {out}")
    raise AssertionError(f"run did not finish: {codes}")


def host_of(run_dir: Path) -> FakeHost:
    return FakeHost(run_dir / "host")


def frames(run_dir: Path) -> list[str]:
    return sorted(r["name"] for r in host_of(run_dir).ledger_rows())


def call_count(run_dir: Path, tool: str, name: str | None = None) -> int:
    return sum(1 for r in host_of(run_dir).call_rows() if r["tool"] == tool and (name is None or r["args"].get("name") == name))


def run_inproc(run_dir: Path, block: str, inp: Any = None, version: str = VERSION, reconciler: bool = True, policy: str = "mixed") -> Any:
    host = host_of(run_dir)
    eng = Engine(run_dir, "run-001", host.tools(reconciler=reconciler), policy)
    return asyncio.run(eng.run(BLOCKS[block], FOOTING_INPUT if inp is None else inp, block, version))


def path_map(run_dir: Path) -> dict[str, tuple[str, str, str]]:
    """First attempt of every step: path -> (name, args_hash, op_id)."""
    m: dict[str, tuple[str, str, str]] = {}
    for e in read_events(run_dir):
        if e.type == "step_started" and e.path is not None:
            m.setdefault(e.path, (e.data["name"], e.data["args_hash"], e.data.get("op_id", "")))
    return m


def assert_eq(a: Any, b: Any, what: str) -> None:
    if a != b:
        raise AssertionError(f"{what}: {a!r} != {b!r}")


# --------------------------------------------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------------------------------------------


def sc_baseline(tmp: Path) -> str:
    d = tmp / "base"
    codes, out = drive(d)
    assert_eq(codes, [10, 0], "launch exit codes (pause for approval, resume)")
    assert_eq(frames(d), EXPECTED_FRAMES, "frames in the host ledger")
    evs = read_events(d)
    types = [e.type for e in evs]
    for t in ("run_started", "step_started", "step_completed", "step_failed", "approval_requested", "run_paused",
              "run_resumed", "approval_resolved", "run_completed"):
        assert t in types, f"missing event type {t}"
    assert_eq(types.count("run_started"), 1, "run_started count")
    approval_seq = next(e.seq for e in evs if e.type == "approval_requested")
    STATE["base_result"] = out["result"]
    STATE["steps"] = [
        (e.path, e.data["name"], e.data["effect"], e.seq > approval_seq)
        for e in evs
        if e.type == "step_started" and e.data["kind"] == "tool"
    ]
    STATE["base_calls"] = {t: call_count(d, t) for t in READ_TOOLS}
    STATE["base_path_map"] = path_map(d)
    resumed = [e for e in evs if e.type == "run_resumed"][0]
    return f"{len(evs)} events; {len(STATE['steps'])} tool steps; resume replayed {resumed.data['recorded_steps']} recorded steps"


def _expect_events(d: Path, path: str, effect: str, point: str) -> None:
    mine = [e for e in read_events(d) if e.path == path]
    types = [e.type for e in mine]
    started = [e for e in mine if e.type == "step_started"]
    rec = [e for e in mine if e.type == "step_reconciled"]
    if effect == "write" and point == "after_started":
        assert_eq(len(started), 2, f"{path}: started events (attempt 1 and the retry after not_applied)")
        assert rec and rec[0].data["outcome"] == "not_applied", f"{path}: expected reconciled not_applied"
        assert started[0].data["op_id"] != started[1].data["op_id"], "retry must carry a new op_id"
    elif effect == "write" and point == "after_effect":
        assert_eq(len(started), 1, f"{path}: started events")
        assert rec and rec[0].data["outcome"] == "applied", f"{path}: expected reconciled applied"
    elif effect == "write":
        assert_eq(len(started), 1, f"{path}: started events")
        assert not rec, f"{path}: nothing to reconcile at {point}"
    elif point in ("after_started", "after_effect"):
        assert "step_rerun" in types, f"{path}: an in-flight read is run again and says so"
    else:
        assert "step_rerun" not in types, f"{path}: unexpected rerun"


def _check_final(d: Path, label: str) -> None:
    assert_eq(frames(d), EXPECTED_FRAMES, f"{label}: frames (each exactly once)")
    for name in EXPECTED_FRAMES:
        assert_eq(call_count(d, "add_frame", name), 1, f"{label}: host calls of add_frame {name}")
    extra = 0
    for t in READ_TOOLS:
        n = call_count(d, t) - STATE["base_calls"][t]
        assert n in (0, 1), f"{label}: {t} ran {n} extra times"
        extra += n
    assert extra <= 1, f"{label}: more than one read re-run"
    assert_eq(path_map(d), STATE["base_path_map"], f"{label}: step identities (path, tool, args, op_id)")


def sc_crash_matrix(tmp: Path) -> str:
    n = 0
    for path, name, effect, post in STATE["steps"]:
        for point in ("before_started", "after_started", "after_effect", "after_completed"):
            label = f"crash {name}@{path}:{point}"
            d = tmp / ("m-" + path.replace("/", "_") + "-" + point)
            codes, out = drive(d, crash=f"{path}@{point}", crash_phase=1 if post else 0)
            assert 86 in codes, f"{label}: the crash did not happen ({codes})"
            assert_eq(out["result"], STATE["base_result"], f"{label}: final result")
            _check_final(d, label)
            _expect_events(d, path, effect, point)
            n += 1
    return f"{n} crash runs (every tool step x 4 points); each: writes exactly once, same result, same step identities"


def sc_nested(tmp: Path) -> str:
    ref = tmp / "nest-ref"
    codes, ref_out = drive(ref, block="nested_block")
    d = tmp / "nest-crash"
    codes, out = drive(d, crash="0/1@after_effect", block="nested_block")
    assert 86 in codes
    assert_eq(out["result"], ref_out["result"], "nested result")
    assert_eq(frames(d), ["N1", "N2", "N3"], "nested frames")
    done = run_inproc(d, "nested_block", {})
    assert_eq(done.status, "COMPLETED", "completed run is returned, not run again")
    assert_eq(call_count(d, "add_frame"), 3, "no host call when resuming a completed run")
    return "child block crashed inside, resumed; completed run returns its result without a call"


def sc_external_kill(tmp: Path) -> str:
    d = tmp / "ext"
    env = dict(os.environ)
    p = subprocess.Popen([PY, WORKER, str(d), "--block", "slow_block", "--no-reconciler"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    path = ""
    end = time.monotonic() + 30
    while time.monotonic() < end and not path:
        try:
            for e in read_events(d):
                if e.type == "step_started" and e.data["name"] == "slow_write":
                    path = e.path or ""
        except (sqlite3.Error, OSError):
            pass
        time.sleep(0.02)
    assert path, "the slow write never started"
    # while the first engine is alive a second one must be refused
    try:
        run_inproc(d, "slow_block")
        raise AssertionError("second engine on the same run was not refused")
    except RunLocked:
        pass
    p.kill()  # ends the process in the middle of the step (SIGKILL on POSIX, TerminateProcess on Windows)
    p.wait(timeout=30)
    p.stdout.close() if p.stdout else None
    p.stderr.close() if p.stderr else None
    assert_eq(frames(d), ["A"], "host applied only A when the process died")
    fast = {"S10_FAST": "1"}
    code, out = worker(d, "--block", "slow_block", "--no-reconciler", env=fast)
    assert_eq(code, 11, "resume without a reconciler must stop")
    code, out = worker(d, "--block", "slow_block", "--no-reconciler", env=fast)
    assert_eq(code, 11, "and keep stopping, not run the write")
    assert_eq(call_count(d, "slow_write"), 1, "in-flight write was never silently run again")
    assert_eq(out["pending"][0]["path"], path, "pending item names the in-flight step")
    for bad in ("0", "99"):
        try:
            resolve_in_flight(d, bad, "applied")
            raise AssertionError("resolve accepted a step that is not in flight")
        except ResolveError:
            pass
    resolve_in_flight(d, path, "not_applied")
    code, out = worker(d, "--block", "slow_block", "--no-reconciler", env=fast)
    assert_eq(code, 0, "after the engineer says not applied")
    assert_eq(frames(d), ["A", "B", "C"], "frames after resolve not_applied")
    assert_eq(call_count(d, "slow_write"), 2, "the retry is a second call with a new op_id")
    # with a reconciler the same situation resolves itself
    d2 = tmp / "ext2"
    p2 = subprocess.Popen([PY, WORKER, str(d2), "--block", "slow_block"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    end = time.monotonic() + 30
    started = False
    while time.monotonic() < end and not started:
        try:
            started = any(e.type == "step_started" and e.data["name"] == "slow_write" for e in read_events(d2))
        except (sqlite3.Error, OSError):
            pass
        time.sleep(0.02)
    p2.kill()
    p2.wait(timeout=30)
    p2.stdout.close() if p2.stdout else None
    p2.stderr.close() if p2.stderr else None
    code, out = worker(d2, "--block", "slow_block", env=fast)
    assert_eq(code, 0, "with reconciler")
    assert_eq(frames(d2), ["A", "B", "C"], "frames with reconciler")
    # engineer says applied after a crash that happened after the host applied the edit
    d3 = tmp / "ext3"
    code, _ = worker(d3, "--block", "slow_block", "--no-reconciler", "--crash", "1@after_effect", env=fast)
    assert_eq(code, 86, "crash after the host applied B")
    code, out = worker(d3, "--block", "slow_block", "--no-reconciler", env=fast)
    assert_eq(code, 11, "no reconciler: stop")
    row = host_of(d3).ledger_rows()[-1]
    resolve_in_flight(d3, "1", "applied", row["result"])
    code, out = worker(d3, "--block", "slow_block", "--no-reconciler", env=fast)
    assert_eq(code, 0, "after the engineer says applied")
    assert_eq(frames(d3), ["A", "B", "C"], "frames after resolve applied")
    assert_eq(call_count(d3, "slow_write"), 1, "applied: never run again")
    return "killed mid-step; second engine refused by the run lock; no silent re-run; resolved as applied / not applied / by reconciler"


def sc_divergence(tmp: Path) -> str:
    d = tmp / "div"
    code, out = worker(d)
    assert_eq(code, 10, "paused at approval")
    before = len(host_of(d).call_rows())
    limit_other = json.dumps({"limit_ref": "limits.other"})
    # label -> (block code, logical block name, version, input)
    variants = {
        "changed argument": ("v_args", "footing", "1", None),
        "different tool": ("v_tool", "footing", "1", None),
        "step inserted": ("v_insert", "footing", "1", None),
        "step removed": ("v_remove", "footing", "1", None),
        "parallel size changed": ("v_arity", "footing", "1", None),
        "approval preview changed": ("v_preview", "footing", "1", None),
        "block ends early (unconsumed journal)": ("v_short", "footing", "1", None),
        "same code, new version": ("footing", "footing", "2", None),
        "run input changed": ("footing", "footing", "1", limit_other),
        "other block name": ("footing", "other_block", "1", None),
    }
    for key, (block, name, version, inp) in variants.items():
        args = ["--block", block, "--name", name, "--version", version] + (["--input", inp] if inp else [])
        code, out = worker(d, *args)
        assert_eq(code, 12, f"{key}: ReplayDivergence")
        assert_eq(len(host_of(d).call_rows()), before, f"{key}: no tool was called")
        STATE.setdefault("div_detail", {})[key] = out["detail"]
    esc = [e for e in read_events(d) if e.type == "run_escalated" and e.data["code"] == "REPLAY_DIVERGENCE"]
    assert_eq(len(esc), len(variants), "each divergence is journaled as run_escalated")
    # an added tail after the frontier is NOT detected (documented limit); it is the block version that guards it
    code, out = worker(d, "--block", "v_tail", "--name", "footing")
    assert_eq(code, 10, "v_tail: same recorded prefix, extra steps later, is accepted")
    # divergence did not poison the run: the right block resumes it
    codes, out = drive(d)
    assert_eq(out["result"], STATE["base_result"], "resumed with the right block")
    assert_eq(frames(d), EXPECTED_FRAMES, "frames after recovery")
    return f"{len(variants)} changed blocks detected before any call; v_tail accepted (known limit); original block still resumes"


PACE_A = {"P0": 60, "P1": 10, "P2": 40, "P3": 0, "P4": 25}
PACE_B = {"P0": 0, "P1": 40, "P2": 60, "P3": 25, "P4": 10}


def _completion_order(d: Path) -> list[str]:
    return [e.path for e in read_events(d) if e.type == "step_completed" and e.path and e.path.count("/") == 2 and e.path.endswith("/0")]


def sc_parallel(tmp: Path) -> str:
    runs = {}
    for label, pace in (("A", PACE_A), ("B", PACE_B)):
        d = tmp / f"par-{label}"
        (d / "host").mkdir(parents=True)
        (d / "host" / "pace.json").write_text(json.dumps(pace))
        out = run_inproc(d, "par_block", {})
        assert_eq(out.status, "COMPLETED", f"par {label}")
        assert_eq([r[0]["frame"] for r in out.result["res"]], [f"P{i}" for i in range(5)], f"par {label}: results in argument order")
        runs[label] = d
    order_a, order_b = _completion_order(runs["A"]), _completion_order(runs["B"])
    assert order_a != order_b, "the two runs must complete in different orders for the test to mean anything"
    assert_eq(path_map(runs["A"]), path_map(runs["B"]), "step identities do not depend on completion order")
    # crash in the middle of the group: one child applied and recorded nothing, three more in flight
    d = tmp / "par-C"
    (d / "host").mkdir(parents=True)
    (d / "host" / "pace.json").write_text(json.dumps(PACE_A))
    code, _ = worker(d, "--block", "par_block", "--input", "{}", "--crash", "0/3/0@after_effect")
    assert_eq(code, 86, "crash inside the group")
    code, out = worker(d, "--block", "par_block", "--input", "{}")
    assert_eq(code, 0, "resume")
    assert_eq(frames(d), [f"P{i}" for i in range(5)], "each frame once after the crash")
    assert_eq(path_map(d), path_map(runs["A"]), "identities after the crash equal the uncrashed run")
    rec = {e.path: e.data["outcome"] for e in read_events(d) if e.type == "step_reconciled"}
    assert_eq(rec["0/3/0"], "applied", "the child that had applied")
    assert sum(1 for v in rec.values() if v == "not_applied") >= 1, "children that were in flight and had not applied"
    return f"completion order A {[p.split('/')[1] for p in order_a]} vs B {[p.split('/')[1] for p in order_b]}, identical identities; crash inside the group reconciled {len(rec)} in-flight writes"


def sc_approval(tmp: Path) -> str:
    d = tmp / "appr"
    code, out = worker(d)
    assert_eq(code, 10, "paused")
    p = out["pending"][0]
    code2, out2 = worker(d)
    assert_eq(code2, 10, "still paused when resumed before an answer")
    assert_eq(sum(1 for e in read_events(d) if e.type == "approval_requested"), 1, "the request is journaled once")
    for args in ((p["path"], True, "0" * 24), ("0", True, p["shown_hash"])):
        try:
            resolve_approval(d, *args)
            raise AssertionError("a wrong answer was accepted")
        except ResolveError:
            pass
    resolve_approval(d, p["path"], True, p["shown_hash"])
    try:
        resolve_approval(d, p["path"], False, p["shown_hash"])
        raise AssertionError("an approval was used twice")
    except ResolveError:
        pass
    code, out = worker(d)
    assert_eq(code, 0, "resumed in a new process after the answer")
    assert_eq(out["result"]["approved"], True, "approved")
    assert "F3" in frames(d)
    d2 = tmp / "rej"
    code, out = worker(d2)
    p = out["pending"][0]
    resolve_approval(d2, p["path"], False, p["shown_hash"])
    code, out = worker(d2)
    assert_eq(out["result"]["approved"], False, "rejected")
    assert_eq(frames(d2), sorted(["F1", "F2", "P1", "P2", "F3-rejected"]), "rejected path takes the other branch")
    return "pause, answer from another process, resume; wrong hash / reuse / non-approval refused; rejection branch"


def sc_rules(tmp: Path) -> str:
    out = run_inproc(tmp / "overlap", "overlap_block", {})
    assert out.status == "FAILED" and "BLOCK_RULE_VIOLATION" in out.detail, out
    # append-only journal
    j = sqlite3.connect(tmp / "base" / "journal.sqlite")
    for sql in ("UPDATE events SET type='x'", "DELETE FROM events"):
        try:
            j.execute(sql)
            raise AssertionError(f"{sql} succeeded")
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc), exc
    j.close()
    # live results pass through the journal codec, so a block sees the same value live and on replay
    async def tup(op_id: str) -> Any:
        return {"t": (1, 2)}

    seen: list[Any] = []

    async def blk(ctx: Any, inp: Any) -> Any:
        seen.append(await ctx.tool("tup"))
        await ctx.approve("stop", {})
        return {}

    d = tmp / "codec"
    for _ in range(2):
        asyncio.run(Engine(d, "run-001", {"tup": ToolSpec(tup, "read")}).run(blk, {}, "blk", "1"))
    assert_eq(seen, [{"t": [1, 2]}, {"t": [1, 2]}], "live and replayed result are the same value")
    # a lock the OS drops with the process: after the kill in sc_external_kill the run could be resumed (done there)
    return "overlapping steps refused; journal append-only (UPDATE and DELETE abort); live == replayed value"


def sc_overhead(tmp: Path) -> str:
    s = bench.step_overhead(tmp, "mixed", "write", 300)
    f = bench.fsync_cost(tmp, 100)
    assert s["p95"] < 20.0, f"p95 {s['p95']:.2f} ms is over the 20 ms target (11 section 10); raw fsync p50 {f['p50']:.2f} ms"
    return f"mixed policy, write step: p50 {s['p50']:.3f} ms, p95 {s['p95']:.3f} ms (target < 20 ms); raw append+fsync p50 {f['p50']:.3f} ms. Full table: bench.py"


def sc_layout(tmp: Path) -> str:
    problems = jobobject.layout_selftest()
    assert not problems, problems
    return "Win32 structure sizes match (48, 64, 144, 28 bytes); behavior on Windows: windows_check.py (pending)"


SCENARIOS: list[tuple[str, Callable[[Path], str]]] = [
    ("baseline run, pause, resume", sc_baseline),
    ("crash matrix", sc_crash_matrix),
    ("nested block, completed run", sc_nested),
    ("external kill, in-flight reconciliation, run lock", sc_external_kill),
    ("replay divergence", sc_divergence),
    ("parallel determinism", sc_parallel),
    ("approval pause and resume", sc_approval),
    ("rules: overlap, append-only, codec", sc_rules),
    ("engine overhead target", sc_overhead),
    ("job object structure layout", sc_layout),
]


def run_all(keep: str = "") -> bool:
    tmp = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="s10-check-"))
    tmp.mkdir(parents=True, exist_ok=True)
    print(f"S-10 check: python {sys.version.split()[0]} on {sys.platform}, scratch {tmp}")
    ok = True
    try:
        for name, fn in SCENARIOS:
            t = time.monotonic()
            try:
                detail = fn(tmp)
                print(f"[PASS] {name} ({time.monotonic() - t:.1f} s)\n       {detail}")
            except Exception as exc:
                ok = False
                import traceback

                print(f"[FAIL] {name} ({time.monotonic() - t:.1f} s)\n       {type(exc).__name__}: {exc}")
                traceback.print_exc(limit=4)
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)
    print("RESULT:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    k = sys.argv[sys.argv.index("--keep") + 1] if "--keep" in sys.argv else ""
    sys.exit(0 if run_all(k) else 1)
