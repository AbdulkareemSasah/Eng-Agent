"""Test doubles of the permission-mode tests (plan 0001 T16; spec 0001 AC48 to AC51); never shipped.

Extra tools for the rig's fake host (a read with a model, a delete, a save that may overwrite the original) and a host
whose writes return the stored result of the revision they produced.
"""

from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import JsonValue

from eng_harness.ports import ToolInfo
from workflows.ctx_flows import written
from workflows.rig import Rig, make_rig


class Overwriting(ToolInfo):
    """A save tool that overwrites the engineer's original when its `target` argument is `original`."""

    def overwrites_original(self, args: Mapping[str, JsonValue]) -> bool:
        """True for `target` `original`."""
        return args.get("target") == "original"


EXTRA = (
    ToolInfo(name="read_m", effect="read", action="plain", host_key="csi", model_param="model"),
    ToolInfo(name="delete_d", effect="write", action="delete", host_key="csi", model_param="model"),
    Overwriting(name="save_s", effect="write", action="save", host_key="csi", model_param="model"),
)


def mode_rig(root: Path) -> Rig:
    """A rig whose fake host opens a distinct `<model>.copy` as a working copy and knows the tools of `EXTRA`."""
    rig = make_rig(root)
    rig.host.alias_copies = False
    for tool in EXTRA:
        rig.host._tools[tool.name] = tool  # the fake host takes its tools at construction
    return rig


def stored_writes(rig: Rig, patch: pytest.MonkeyPatch) -> None:
    """Make each write to a working copy return a stored result with the revision it produced, as an adapter does."""
    take = rig.host.working_copy

    async def copy(model_key: str, folder: Path) -> str:
        key = await take(model_key, folder)
        rig.host.script("write_b", *(written(rig, key, n) for n in (1, 2)))
        return key

    patch.setattr(rig.host, "working_copy", copy)
