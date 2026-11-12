"""The CSI `ToolPort` over the edit tools (plan 0002 T12; spec 0002 sections 4.5.2, 4.5.4, 4.6.2, 4.6.3).

A `token` tool passes the units token whose units make its conversion simplest (spec 4.5.4): `kN_mm_C` for the wall
thickness, `kN_m_C` for the loads (spec 4.6.3). The framework fixes one token per binding, so the token of the tool
being called is put on the binding here.
"""

from collections.abc import Mapping
from contextvars import ContextVar
from typing import Any

from eng_contract.envelope import Envelope
from pydantic import JsonValue

from eng_harness.adapters._allowlist import Allowlist
from eng_harness.adapters._toolport import AdapterToolPort, Binding, ModelBinder
from eng_harness.adapters.csi import csi_allowlist
from eng_harness.adapters.csi._edits import EDIT_BUILDERS, EDIT_MODELS

__all__ = ["TOKENS", "CsiToolPort", "edit_allowlist"]

TOKENS = {  # spec 4.6.2 and 4.6.3
    "csi_define_wall_section": "kN_mm_C",
    "csi_set_frame_load_distributed": "kN_m_C",
    "csi_set_area_load_uniform": "kN_m_C",
}
_CALLING: ContextVar[str] = ContextVar("csi_calling_tool", default="")


def edit_allowlist() -> Allowlist:
    """The packaged CSI allowlist reduced to the edit tools of spec 4.6.2 (the rest follows in T13, T14)."""
    full = csi_allowlist()
    return full.model_copy(update={"tools": tuple(t for t in full.tools if t.name in EDIT_BUILDERS)})


class _TokenBinder:
    """The adapter's binder with the units token of the tool being called."""

    def __init__(self, inner: ModelBinder) -> None:
        self._inner = inner

    async def binding(self, host_key: str, model: str | None) -> Binding:
        bound = await self._inner.binding(host_key, model)
        token = TOKENS.get(_CALLING.get())
        return bound if token is None else bound.model_copy(update={"units_system": token})

    def revision(self, model_id: str) -> int | None:
        return self._inner.revision(model_id)


class CsiToolPort(AdapterToolPort):
    """`AdapterToolPort` over `edit_allowlist()`, the edit argument models and builders; `wiring` as its parameters."""

    def __init__(self, *, binder: ModelBinder, **wiring: Any) -> None:
        super().__init__(
            allowlist=edit_allowlist(), arg_models=EDIT_MODELS, builders=EDIT_BUILDERS,
            binder=_TokenBinder(binder), **wiring,
        )  # fmt: skip

    async def call(self, tool: str, args: Mapping[str, JsonValue], *, op_id: str, model: str | None) -> Envelope:
        """Call `tool` with its units token on the binding."""
        reset = _CALLING.set(tool)
        try:
            return await super().call(tool, args, op_id=op_id, model=model)
        finally:
            _CALLING.reset(reset)
