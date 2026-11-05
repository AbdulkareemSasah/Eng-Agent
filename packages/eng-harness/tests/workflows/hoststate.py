"""Helpers of the in-flight and host-state replay tests (plan 0001 T11b, T11c; spec 0001 AC31 to AC34, AC63, AC64).

Test doubles, never shipped. The stop points of these tests (a write cut off between its start and its end, a host that
lost its models, a model reopened in another instance) are not reachable through the public API, so `forge` writes the
journal of such a run by hand, event by event, and the test resumes it with a real engine. `ScriptedHost` is the rig's
fake host with a log of the calls that name a model or an instance, a reconciler that can be absent or fail, a
read-back that can answer, fail or raise, and a `restore` whose units can be made to differ. No clock, network or host
program.
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from fakes.ports import ENVELOPE, failure
from pydantic import JsonValue

from eng_harness.block import BlockDef
from eng_harness.journal import Event, EventType, JournalWriter
from eng_harness.ports import (
    HostInstance,
    HostModelState,
    InputAnswer,
    InputRequest,
    Reconciliation,
    SavedModel,
    UnitsState,
)
from workflows.rig import Host, Rig, make_rig

T = EventType
AT = "2026-01-01T00:10:00.000Z"
INSTANCE = HostInstance(instance_id="csi-1", pid=4242, process_started_at=AT, program="csi")
REOPENED = HostInstance(instance_id="csi-2", pid=4243, process_started_at=AT, program="csi")
REF = "res_" + "1" * 26
OP = "op_" + "a" * 32  # the op_id of a forged write: the engine takes it from the journal as it is
Forged = tuple[EventType, str | None, int | None, dict[str, Any]]
"""An event to write: type, step path, attempt and payload."""


class ScriptedHost(Host):
    """The rig's fake host with a call log, an optional reconciler and a `restore` with scripted units."""

    def __init__(self, ids: SeededIdSource, clock: FixedClock, runs_dir: Path) -> None:
        """Serve the rig's tools; `calls` gets (method, key, instance id) for the calls that name a model."""
        super().__init__(ids, clock, runs_dir)
        self.calls: list[tuple[str, str, str | None]] = []
        self.unsupported: set[str] = set()
        self.reconcile_error: ContractError | None = None
        self.restored_units: UnitsState | None = None
        self.in_place = False
        self.read_back_reply: ENVELOPE | ContractError | None = None  # None: the adapter has no read-back
        self.reconciled_args: list[Mapping[str, JsonValue]] = []

    def supports_reconcile(self, tool: str) -> bool:
        """False for the tools in `unsupported`, else as the fake host."""
        return tool not in self.unsupported and super().supports_reconcile(tool)

    async def reconcile(self, tool: str, args: Mapping[str, JsonValue], op_id: str) -> Reconciliation:
        """Log the call, raise `reconcile_error` when set, else behave as the fake host."""
        self.calls.append(("reconcile", op_id, None))
        self.reconciled_args.append(dict(args))
        if self.reconcile_error is not None:
            raise self.reconcile_error
        return await super().reconcile(tool, args, op_id)

    async def read_back(self, tool: str, args: Mapping[str, JsonValue]) -> ENVELOPE | None:
        """`read_back_reply`: returned as it is, or raised when it is an error; None means no read-back."""
        if isinstance(self.read_back_reply, ContractError):
            raise self.read_back_reply
        return self.read_back_reply

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> Any:
        """Log the call, then behave as the rig's host."""
        self.calls.append(("call", tool, model))
        return await super().call(tool, args, op_id=op_id, model=model)

    async def locate(self, model_key: str) -> HostInstance | None:
        """Log the call, then behave as the fake host."""
        self.calls.append(("locate", model_key, None))
        return await super().locate(model_key)

    async def read_units(self, model_key: str, instance_id: str) -> UnitsState:
        """Log the call with the instance it names, then behave as the fake host."""
        self.calls.append(("read_units", model_key, instance_id))
        return await super().read_units(model_key, instance_id)

    async def model_state(self, model_key: str, instance_id: str) -> HostModelState:
        """Log the call with the instance it names, then behave as the fake host."""
        self.calls.append(("model_state", model_key, instance_id))
        return await super().model_state(model_key, instance_id)

    async def restore(self, model_key: str, saved: SavedModel) -> HostInstance:
        """Log the call; the units of the restored model are `restored_units` when set."""
        self.calls.append(("restore", model_key, None))
        if self.in_place:  # the instance that holds the model still runs: the saved state returns in it
            self.models[model_key] = HostModelState(
                loaded=True,
                model_id=saved.model_id,
                revision=saved.revision,
                fingerprint=saved.fingerprint,
                file_sha256=saved.file_sha256,
            )
            return next(i for group in self.instances.values() for i in group if i.instance_id == self.bound[model_key])
        instance = await super().restore(model_key, saved)
        if self.restored_units is not None:
            self.units[model_key] = self.restored_units
        return instance


def scripted_rig(root: Path) -> tuple[Rig, ScriptedHost]:
    """A rig whose host is a `ScriptedHost`, and that host."""
    rig = make_rig(root)
    host = ScriptedHost(rig.ids, rig.clock, rig.workspace.root / "runs")
    return replace(rig, host=host), host


def start(path: str, tool: str, args: Mapping[str, JsonValue], *, attempt: int = 1, write: bool = False) -> Forged:
    """The `step_started` of a tool step (a write step has an `op_id` and the model named by `args["model"]`)."""
    model = args.get("model")
    body = {
        "kind": "tool", "name": tool, "args": dict(args), "args_sha256": payload_sha256(dict(args)),
        "effect": "write" if write else "read", "op_id": OP if write else None, "host_key": "csi",
        "model_key": model if isinstance(model, str) else None,
    }  # fmt: skip
    return T.STEP_STARTED, path, attempt, body


def done(path: str, *, attempt: int = 1, ref: str = REF) -> Forged:
    """The `step_completed` of a step whose result is `ref`."""
    result = {"ref": ref, "summary": {}, "warnings": [], "complete": True}
    return T.STEP_COMPLETED, path, attempt, {"result": result, "duration_ms": 0}


def failed(path: str, *, attempt: int = 1) -> Forged:
    """The `step_failed` of a step with a retryable failure."""
    error = failure(ErrorCode.HOST_BUSY).error.model_dump(mode="json")
    return T.STEP_FAILED, path, attempt, {"error": error, "retryable": True, "duration_ms": 0}


def bound(model: str, instance: HostInstance, reason: str = "first_use") -> Forged:
    """The `model_bound` event that binds `model` to `instance`."""
    body = {"model_key": model, "host_key": "csi", "instance_id": instance.instance_id, "reason": reason}
    return T.MODEL_BOUND, None, None, body | {"file_names": [f"{model}.edb"]}


def saved(rig: Rig, model: str, role: str = "working_copy") -> Forged:
    """The `model_saved` event for the model as the host holds it now (the host saves it)."""
    model_saved = asyncio.run(rig.host.save(model, role))
    return T.MODEL_SAVED, None, None, {"model_key": model, **model_saved.model_dump(mode="json"), "role": role}


def forge(rig: Rig, workflow: BlockDef[Any, Any], *events: Forged) -> str:
    """A run folder with the header of a run of `workflow` and then `events`; the run's id."""
    run_id = rig.forge(workflow)
    writer = JournalWriter(rig.run_dir(run_id), rig.store, rig.clock, rig.ids)
    for kind, path, attempt, body in events:
        writer.append(kind, body, path=path, attempt=attempt)
    writer.close()
    return run_id


def resume(rig: Rig, workflow: BlockDef[Any, Any], run_id: str) -> Any:
    """Resume the run with a new engine, as a new process would; its `RunOutcome`."""
    return asyncio.run(rig.engine(workflow).resume(run_id))


def trace(
    rig: Rig, run_id: str, after: int = 0, *, housekeeping: bool = False
) -> list[tuple[str, str | None, int | None]]:
    """(type, path, attempt) of the events after the first `after`; the `@resume` steps only when asked for."""
    events: Sequence[Event] = rig.events(run_id)[after:]
    return [(e.type.value, e.path, e.attempt) for e in events if housekeeping or not (e.path or "").startswith("@")]


def answer(asked: InputRequest, choice: str, question: str, *, by: str = "engineer:test") -> InputAnswer:
    """The answer `choice` to the question `question` of `asked`."""
    return InputAnswer(
        request_id=asked.request_id, shown_sha256=asked.fields_schema_sha256, choices={question: choice}, by=by
    )


def options(asked: InputRequest, question: str) -> list[str]:
    """The option values of one question of a choice request."""
    props: Any = asked.fields_schema["properties"]
    return list(props[question]["enum"])
