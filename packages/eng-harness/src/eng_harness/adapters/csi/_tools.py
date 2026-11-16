"""The CSI `ToolPort` over the edit, analysis, design and result tools (plan 0002 T12, T13; spec 0002 4.5.2 to 4.6.3).

A `token` tool passes the units token whose units make its conversion simplest (spec 4.5.4): `kN_mm_C` for the wall
thickness, `kN_m_C` for the loads and the force results (spec 4.6.1, 4.6.3). The framework fixes one token per
binding, so the token of the tool being called, from its descriptor, is put on the binding here.

Analysis and design are `long`-class tools: the framework sends them to the `long` role (its own call timeout) and
their `action` makes the engine save the model first (engine invariant 7).

Each write is recorded for the read-back (plan 0002 T12b): the wrapped builder, which sees the canonical model and the
binding before the send, prepares the item; a successful reply commits it and marks the write on the host port, so the
fingerprint change is not an outside edit; a failed call records nothing (an unknown outcome is T14's reconciliation).

Adapter-local tools (plan 0007 T5; spec 0007 4.10) are defined here, not in the allowlist file, whose names the build
check compares with the server's tool list: the reads of `_read_state_tool.py`, `csi_open_revision` and `csi_save_model`
with `as_new_revision` (`_revisions.py`). Each composes allowlisted host tools; `csi_open_model` is allowlisted for
`csi_open_revision` alone, so the port refuses it by name. With `Revisions` wired, the open file is read before every
write but an open: a snapshot is never written. A save or restore a timeout cut off is not reconciled: the engineer
decides. The summary of a snapshot save and of a restore carries `saved_file` (`name`, `sha256`).
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

from eng_contract.envelope import Envelope, SuccessEnvelope, make_failure
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.params import ParamModel
from pydantic import BaseModel, Field, JsonValue

from eng_harness.adapters._allowlist import Allowlist
from eng_harness.adapters._args import validate_call
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._envelope import make_envelope
from eng_harness.adapters._toolport import AdapterToolPort, Binding, Builder, ModelBinder, Reader
from eng_harness.adapters.csi import _replies, csi_allowlist
from eng_harness.adapters.csi._checks import WrittenItems
from eng_harness.adapters.csi._edits import EDIT_BUILDERS, EDIT_MODELS
from eng_harness.adapters.csi._read_state_tool import READ_TOOLS, ModelArgs
from eng_harness.adapters.csi._revisions import CsiToolInfo, OpenRevisionArgs, Revisions, SavedFile, SaveModelArgs
from eng_harness.errors import ToolFailed
from eng_harness.ports import ToolInfo
from eng_harness.servers import CallEffect

__all__ = ["READERS", "TOKENS", "CsiToolPort", "tool_allowlist"]

TOKENS = {  # spec 4.6.2 and 4.6.3
    "csi_define_wall_section": "kN_mm_C",
    "csi_set_frame_load_distributed": "kN_m_C",
    "csi_set_area_load_uniform": "kN_m_C",
    "csi_results_joint_reactions": "kN_m_C",
    "csi_results_frame_forces": "kN_m_C",
    "csi_results_story_drifts": "kN_m_C",
}


DesignKind = Literal["steel", "concrete", "aluminum", "coldformed"]  # the host rejects the last two (S-12 1)


class _ModelArgs(ParamModel):
    """`csi_run_analysis` (synchronous, `long` role) and `csi_analysis_status`: the whole model."""

    model: str


class DesignRunArgs(ParamModel):
    """`csi_design_run`: one design kind (`long` role)."""

    model: str
    kind: DesignKind


class DesignResultsArgs(ParamModel):
    """`csi_design_results`: the rows of a design kind already run; `name` is one member, `limit` the host's cap."""

    model: str
    kind: DesignKind
    name: str | None = None
    limit: int = Field(default=2000, ge=1, le=2000)


class _ResultsArgs(_ModelArgs):
    """`csi_results_story_drifts` (ETABS only): load case and combination names, the host's `cases` and `combos`."""

    cases: list[str] = Field(default_factory=list)
    combos: list[str] = Field(default_factory=list)


class _ObjectResultsArgs(_ResultsArgs):
    """`csi_results_joint_reactions` and `csi_results_frame_forces`; `object` is one joint or frame, else all."""

    object: str | None = None


class OpenModelArgs(ParamModel):
    """`csi_open_model`, reached only by `csi_open_revision` (the port refuses it by name): the file to open."""

    model: str
    path: str


def _local(name: str, args_model: str, *, write: bool) -> ToolDescriptor:
    return ToolDescriptor(
        name=name, kind="write" if write else "read", timeout_class="call", effect="write" if write else "read",
        action="open" if write else "plain", args_model=args_model, units="none", confirm="never",
        readback="model_file" if write else None, products=("ETABS",),
    )  # fmt: skip


LOCAL_TOOLS = (  # adapter-local (spec 0007 4.10): not in the server's tool list, so not in the allowlist file
    _local("csi_read_model_state", "ModelArgs", write=False),
    _local("csi_read_analysis_messages", "ModelArgs", write=False),
    _local("csi_open_revision", "OpenRevisionArgs", write=True),
)
SESSION_TOOLS = frozenset({"csi_save_model", "csi_open_model"})  # allowlisted; their canonical arguments are below
_UNRECONCILED = SESSION_TOOLS | {"csi_open_revision"}

ANALYSIS_MODELS: dict[str, type[ParamModel]] = {  # by the allowlist's `args_model`
    "RunAnalysisArgs": _ModelArgs,
    "AnalysisStatusArgs": _ModelArgs,
    "DesignRunArgs": DesignRunArgs,
    "DesignResultsArgs": DesignResultsArgs,
    "ResultsJointReactionsArgs": _ObjectResultsArgs,
    "ResultsFrameForcesArgs": _ObjectResultsArgs,
    "ResultsStoryDriftsArgs": _ResultsArgs,
    "ModelArgs": ModelArgs,
    "OpenRevisionArgs": OpenRevisionArgs,
    "SaveModelArgs": SaveModelArgs,
    "OpenModelArgs": OpenModelArgs,
}


def _reader(mapper: Callable[[Mapping[str, Any], Binding], BaseModel]) -> Reader:
    def read(reply: Mapping[str, JsonValue], binding: Binding) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
        return mapper(reply, binding).model_dump(mode="json"), {}

    return read


READERS: dict[str, Reader] = {  # the host tool to its stored kind (spec 4.6.1); the units token is the binding's
    "csi_run_analysis": _reader(lambda r, b: _replies.analysis_run(r)),
    "csi_analysis_status": _reader(lambda r, b: _replies.analysis_status(r)),
    "csi_design_run": _reader(lambda r, b: _replies.design_run(r)),
    "csi_design_results": _reader(lambda r, b: _replies.design_results(r)),
    "csi_results_joint_reactions": _reader(lambda r, b: _replies.joint_reactions(r, b.units_system or "")),
    "csi_results_frame_forces": _reader(lambda r, b: _replies.member_forces(r, b.units_system or "")),
    "csi_results_story_drifts": _reader(lambda r, b: _replies.story_drifts(r, b.units_system or "")),
}


def tool_allowlist() -> Allowlist:
    """The packaged CSI allowlist reduced to the edit tools of spec 4.6.2, the analysis, design and result tools and the
    session tools of `SESSION_TOOLS`, plus the adapter-local `LOCAL_TOOLS`."""
    full = csi_allowlist()
    kept = EDIT_BUILDERS | READERS.keys() | SESSION_TOOLS
    return full.model_copy(update={"tools": (*(t for t in full.tools if t.name in kept), *LOCAL_TOOLS)})


class _TokenBinder:
    """The adapter's binder with the units token of the tool being called."""

    def __init__(self, inner: ModelBinder) -> None:
        self._inner = inner

    async def binding(self, host_key: str, model: str | None, descriptor: ToolDescriptor) -> Binding:
        bound = await self._inner.binding(host_key, model, descriptor)
        token = TOKENS.get(descriptor.name)
        return bound if token is None else bound.model_copy(update={"units_system": token})

    def revision(self, model_id: str) -> int | None:
        return self._inner.revision(model_id)


def _noting(build: Builder, written: WrittenItems) -> Builder:
    def run(model: ParamModel, descriptor: ToolDescriptor, binding: Binding) -> dict[str, JsonValue]:
        sent = build(model, descriptor, binding)  # a gap or a bad argument is raised here, before anything is noted
        written.prepare(model)
        return sent

    return run


class CsiToolPort(AdapterToolPort):
    """`AdapterToolPort` over `tool_allowlist()` and its argument models, builders, readers; `wiring` as its parameters.

    `written` is the book that `AdapterHostPort.check_model` reads (its `ReadBack`) and `wrote` is the host port's; a
    port made without them records into a book nobody reads. `revisions` holds the run's snapshots: without it
    `csi_open_revision` and a save `as_new_revision` are refused with `INTERNAL` and writes are not checked. `reopened`
    is the host port's (`AdapterHostPort.reopened`): called with the model key and the new working file after a
    successful `csi_open_revision` only.
    """

    def __init__(
        self, *, binder: ModelBinder, written: WrittenItems | None = None, wrote: Callable[[str], None] | None = None,
        revisions: Revisions | None = None, reopened: Callable[[str, Path], None] | None = None, **wiring: Any,
    ) -> None:  # fmt: skip
        self._written, self._wrote, self._revisions = written or WrittenItems(), wrote or (lambda key: None), revisions
        self._reopened = reopened or (lambda key, path: None)
        builders: dict[str, Builder] = {tool: _noting(build, self._written) for tool, build in EDIT_BUILDERS.items()}
        builders["csi_save_model"] = (
            lambda model, descriptor, binding: {}
        )  # the open file in place; no `as_new_revision`
        super().__init__(
            allowlist=tool_allowlist(), arg_models=EDIT_MODELS | ANALYSIS_MODELS, builders=builders, readers=READERS,
            binder=_TokenBinder(binder), **wiring,
        )  # fmt: skip

    async def describe(self, tool: str) -> ToolInfo:
        """As `AdapterToolPort.describe`, as a `CsiToolInfo` (`saves_new_file`)."""
        return CsiToolInfo(**(await super().describe(tool)).model_dump())

    def supports_reconcile(self, tool: str) -> bool:
        """As `AdapterToolPort.supports_reconcile`; false for saves and restores (the engineer decides)."""
        return tool not in _UNRECONCILED and super().supports_reconcile(tool)

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> Envelope:
        """As `AdapterToolPort.call`; a successful edit is committed to the book and marked on the host port.

        Raises:
            ContractError: `INVALID_ARGUMENT` for a tool outside the allowlist and for `csi_open_model`.
        """
        descriptor = self._find(tool)
        if tool == "csi_open_model":
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, "csi_open_model is reached through csi_open_revision", field="tool"
            )
        try:
            if tool in READ_TOOLS:
                return await self._read_parts(descriptor, args, model)
            if tool == "csi_open_revision":
                return await self._open_revision(args, op_id, model)
            if tool == "csi_save_model" and args.get("as_new_revision") is True:
                return await self._new_revision(descriptor, args, op_id, model)
            if self._revisions is not None and descriptor.effect == "write":
                self._not_a_snapshot(await self._open_file(descriptor, model))
        except (ContractError, ToolFailed) as error:
            return make_failure(error.detail)
        reply = await super().call(tool, args, op_id=op_id, model=model)
        key = str(args.get("model"))
        if isinstance(reply, SuccessEnvelope) and tool in EDIT_BUILDERS:  # analysis and reads change no model row
            self._written.commit(key)
            self._wrote(key)
        return reply

    def _wired(self) -> Revisions:
        if self._revisions is None:
            raise ContractError(ErrorCode.INTERNAL, "no revision wiring", incident_id=self._ids.new_ulid())
        return self._revisions

    async def _open_file(self, descriptor: ToolDescriptor, model: str | None) -> Path | None:
        """The path the host reports for the model open in the bound instance, `None` when none is open."""
        binding = await self._binder.binding(self._config.servers[self._server].host_key, model, descriptor)
        info = await self._read("csi_model_info", {"target": binding.target.model_dump()}, CallEffect.READ)
        path = info.get("model_path")
        return Path(path) if isinstance(path, str) else None

    def _not_a_snapshot(self, path: Path | None) -> None:
        if path is not None and self._wired().is_snapshot(path):
            raise ContractError(ErrorCode.CONFLICT, "the open file is a snapshot of this run", received=path.name)

    async def _read_parts(
        self, descriptor: ToolDescriptor, args: Mapping[str, JsonValue], model: str | None
    ) -> Envelope:
        """An adapter-local read: each part stored as its own result, the last one answers (`_read_state_tool`)."""
        server = self._config.servers[self._server]
        self._health.check(server.host_key)  # a wedged host gets nothing until the engine has reconciled
        started, began = self._clock.now(), self._clock.now_ms()
        validated = validate_call(ModelArgs, args, source=self._store, current_revision=self._binder.revision)
        binding = await self._binder.binding(server.host_key, model, descriptor)
        *others, (_, kind, payload) = await READ_TOOLS[descriptor.name](self._read, binding.target)

        def put(kind: str, payload: dict[str, JsonValue], summary: dict[str, JsonValue]) -> SuccessEnvelope:
            return make_envelope(
                self._store, tool=f"{self._allowlist.adapter}/{descriptor.name}", kind=kind, payload=payload,
                summary=summary, reply={}, check=self._check, host=binding.host, inputs=validated.inputs,
                started_at=started, duration_ms=self._clock.now_ms() - began,
            )  # fmt: skip

        refs: dict[str, JsonValue] = {key: put(part, body, {}).result_id for key, part, body in others}
        return put(kind, payload, refs)

    async def _new_revision(
        self, descriptor: ToolDescriptor, args: Mapping[str, JsonValue], op_id: str, model: str | None
    ) -> Envelope:
        """`csi_save_model` with `as_new_revision`: the open file saved in place, then copied to a verified snapshot."""
        revisions = self._wired()
        working = await self._open_file(descriptor, model)
        if working is None:
            raise ContractError(ErrorCode.PRECONDITION_FAILED, "no model is open", precondition=Precondition.model_open)
        self._not_a_snapshot(working)
        target = revisions.target(working)  # refused before anything is saved
        reply = await super().call("csi_save_model", args, op_id=op_id, model=model)
        if not isinstance(reply, SuccessEnvelope):
            return reply
        return _with_saved_file(reply, revisions.snapshot(working, target))

    async def _open_revision(self, args: Mapping[str, JsonValue], op_id: str, model: str | None) -> Envelope:
        """`csi_open_revision`: a copy of an unchanged snapshot becomes the working file, opened without saving."""
        revisions = self._wired()
        validated = validate_call(OpenRevisionArgs, args, source=self._store, current_revision=self._binder.revision)
        path, saved = revisions.reopen(validated.model.revision)
        reply = await super().call(
            "csi_open_model", {"model": validated.model.model, "path": str(path)}, op_id=op_id, model=model
        )
        if not isinstance(reply, SuccessEnvelope):
            return reply
        self._reopened(validated.model.model, path)
        return _with_saved_file(reply, saved)


def _with_saved_file(reply: SuccessEnvelope, saved: SavedFile) -> SuccessEnvelope:
    """`reply` whose summary also names the file written (engine 4.6 "Tool saves": `saved_file`)."""
    return reply.model_copy(update={"summary": {**reply.summary, "saved_file": saved.model_dump()}})
