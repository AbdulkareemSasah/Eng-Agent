"""`csi_read_model_state` and `csi_read_analysis_messages`, adapter-local reads (spec 0007 4.10; plan 0007 T5).

Each tool composes allowlisted host reads and answers parts `(key, kind, payload)`: the tool port stores each as its
own result; the last answers and its summary holds the references of the others by `key`. The read set is spec 0002
4.6.4 less `model.grid_system/1` and `model.sections/1` (S12-G8: not readable, so downstream calcs give `not_read`),
plus `harness.csi_name_lists/1`. Errors (`ContractError`): `LIMIT_EXCEEDED` for a list or table cut at 2000 rows,
`HOST_ERROR` (`UNEXPECTED_REPLY`) for a reply without rows or a name row without `name`, the state reader's errors.
Reply fields and the `Analysis Messages` table are host facts to confirm locally (OQ-G10, `docs/local-testing.md`).
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import ParamModel
from pydantic import JsonValue

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._toolport import HostRead
from eng_harness.adapters.csi import _replies
from eng_harness.adapters.csi._state import LIST_LIMIT, CsiStateReader
from eng_harness.adapters.csi.products import _etabs
from eng_harness.servers import CallEffect

__all__ = ["READ_TOOLS", "ModelArgs", "Part"]

Part = tuple[str, str, dict[str, JsonValue]]  # (summary key, result kind, payload)
_SET = {  # summary key: stored kind (spec 0007 4.10)
    "stories": "model.stories/1",
    "frames": "model.frame_placements/1",
    "areas": "model.area_placements/1",
    "loads": "model.load_set/1",
    "restraints": "model.joint_restraints/1",
}
_STATUS = "harness.csi_model_status/1"
_NAMES = (  # (field of harness.csi_name_lists/1, host list tool)
    ("frame_sections", "csi_list_frame_sections"),
    ("area_sections", "csi_list_area_sections"),
    ("materials", "csi_list_materials"),
    ("patterns", "csi_list_load_patterns"),
    ("combinations", "csi_list_load_combos"),
)


class ModelArgs(ParamModel):
    """The arguments of both read tools: the model."""

    model: str


async def _model_state(read: HostRead, target: HostTarget) -> list[Part]:
    given = {"target": target.model_dump()}
    reader = CsiStateReader(product=target.product, call=read)
    path = (await read("csi_model_info", given, CallEffect.READ)).get("model_path")
    state = await reader.read(target.pid, Path(path) if isinstance(path, str) else None)
    names: dict[str, JsonValue] = {}
    for field, tool in _NAMES:
        rows = await reader._rows(tool, "items", {**given, "limit": LIST_LIMIT}, tool)  # B-451: the reader's read
        names[field] = [*sorted({_name(row, tool) for row in rows})]
    parts: list[Part] = [(key, kind, state.payloads[kind].model_dump(mode="json")) for key, kind in _SET.items()]
    return [
        *parts,
        ("names", "harness.csi_name_lists/1", names),
        ("status", _STATUS, state.status.model_dump(mode="json")),
    ]


def _name(row: dict[str, Any], tool: str) -> str:
    if not isinstance(row.get("name"), str):
        raise ContractError(
            ErrorCode.HOST_ERROR, f"a row of {tool} has no name", retryable=False, host_code="UNEXPECTED_REPLY",
            host_method=tool, field="items",
        )  # fmt: skip
    return str(row["name"])


async def _analysis_messages(read: HostRead, target: HostTarget) -> list[Part]:
    reader = CsiStateReader(product=target.product, call=read)
    arguments = {"target": target.model_dump(), "table": _etabs.ANALYSIS_MESSAGES, "row_limit": LIST_LIMIT}
    rows = await reader._rows("csi_db_table_read", "rows", arguments, _etabs.ANALYSIS_MESSAGES)  # B-451
    messages = _replies.analysis_messages({"rows": rows})
    return [("messages", "harness.csi_analysis_messages/1", messages.model_dump(mode="json"))]


READ_TOOLS: dict[str, Callable[[HostRead, HostTarget], Awaitable[list[Part]]]] = {
    "csi_read_model_state": _model_state,
    "csi_read_analysis_messages": _analysis_messages,
}
