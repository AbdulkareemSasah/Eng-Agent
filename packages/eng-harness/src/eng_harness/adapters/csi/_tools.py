"""The CSI `ToolPort` over the edit tools (plan 0002 T12; spec 0002 sections 4.5.2, 4.5.4, 4.6.2, 4.6.3).

A `token` tool passes the units token whose units make its conversion simplest (spec 4.5.4): `kN_mm_C` for the wall
thickness, `kN_m_C` for the loads (spec 4.6.3). The framework fixes one token per binding, so the token of the tool
being called, from its descriptor, is put on the binding here.

Each write is recorded for the read-back (plan 0002 T12b): the wrapped builder, which sees the canonical model and the
binding before the send, prepares the item; a successful reply commits it and marks the write on the host port, so the
fingerprint change is not an outside edit; a failed call records nothing (an unknown outcome is T14's reconciliation).
"""

from collections.abc import Callable, Mapping
from typing import Any

from eng_contract.envelope import Envelope, SuccessEnvelope
from eng_contract.params import ParamModel
from pydantic import JsonValue

from eng_harness.adapters._allowlist import Allowlist
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._toolport import AdapterToolPort, Binding, Builder, ModelBinder
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.adapters.csi._checks import WrittenItems
from eng_harness.adapters.csi._edits import EDIT_BUILDERS, EDIT_MODELS

__all__ = ["TOKENS", "CsiToolPort", "edit_allowlist"]

TOKENS = {  # spec 4.6.2 and 4.6.3
    "csi_define_wall_section": "kN_mm_C",
    "csi_set_frame_load_distributed": "kN_m_C",
    "csi_set_area_load_uniform": "kN_m_C",
}


def edit_allowlist() -> Allowlist:
    """The packaged CSI allowlist reduced to the edit tools of spec 4.6.2 (the rest follows in T13, T14)."""
    full = csi_allowlist()
    return full.model_copy(update={"tools": tuple(t for t in full.tools if t.name in EDIT_BUILDERS)})


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
    """`AdapterToolPort` over `edit_allowlist()`, the edit argument models and builders; `wiring` as its parameters.

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
            allowlist=edit_allowlist(), arg_models=EDIT_MODELS, builders=builders,
            binder=_TokenBinder(binder), **wiring,
        )  # fmt: skip

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> Envelope:
        """As `AdapterToolPort.call`; a successful write is committed to the book and marked on the host port."""
        reply = await super().call(tool, args, op_id=op_id, model=model)
        key = str(args.get("model"))
        if isinstance(reply, SuccessEnvelope):
            self._written.commit(key)
            self._wrote(key)
        return reply
