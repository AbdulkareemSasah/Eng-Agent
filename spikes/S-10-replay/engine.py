"""S-10 spike: a minimal replay engine with an append-only SQLite journal.

Throwaway code (spike S-10, design/docs/architecture/19-roadmap-and-spikes.md section 2). Never ships.

A block is `async def block(ctx, inp)`. It talks to the world only through `ctx`. Every step gets a deterministic
path. After a crash or a pause the engine runs the block again from the start; a step whose path has a result in the
journal returns the recorded result, and execution continues live from the first step without one.

Standard library only.
"""

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------------------------------------------
# Errors. EngineStop derives from BaseException so that a block's `except Exception` cannot swallow a pause, a
# divergence or a reconciliation stop (the same reason asyncio.CancelledError is a BaseException).
# --------------------------------------------------------------------------------------------------------------


class EngineStop(BaseException):
    code = "ENGINE_STOP"

    def __init__(self, message: str = "", **info: Any) -> None:
        super().__init__(message)
        self.message = message
        self.info = info


class RunPaused(EngineStop):
    code = "RUN_PAUSED"


class ReplayDivergence(EngineStop):
    code = "REPLAY_DIVERGENCE"


class ReconciliationRequired(EngineStop):
    code = "NEEDS_RECONCILIATION"


class BlockRuleViolation(EngineStop):
    code = "BLOCK_RULE_VIOLATION"


class StepFailed(Exception):
    """A step ended with an error. Visible to the block, which may catch it. Replayed from the journal."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class ToolError(Exception):
    """Raised by a tool function for a definite failure (the call did not take effect)."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class RunLocked(Exception):
    pass


class ResolveError(Exception):
    pass


# --------------------------------------------------------------------------------------------------------------
# Canonical JSON and identifiers
# --------------------------------------------------------------------------------------------------------------


def canon(x: Any) -> str:
    return json.dumps(x, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(x: Any) -> str:
    return hashlib.sha256(canon(x).encode()).hexdigest()[:24]


def roundtrip(x: Any) -> Any:
    """Live results pass through the journal codec, so a block sees the same value live and on replay."""
    return json.loads(canon(x))


def make_op_id(run_id: str, path: str, attempt: int) -> str:
    """11 section 3: op_id is generated deterministically from run id, step path and attempt."""
    return "op-" + hashlib.sha256(f"{run_id}|{path}|{attempt}".encode()).hexdigest()[:24]


# --------------------------------------------------------------------------------------------------------------
# Journal
# --------------------------------------------------------------------------------------------------------------

# policy -> (journal_mode, synchronous for ordinary events, synchronous for durable events)
POLICIES: dict[str, tuple[str, str, str]] = {
    "full": ("WAL", "FULL", "FULL"),
    "mixed": ("WAL", "NORMAL", "FULL"),
    "normal": ("WAL", "NORMAL", "NORMAL"),
    "delete_full": ("DELETE", "FULL", "FULL"),
    "off": ("WAL", "OFF", "OFF"),
}

# Events whose loss after a power failure could make the engine act wrongly (re-run a write, ask again after an
# answer). Under the "mixed" policy these commits are synchronous=FULL, the rest NORMAL.
DURABLE_STEP_EFFECTS = ("write",)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events(
  seq   INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_ns INTEGER NOT NULL,
  type  TEXT NOT NULL,
  path  TEXT,
  data  TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'journal is append-only'); END;
"""


@dataclass
class Event:
    seq: int
    type: str
    path: str | None
    data: dict[str, Any]


class Journal:
    def __init__(self, path: Path, policy: str = "mixed") -> None:
        mode, base, durable = POLICIES[policy]
        self.policy = policy
        self.path = path
        self._base, self._durable = base, durable
        self.db = sqlite3.connect(str(path), isolation_level=None, timeout=30)  # autocommit: one INSERT = one commit
        self.db.execute(f"PRAGMA journal_mode={mode}").fetchone()
        self.db.executescript(_SCHEMA)
        self._sync = ""
        self._set_sync(base)

    def _set_sync(self, level: str) -> None:
        if level != self._sync:
            self.db.execute(f"PRAGMA synchronous={level}")
            self._sync = level

    def append(self, type_: str, path: str | None, data: dict[str, Any], durable: bool = False) -> int:
        self._set_sync(self._durable if durable else self._base)
        cur = self.db.execute(
            "INSERT INTO events(ts_ns, type, path, data) VALUES (?, ?, ?, ?)",
            (time.time_ns(), type_, path, canon(data)),
        )
        assert cur.lastrowid is not None
        return cur.lastrowid

    def events(self) -> list[Event]:
        rows = self.db.execute("SELECT seq, type, path, data FROM events ORDER BY seq").fetchall()
        return [Event(s, t, p, json.loads(d)) for s, t, p, d in rows]

    def close(self) -> None:
        self.db.close()


def read_events(run_dir: Path) -> list[Event]:
    """Read-only access for the approval page, reports and tests (a second connection, possibly another process).
    Opens the file read-only, so reading never creates or changes a journal."""
    db = sqlite3.connect(f"{(run_dir / 'journal.sqlite').resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    try:
        rows = db.execute("SELECT seq, type, path, data FROM events ORDER BY seq").fetchall()
    finally:
        db.close()
    return [Event(s, t, p, json.loads(d)) for s, t, p, d in rows]


# --------------------------------------------------------------------------------------------------------------
# Index of a journal: what replay needs
# --------------------------------------------------------------------------------------------------------------

CONTAINERS = ("parallel", "block")


@dataclass
class Rec:
    path: str
    kind: str  # tool | approve | parallel | block
    name: str
    args_hash: str
    effect: str  # read | write | none
    attempt: int = 1
    op_id: str = ""
    # started | completed | failed | not_applied | requested | approved | rejected
    state: str = "started"
    result: Any = None
    error: dict[str, str] | None = None
    consumed: bool = False


@dataclass
class RunIndex:
    started: dict[str, Any] | None = None
    terminal: Event | None = None
    recs: dict[str, Rec] = field(default_factory=dict)
    n_events: int = 0


def build_index(events: list[Event]) -> RunIndex:
    ix = RunIndex(n_events=len(events))
    for e in events:
        d = e.data
        if e.type == "run_started":
            ix.started = d
        elif e.type in ("run_completed", "run_failed"):
            ix.terminal = e
        elif e.type == "step_started":
            assert e.path is not None
            ix.recs[e.path] = Rec(
                e.path, d["kind"], d["name"], d["args_hash"], d["effect"], d.get("attempt", 1), d.get("op_id", "")
            )
        elif e.type == "step_completed":
            assert e.path is not None
            r = ix.recs[e.path]
            r.state, r.result = "completed", d.get("result")
        elif e.type == "step_failed":
            assert e.path is not None
            r = ix.recs[e.path]
            r.state, r.error = "failed", {"code": d["code"], "message": d.get("message", "")}
        elif e.type == "step_reconciled":
            assert e.path is not None
            r = ix.recs[e.path]
            if d["outcome"] == "applied":
                r.state, r.result = "completed", d.get("result")
            else:
                r.state = "not_applied"
        elif e.type == "approval_requested":
            assert e.path is not None
            ix.recs[e.path] = Rec(e.path, "approve", d["title"], d["args_hash"], "none", state="requested")
        elif e.type == "approval_resolved":
            assert e.path is not None
            r = ix.recs[e.path]
            r.state = "approved" if d["approved"] else "rejected"
    return ix


# --------------------------------------------------------------------------------------------------------------
# Single engine per run: an OS file lock, released by the OS when the process dies
# --------------------------------------------------------------------------------------------------------------


class RunLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def acquire(self) -> None:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise RunLocked(str(self.path)) from exc
        self.fd = fd

    def release(self) -> None:
        if self.fd is not None:
            os.close(self.fd)  # closing the descriptor drops the lock
            self.fd = None


# --------------------------------------------------------------------------------------------------------------
# Tools, the engine and the context
# --------------------------------------------------------------------------------------------------------------

ToolFn = Callable[..., Awaitable[Any]]  # async fn(op_id, **args) -> JSON-able result
ReconcileFn = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]  # (op_id, args) -> {"outcome", "result"?}


@dataclass
class ToolSpec:
    fn: ToolFn
    effect: str = "read"  # read | write
    reconcile: ReconcileFn | None = None


@dataclass
class ApprovalResult:
    approved: bool
    path: str


@dataclass
class Outcome:
    status: str  # COMPLETED | PAUSED | REPLAY_DIVERGENCE | NEEDS_RECONCILIATION | FAILED
    result: Any = None
    detail: str = ""
    pending: list[dict[str, Any]] = field(default_factory=list)
    replayed: int = 0
    live: int = 0


class Scope:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.n = 0
        self.busy = False

    def next_path(self) -> str:
        p = f"{self.prefix}/{self.n}" if self.prefix else str(self.n)
        self.n += 1
        return p


FaultFn = Callable[[str, str], None]


class Engine:
    def __init__(
        self,
        run_dir: Path,
        run_id: str,
        tools: dict[str, ToolSpec],
        policy: str = "mixed",
        faults: FaultFn | None = None,
    ) -> None:
        self.run_dir, self.run_id, self.tools, self.policy, self.faults = run_dir, run_id, tools, policy, faults
        run_dir.mkdir(parents=True, exist_ok=True)
        self.journal: Journal
        self.ix = RunIndex()
        self.replayed = 0
        self.live = 0
        self.pending_pauses: list[dict[str, Any]] = []

    def hit(self, point: str, path: str) -> None:
        if self.faults:
            self.faults(point, path)

    async def run(
        self,
        block: Callable[["Ctx", Any], Awaitable[Any]],
        inp: Any,
        block_name: str,
        block_version: str,
    ) -> Outcome:
        lock = RunLock(self.run_dir / "run.lock")
        lock.acquire()
        self.journal = Journal(self.run_dir / "journal.sqlite", self.policy)
        try:
            return await self._run(block, inp, block_name, block_version)
        finally:
            self.journal.close()
            lock.release()

    async def _run(self, block: Any, inp: Any, block_name: str, block_version: str) -> Outcome:
        self.ix = build_index(self.journal.events())
        ix = self.ix
        if ix.terminal is not None and ix.terminal.type == "run_completed":
            return Outcome("COMPLETED", ix.terminal.data["result"])
        head = {"run_id": self.run_id, "block": block_name, "version": block_version, "input_hash": digest(inp)}
        try:
            if ix.started is None:
                self.journal.append("run_started", None, {**head, "input": inp}, durable=True)
            else:
                for k, v in head.items():
                    if ix.started.get(k) != v:
                        raise ReplayDivergence(f"run header differs in {k}", expected=ix.started.get(k), got=v)
                self.journal.append("run_resumed", None, {"recorded_steps": len(ix.recs)})
            result = await block(Ctx(self, Scope("")), inp)
            result = roundtrip(result)
            unconsumed = sorted(p for p, r in ix.recs.items() if not r.consumed)
            if unconsumed:
                raise ReplayDivergence("journal has steps the block did not call", paths=unconsumed)
            self.journal.append("run_completed", None, {"result": result}, durable=True)
            return Outcome("COMPLETED", result, replayed=self.replayed, live=self.live)
        except RunPaused as e:
            self.journal.append("run_paused", None, {"pending": e.info.get("pending", [])})
            return Outcome("PAUSED", pending=e.info.get("pending", []), replayed=self.replayed, live=self.live)
        except ReplayDivergence as e:
            # Not terminal: the journal is untouched, so reverting the block makes the run resumable again.
            self.journal.append("run_escalated", None, {"code": e.code, "detail": e.message, "info": e.info})
            return Outcome("REPLAY_DIVERGENCE", detail=e.message, replayed=self.replayed, live=self.live)
        except ReconciliationRequired as e:
            self.journal.append("run_escalated", None, {"code": e.code, "detail": e.message, "info": e.info})
            return Outcome("NEEDS_RECONCILIATION", detail=e.message, pending=[e.info], replayed=self.replayed)
        except BlockRuleViolation as e:
            self.journal.append("run_failed", None, {"code": e.code, "detail": e.message})
            return Outcome("FAILED", detail=f"{e.code}: {e.message}")
        except StepFailed as e:
            self.journal.append("run_failed", None, {"code": e.code, "detail": e.message})
            return Outcome("FAILED", detail=f"{e.code}: {e.message}")
        except Exception as e:  # a bug in the block
            self.journal.append("run_failed", None, {"code": "BLOCK_EXCEPTION", "detail": type(e).__name__})
            return Outcome("FAILED", detail=f"BLOCK_EXCEPTION: {type(e).__name__}: {e}")


class Ctx:
    def __init__(self, engine: Engine, scope: Scope) -> None:
        self.e, self.scope = engine, scope

    # ---- scope bookkeeping: one step at a time per scope; concurrency only through ctx.parallel -------------

    def _begin(self) -> str:
        if self.scope.busy:
            raise BlockRuleViolation("overlapping steps in one scope; use ctx.parallel for concurrency")
        self.scope.busy = True
        return self.scope.next_path()

    def _end(self) -> None:
        self.scope.busy = False

    def _match(self, path: str, kind: str, name: str, args_hash: str) -> Rec | None:
        rec = self.e.ix.recs.get(path)
        if rec is None:
            return None
        if (rec.kind, rec.name, rec.args_hash) != (kind, name, args_hash):
            raise ReplayDivergence(
                f"step {path} differs from the journal",
                path=path,
                recorded={"kind": rec.kind, "name": rec.name, "args_hash": rec.args_hash},
                replayed={"kind": kind, "name": name, "args_hash": args_hash},
            )
        rec.consumed = True
        return rec

    # ---- ctx.tool --------------------------------------------------------------------------------------------

    async def tool(self, name: str, /, **args: Any) -> Any:
        spec = self.e.tools.get(name)
        if spec is None:
            raise BlockRuleViolation(f"unknown tool {name}")
        path = self._begin()
        try:
            return await self._tool(path, name, spec, args)
        finally:
            self._end()

    async def _tool(self, path: str, name: str, spec: ToolSpec, args: dict[str, Any]) -> Any:
        e = self.e
        ah = digest(args)
        rec = self._match(path, "tool", name, ah)
        attempt = 1
        if rec is not None:
            if rec.state == "completed":
                e.replayed += 1
                return rec.result
            if rec.state == "failed":
                e.replayed += 1
                assert rec.error is not None
                raise StepFailed(rec.error["code"], rec.error["message"])
            if rec.state == "started":  # in flight when the process died
                if rec.effect == "write":
                    outcome, result = await self._reconcile(rec, spec, args)
                    if outcome == "applied":
                        e.replayed += 1
                        return result
                    attempt = rec.attempt + 1
                else:  # a read has no side effect: safe to run again
                    e.journal.append("step_rerun", path, {"reason": "read in flight"})
                    attempt = rec.attempt
            elif rec.state == "not_applied":
                attempt = rec.attempt + 1
        op_id = make_op_id(e.run_id, path, attempt)
        e.hit("before_started", path)
        e.journal.append(
            "step_started",
            path,
            {"kind": "tool", "name": name, "args": args, "args_hash": ah, "effect": spec.effect, "attempt": attempt, "op_id": op_id},
            durable=spec.effect in DURABLE_STEP_EFFECTS,
        )
        e.hit("after_started", path)
        e.live += 1
        try:
            raw = await spec.fn(op_id, **args)
        except ToolError as exc:
            e.hit("after_effect", path)
            e.journal.append("step_failed", path, {"code": exc.code, "message": exc.message})
            e.hit("after_completed", path)
            raise StepFailed(exc.code, exc.message) from exc
        except Exception as exc:
            if spec.effect == "write":
                # timeout or crash inside a write: outcome unknown. The step stays in flight (never retried here).
                raise ReconciliationRequired(f"{type(exc).__name__} during write {path}", path=path, op_id=op_id) from exc
            e.journal.append("step_failed", path, {"code": "UNEXPECTED", "message": type(exc).__name__})
            raise StepFailed("UNEXPECTED", type(exc).__name__) from exc
        e.hit("after_effect", path)
        result = roundtrip(raw)
        e.journal.append("step_completed", path, {"result": result})
        e.hit("after_completed", path)
        return result

    async def _reconcile(self, rec: Rec, spec: ToolSpec, args: dict[str, Any]) -> tuple[str, Any]:
        """A write that was in flight. Ask the host (reconcile_operation); never run it again unreconciled."""
        info = {"path": rec.path, "tool": rec.name, "op_id": rec.op_id, "attempt": rec.attempt}
        if spec.reconcile is None:
            raise ReconciliationRequired(f"write {rec.path} was in flight and no reconciler exists", **info)
        r = await spec.reconcile(rec.op_id, args)
        outcome = r.get("outcome")
        if outcome not in ("applied", "not_applied"):
            raise ReconciliationRequired(f"write {rec.path} was in flight; the host cannot tell", **info)
        result = roundtrip(r.get("result"))
        self.e.journal.append(
            "step_reconciled", rec.path, {"outcome": outcome, "result": result, "by": "reconcile_operation"}, durable=True
        )
        return outcome, result

    # ---- ctx.approve -----------------------------------------------------------------------------------------

    async def approve(self, title: str, preview: Any) -> ApprovalResult:
        path = self._begin()
        try:
            e = self.e
            ah = digest({"title": title, "preview": preview})
            rec = self._match(path, "approve", title, ah)
            if rec is None:
                e.journal.append(
                    "approval_requested", path, {"title": title, "preview": preview, "args_hash": ah}, durable=True
                )
                rec = e.ix.recs[path] = Rec(path, "approve", title, ah, "none", state="requested", consumed=True)
            if rec.state == "requested":
                raise RunPaused("waiting for approval", pending=[{"kind": "approval", "path": path, "shown_hash": ah}])
            e.replayed += 1
            return ApprovalResult(rec.state == "approved", path)
        finally:
            self._end()

    # ---- ctx.parallel ----------------------------------------------------------------------------------------

    async def parallel(self, *thunks: Callable[["Ctx"], Awaitable[Any]]) -> list[Any]:
        """Run independent steps concurrently. Child i gets scope `<path>/<i>`, so its step paths depend on the
        argument position only, never on completion order. Results come back in argument order."""
        path = self._begin()
        try:
            e = self.e
            ah = digest({"n": len(thunks)})
            if self._match(path, "parallel", "", ah) is None:
                e.journal.append("step_started", path, {"kind": "parallel", "name": "", "args": {"n": len(thunks)}, "args_hash": ah, "effect": "none"})
                e.ix.recs[path] = Rec(path, "parallel", "", ah, "none", consumed=True)

            async def child(i: int, t: Callable[[Ctx], Awaitable[Any]]) -> tuple[str, Any]:
                try:
                    return "ok", await t(Ctx(e, Scope(f"{path}/{i}")))
                except (Exception, EngineStop) as exc:
                    return "err", exc

            done = await asyncio.gather(*(child(i, t) for i, t in enumerate(thunks)))
            errors = [x for tag, x in done if tag == "err"]
            if errors:
                # Deterministic priority (lowest child index first within a class), independent of completion order.
                for cls in (ReplayDivergence, BlockRuleViolation, ReconciliationRequired, StepFailed):
                    for x in errors:
                        if isinstance(x, cls):
                            raise x
                pauses = [x for x in errors if isinstance(x, RunPaused)]
                if pauses:
                    pending = [p for x in pauses for p in x.info.get("pending", [])]
                    raise RunPaused("waiting for approval", pending=pending)
                raise errors[0]
            e.journal.append("step_completed", path, {})
            return [x for _, x in done]
        finally:
            self._end()

    # ---- ctx.block -------------------------------------------------------------------------------------------

    async def block(self, fn: Callable[["Ctx", Any], Awaitable[Any]], inp: Any) -> Any:
        path = self._begin()
        try:
            e = self.e
            name = fn.__name__
            ah = digest(inp)
            if self._match(path, "block", name, ah) is None:
                e.journal.append("step_started", path, {"kind": "block", "name": name, "args": inp, "args_hash": ah, "effect": "none"})
                e.ix.recs[path] = Rec(path, "block", name, ah, "none", consumed=True)
            result = roundtrip(await fn(Ctx(e, Scope(path)), inp))
            e.journal.append("step_completed", path, {"result": result})
            return result
        finally:
            self._end()


# --------------------------------------------------------------------------------------------------------------
# Resolution API for the approval page and the reconciliation screen: separate process, no engine running
# --------------------------------------------------------------------------------------------------------------


def resolve_approval(run_dir: Path, path: str, approved: bool, shown_hash: str, by: str = "engineer") -> None:
    """Record the engineer's answer. Bound to the hash of what was shown; used once."""
    j = Journal(run_dir / "journal.sqlite", "mixed")
    try:
        ix = build_index(j.events())
        rec = ix.recs.get(path)
        if rec is None or rec.kind != "approve":
            raise ResolveError(f"no approval at {path}")
        if rec.state != "requested":
            raise ResolveError(f"approval at {path} is already {rec.state}")
        if rec.args_hash != shown_hash:
            raise ResolveError("the answer is bound to a different preview than the one requested")
        j.append("approval_resolved", path, {"approved": approved, "shown_hash": shown_hash, "by": by}, durable=True)
    finally:
        j.close()


def resolve_in_flight(run_dir: Path, path: str, outcome: str, result: Any = None, by: str = "engineer") -> None:
    """The engineer (or a tool that read the model) decides what happened to a write that was in flight."""
    if outcome not in ("applied", "not_applied"):
        raise ResolveError(outcome)
    j = Journal(run_dir / "journal.sqlite", "mixed")
    try:
        ix = build_index(j.events())
        rec = ix.recs.get(path)
        if rec is None or rec.state != "started" or rec.effect != "write":
            raise ResolveError(f"no write in flight at {path}")
        j.append("step_reconciled", path, {"outcome": outcome, "result": roundtrip(result), "by": by}, durable=True)
    finally:
        j.close()
