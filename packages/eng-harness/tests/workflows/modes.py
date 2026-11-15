"""Test doubles of the permission-mode and promotion tests (plan 0001 T16, T16b; spec 0001 AC48 to AC53); never shipped.

Extra tools for the rig's fake host (a read with a model, a delete, a save that may overwrite the original), a host
whose writes return the stored result of the revision they produced, a host whose models have real files, a fake
`FileOps` over a dictionary, and the flow that promotes a working copy.
"""

import asyncio
import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError
from pydantic import JsonValue

from eng_harness import errors
from eng_harness.ctx import ApprovalKind, ModelHandle, Promotion
from eng_harness.engine import PermissionMode
from eng_harness.ports import ToolInfo
from workflows.ctx_flows import change_set, flow, reply, request_id, written
from workflows.rig import Rig, make_rig, request


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


def sha(content: bytes) -> str:
    """Hex SHA-256 of `content`, the hash `LocalFileOps` gives one file."""
    return hashlib.sha256(content).hexdigest()


def give_files(
    rig: Rig, patch: pytest.MonkeyPatch, folder: Path, model: str, original: bytes, copy: bytes
) -> tuple[Path, Path]:
    """Real files for `model` and for its working copy `<model>.copy`; the host reports the hash of the original's."""
    first, second = folder / f"{model}.edb", folder / f"{model}.copy.edb"
    first.write_bytes(original)
    second.write_bytes(copy)
    state = rig.host.models[model]
    rig.host.models[model] = state.model_copy(update={"file_sha256": sha(original)})
    files = {model: first, f"{model}.copy": second}
    patch.setattr(rig.host, "model_files", lambda key: (files[key],))  # files that exist on disk
    return first, second


def stored_writes(rig: Rig, patch: pytest.MonkeyPatch) -> None:
    """Make each write to a working copy return a stored result with the revision it produced, as an adapter does."""
    take = rig.host.working_copy

    async def copy(model_key: str, folder: Path) -> str:
        key = await take(model_key, folder)
        rig.host.script("write_b", *(written(rig, key, n) for n in (1, 2)))
        return key

    patch.setattr(rig.host, "working_copy", copy)


class FakeFileOps:
    """A `FileOps` over a dictionary of paths to bytes; `ops` lists what was done, `corrupt` names a copy to spoil."""

    def __init__(self, files: Mapping[Path, bytes], corrupt: str | None = None) -> None:
        """Hold `files`; a copy whose target name is `corrupt` gets other bytes than its source."""
        self.files, self.ops, self._corrupt = dict(files), list[str](), corrupt

    def sha256(self, paths: Sequence[Path]) -> str:
        """SHA-256 of the bytes of `paths`, in order."""
        return sha(b"".join(self.files[p] for p in paths))

    def copy(self, source: Path, target: Path) -> None:
        """Copy the bytes; a spoiled target gets an extra byte."""
        self.ops.append(f"copy {source.name} {target.name}")
        self.files[target] = self.files[source] + (b"!" if target.name == self._corrupt else b"")

    def replace(self, source: Path, target: Path) -> None:
        """Move the bytes over the target."""
        self.ops.append(f"replace {source.name} {target.name}")
        self.files[target] = self.files.pop(source)


def promoting(
    rig: Rig, *, kind: ApprovalKind = ApprovalKind.PROMOTION, models: tuple[str, ...] = ("m1",),
    between: Callable[[], None] | None = None, again: bool = False,
) -> tuple[Any, list[object]]:  # fmt: skip
    """A flow that writes `m1`, asks for a promotion approval, then promotes (twice with `again`); what it caught."""
    seen: list[object] = []

    async def body(ctx: Any) -> list[str]:
        await ctx.tool("write_b", {"n": 1, "model": "m1"})
        approval = await ctx.approve("Promote", change_set(rig, "i1", models=models), kind=kind)
        state = rig.host.models["m1.copy"]
        handle = ModelHandle(model_key="m1", model_id=state.model_id or "", revision=state.revision or 0)
        if between is not None:
            between()
        for _ in range(2 if again else 1):
            try:
                seen.append(await ctx.promote(handle, Promotion.FILE_COPY, approval))
            except (errors.BlockRuleViolation, errors.StepError, ContractError) as exc:
                seen.append(exc)
        return []

    return flow(body), seen


def approved(rig: Rig, workflow: Any) -> tuple[Any, str]:
    """The engine of `workflow` started in `work_on_copy` and paused at the approval, which is answered; its run id."""
    engine = rig.engine(workflow)
    paused = asyncio.run(engine.start(request(mode=PermissionMode.WORK_ON_COPY)))
    rid = request_id(paused.run_id, "1")
    rig.approvals.script(rid, reply(rig))
    return engine, paused.run_id
