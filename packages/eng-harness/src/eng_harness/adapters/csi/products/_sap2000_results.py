"""SAP2000 analysis, result and design readers (plan 0012 T6; spec 0012 section 3.5, AC14 to AC16).

Reuses the shared CSI reply mappers so force and design kinds cannot drift from ETABS/SAFE. Units token `kN_m_C`
for force/moment results (AC15). Aluminum and coldformed design are refused with `NOT_SUPPORTED_BY_VERSION` before any
host call (AC16). Concrete design results for a named non-beam frame are gap SP-3 (S-12 §1: concrete reads beams only).
No engineering number is invented; sign conventions stay `host_local/1` / `host_unconfirmed/1`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ParamModel
from pydantic import JsonValue

from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._toolport import Binding, Builder, Reader
from eng_harness.adapters.csi import _replies
from eng_harness.adapters.csi._gaps import refuse_step
from eng_harness.adapters.csi.products import _safe_results

__all__ = [
    "BUILDERS",
    "READERS",
    "TOKENS",
    "concrete_non_beam_results",
    "refuse_unsupported_design_kind",
]

_MODEL_KEY = "model"


def _reader(mapper: Any) -> Reader:
    def read(reply: Mapping[str, JsonValue], binding: Binding) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
        return mapper(reply, binding).model_dump(mode="json"), {}

    return read


def refuse_unsupported_design_kind(kind: str) -> NoReturn:
    """Refuse aluminum/coldformed before any host call (spec 0012 AC16, coverage table §4.1)."""
    raise ContractError(
        ErrorCode.NOT_SUPPORTED_BY_VERSION,
        f"Design kind {kind} is not supported by this version.",
        retryable=False,
    )


def concrete_non_beam_results() -> NoReturn:
    """Refuse concrete design results for frames that are not beams (gap SP-3, AC16)."""
    refuse_step("concrete_non_beam", product="SAP2000")


def _fields(model: ParamModel) -> dict[str, JsonValue]:
    return model.model_dump(mode="json", exclude_none=True, exclude={_MODEL_KEY})


def _design_run(model: ParamModel, descriptor: ToolDescriptor, binding: Binding) -> dict[str, JsonValue]:
    """Build `csi_design_run` arguments; SAP2000 refuses aluminum/coldformed before any call (AC16)."""
    kind = getattr(model, "kind", None)
    if binding.target.product == "SAP2000" and kind in ("aluminum", "coldformed"):
        refuse_unsupported_design_kind(str(kind))
    return _fields(model)


def _design_results(model: ParamModel, descriptor: ToolDescriptor, binding: Binding) -> dict[str, JsonValue]:
    """Build `csi_design_results` arguments; a named concrete member on SAP2000 is SP-3 (non-beam, AC16)."""
    kind = getattr(model, "kind", None)
    name = getattr(model, "name", None)
    if binding.target.product == "SAP2000" and kind == "concrete" and name is not None:
        concrete_non_beam_results()
    return _fields(model)


# Discoverable on this module (SAFE T7 pattern); shared `_tools` already registers the same mappers.
READERS: dict[str, Reader] = {
    "csi_run_analysis": _reader(lambda r, b: _replies.analysis_run(r)),
    "csi_analysis_status": _reader(lambda r, b: _replies.analysis_status(r)),
    "csi_design_run": _reader(lambda r, b: _replies.design_run(r)),
    "csi_design_results": _reader(lambda r, b: _replies.design_results(r)),
    "csi_results_joint_reactions": _reader(lambda r, b: _replies.joint_reactions(r, b.units_system or "")),
    "csi_results_frame_forces": _reader(lambda r, b: _replies.member_forces(r, b.units_system or "")),
    "csi_results_base_reactions": _reader(lambda r, b: _safe_results.base_reactions(r, b.units_system or "")),
}

TOKENS = {
    "csi_results_joint_reactions": "kN_m_C",
    "csi_results_frame_forces": "kN_m_C",
    "csi_results_base_reactions": "kN_m_C",
}

# Wired into CsiToolPort builders (plan 0012 T6; same merge pattern as plan 0008 T7 / B-588).
BUILDERS: dict[str, Builder] = {
    "csi_design_run": _design_run,
    "csi_design_results": _design_results,
}
