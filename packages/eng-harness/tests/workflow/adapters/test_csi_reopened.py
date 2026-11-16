"""The host port follows the working file that `csi_open_revision` opens (plan 0007 T13; spec 0007 4.10, AC38).

A `CsiToolPort` and an `AdapterHostPort` are wired over the synthetic fake: the tool port's `reopened` callback is the
host port's `reopened`. A snapshot is saved and opened again; the host port then names, finds and reads the new working
file on the same bound instance, and its first `model_state` is a new baseline (no `MODEL_CHANGED_OUTSIDE`). A refused
open leaves the previous file bound. The revision number of the restored file is spec Q16 (open): it is not pinned.
"""

import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
from eng_contract.envelope import FailureEnvelope, SuccessEnvelope
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, ResultStore, Workspace

from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.servers import ServerManager
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

from . import test_csi_read_state_tool as base
from .test_csi_analysis import CHECK
from .test_csi_session_ops import ETABS_EXE, ConfigFactory, LaunchInspector
from .test_readback import Binder

store = base.store  # the fixture of the read-state tests, by name


def _saved_name(envelope: SuccessEnvelope) -> str:
    saved = envelope.summary["saved_file"]
    assert isinstance(saved, dict)
    name = saved["name"]
    assert isinstance(name, str)
    return name


@dataclass
class Rig:
    host: Any
    port: Any
    key: str
    pid: int
    folder: Path
    calls: list[tuple[str, Path]]

    async def call(self, tool: str, **arguments: Any) -> Any:
        return await self.port.call(tool, {"model": self.key, **arguments}, op_id=f"op-{tool}", model=self.key)

    async def snapshot(self) -> Path:
        saved = await self.call("csi_save_model", as_new_revision=True)
        assert isinstance(saved, SuccessEnvelope), saved
        return self.folder / _saved_name(saved)


@asynccontextmanager
async def _rig(tmp_path: Path, config: Any, control: Path, store: ResultStore, run_dir: Path) -> AsyncIterator[Rig]:
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.csi._revisions import Revisions
    from eng_harness.adapters.csi._tools import CsiToolPort

    base._seeded(control)
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"reopened", clock)
    workspace = Workspace(root=tmp_path / "idws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    original = tmp_path / "original.EDB"
    original.write_bytes(b"model-v1")
    inspector = LaunchInspector(control)
    guard = ProcessGuard(inspector, run_dir, host_exes=[ETABS_EXE])
    locks = HostLocks(
        tmp_path / "locks", run_id="b522", engine=ProcessIdentity(os.getpid(), "t0", "python"), clock=clock
    )
    manager = ServerManager(config, run_dir, helpers=guard)
    host = AdapterHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids), states=states, sessions=manager,
        guard=guard, inspector=inspector, locks=locks, clock=clock, ids=ids, run_dir=run_dir, product="ETABS",
        program="ETABS", exe_name=ETABS_EXE, files={"m": original},
    )  # fmt: skip
    calls: list[tuple[str, Path]] = []

    def reopened(key: str, path: Path) -> None:
        calls.append((key, path))
        host.reopened(key, path)

    async with manager:
        folder = tmp_path / "copies"
        key = await host.working_copy("m", folder)
        held = await host.locate(key)
        assert held is not None
        port = CsiToolPort(
            binder=Binder(held.pid), reopened=reopened, revisions=Revisions(folder, run_dir / "adapter" / "revs.json"),
            config=config, server="csi", caller=manager, store=store, ledger=WriteLedger(run_dir), clock=clock,
            ids=ids, check=CHECK, errors=CsiErrorMapper(ids),
        )  # fmt: skip
        yield Rig(host, port, key, held.pid, folder, calls)


def _run(
    body: Callable[[Rig], Any], tmp_path: Path, make_config: ConfigFactory, control: Path, **fixtures: Any
) -> None:
    async def scenario() -> None:
        async with _rig(tmp_path, make_config(), control, fixtures["store"], fixtures["run_dir"]) as rig:
            await body(rig)

    anyio.run(scenario)


def test_restore_moves_host_port(
    tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """AC38: after the open the host port names, finds and reads the restored file, with no outside-edit warning."""

    async def body(rig: Rig) -> None:
        first = await rig.host.locate(rig.key)
        assert first is not None
        before = await rig.host.model_state(rig.key, first.instance_id)
        assert before.loaded is True
        snapshot = await rig.snapshot()
        opened = await rig.call("csi_open_revision", revision=snapshot.name)
        assert isinstance(opened, SuccessEnvelope), opened
        restored = rig.folder / _saved_name(opened)
        assert rig.calls == [(rig.key, restored)]
        assert rig.host.model_files(rig.key) == (restored.resolve(),)
        found = await rig.host.locate(rig.key)
        assert found is not None
        assert (found.instance_id, found.pid) == (first.instance_id, first.pid)  # the same bound instance
        assert rig.host.last_read(rig.key) is None  # a new baseline for the outside-edit check
        after = await rig.host.model_state(rig.key, found.instance_id)
        assert after.loaded is True
        assert after.model_id == before.model_id  # spec Q16 (open): the binding's model id is kept
        assert rig.host.take_warnings() == []  # no MODEL_CHANGED_OUTSIDE
        state = json.loads((run_dir / "adapter" / "state.json").read_text(encoding="utf-8"))
        assert state["bindings"][rig.key]["file"] == str(restored.resolve())  # persisted

    _run(body, tmp_path, make_config, control, store=store, run_dir=run_dir)


def test_refused_open_keeps_previous_file(
    tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """A changed snapshot is a `CONFLICT`: the callback is not called and the previous file stays bound and found."""

    async def body(rig: Rig) -> None:
        previous = rig.host.model_files(rig.key)
        snapshot = await rig.snapshot()
        snapshot.write_bytes(snapshot.read_bytes() + b"x")
        refused = await rig.call("csi_open_revision", revision=snapshot.name)
        assert isinstance(refused, FailureEnvelope), refused
        assert refused.error.code is ErrorCode.CONFLICT
        assert rig.calls == []
        assert rig.host.model_files(rig.key) == previous
        assert await rig.host.locate(rig.key) is not None

    _run(body, tmp_path, make_config, control, store=store, run_dir=run_dir)


def test_other_tools_do_not_call_reopened(
    tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """A snapshot save and a read are not an open: the callback is called by `csi_open_revision` only."""

    async def body(rig: Rig) -> None:
        await rig.snapshot()
        assert isinstance(await rig.call("csi_read_model_state"), SuccessEnvelope)
        assert rig.calls == []

    _run(body, tmp_path, make_config, control, store=store, run_dir=run_dir)


def test_reopened_unknown_key(
    tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """`reopened` of a key with no bound file is `NOT_FOUND` and binds nothing."""
    import pytest
    from eng_contract.errors import ContractError

    async def body(rig: Rig) -> None:
        with pytest.raises(ContractError) as raised:
            rig.host.reopened("nope", tmp_path / "x.EDB")
        assert raised.value.detail.code is ErrorCode.NOT_FOUND
        assert rig.host.model_files(rig.key)  # the bound key is untouched

    _run(body, tmp_path, make_config, control, store=store, run_dir=run_dir)
