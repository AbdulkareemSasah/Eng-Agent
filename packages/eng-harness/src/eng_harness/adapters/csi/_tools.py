"""The CSI `ToolPort` over the edit, analysis, design and result tools (plan 0002 T12, T13; spec 0002 4.5.2 to 4.6.3).

A `token` tool passes the units token whose units make its conversion simplest (spec 4.5.4): `kN_mm_C` for the wall
thickness, `kN_m_C` for the loads and the force results (spec 4.6.1, 4.6.3). The framework fixes one token per
binding, so the token of the tool being called, from its descriptor, is put on the binding here.

Analysis and design are `long`-class tools: the framework sends them to the `long` role (its own call timeout) and
their `action` makes the engine save the model first (engine invariant 7).

Each write is recorded for the read-back (plan 0002 T12b): the wrapped builder, which sees the canonical model and the
binding before the send, prepares the item; a successful reply commits it and marks the write on the host port, so the
fingerprint change is not an outside edit; a failed call records nothing (an unknown outcome is T14's reconciliation).
"""

from collections.abc import Callable, Mapping
from typing import Any, Literal

from eng_contract.envelope import Envelope, SuccessEnvelope
from eng_contract.params import ParamModel
from pydantic import BaseModel, Field, JsonValue

from eng_harness.adapters._allowlist import Allowlist
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._toolport import AdapterToolPort, Binding, Builder, ModelBinder, Reader
from eng_harness.adapters.csi import _replies, csi_allowlist
from eng_harness.adapters.csi._checks import WrittenItems
from eng_harness.adapters.csi._edits import EDIT_BUILDERS, EDIT_MODELS

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


ANALYSIS_MODELS: dict[str, type[ParamModel]] = {  # by the allowlist's `args_model`
    "RunAnalysisArgs": _ModelArgs,
    "AnalysisStatusArgs": _ModelArgs,
    "DesignRunArgs": DesignRunArgs,
    "DesignResultsArgs": DesignResultsArgs,
    "ResultsJointReactionsArgs": _ObjectResultsArgs,
    "ResultsFrameForcesArgs": _ObjectResultsArgs,
    "ResultsStoryDriftsArgs": _ResultsArgs,
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
    """The packaged CSI allowlist reduced to the edit tools of spec 4.6.2 and the analysis, design and result tools."""
    full = csi_allowlist()
    return full.model_copy(update={"tools": tuple(t for t in full.tools if t.name in EDIT_BUILDERS | READERS.keys())})


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
    port made without them records into a book nobody reads.
    """

    def __init__(
        self, *, binder: ModelBinder, written: WrittenItems | None = None, wrote: Callable[[str], None] | None = None,
        **wiring: Any,
    ) -> None:  # fmt: skip
        self._written, self._wrote = written or WrittenItems(), wrote or (lambda key: None)
        builders: Mapping[str, Builder] = {tool: _noting(build, self._written) for tool, build in EDIT_BUILDERS.items()}
        super().__init__(
            allowlist=tool_allowlist(), arg_models=EDIT_MODELS | ANALYSIS_MODELS, builders=builders, readers=READERS,
            binder=_TokenBinder(binder), **wiring,
        )  # fmt: skip

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> Envelope:
        """As `AdapterToolPort.call`; a successful edit is committed to the book and marked on the host port."""
        reply = await super().call(tool, args, op_id=op_id, model=model)
        key = str(args.get("model"))
        if isinstance(reply, SuccessEnvelope) and tool in EDIT_BUILDERS:  # analysis and reads change no model row
            self._written.commit(key)
            self._wrote(key)
        return reply
