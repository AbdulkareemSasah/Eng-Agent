"""The CSI host port opens the original for the step 2 open and launches visible on request (plan 0002 T23; AC51).

A `CsiToolPort` and an `AdapterHostPort` are wired over the synthetic fake: the tool port's `opener` is the host
port's `open_original`, and the test binder reads the instance the host port holds for the model key (the binder of
`build_ports` is T19a's). Every refusal is an envelope and nothing is sent to the host for it.
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

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.servers import ServerManager
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

from . import test_csi_read_state_tool as base
from .test_csi_analysis import CHECK
from .test_csi_session_ops import ETABS_EXE, FIRST_PID, ConfigFactory, LaunchInspector
from .test_readback import HOST

store = base.store  # the fixture of the read-state tests, by name


class HostBinder:
    """The instance the host port holds for the model key, as the binder of `build_ports` reads it."""

    def __init__(self, host: Any) -> None:
        self._host = host

    async def binding(self, host_key: str, model: str | None, descriptor: ToolDescriptor) -> Binding:
        held = await self._host.locate(model)
        assert held is not None, "the open did not bind the model key"
        return Binding(target=HostTarget(product="ETABS", pid=held.pid), host=HOST, owned=True)

    def revision(self, model_id: str) -> int | None:
        return None


@dataclass
class Rig:
    host: Any
    port: Any
    original: Path
    control: Path
    store: ResultStore

    def calls(self, tool: str) -> list[dict[str, Any]]:
        sent = json.loads(self.control.read_text()).get("calls", [])
        return [call for call in sent if call["tool"] == tool]

    async def open(self, **arguments: Any) -> Any:
        return await self.port.call("csi_open_model", {"model": "m", **arguments}, op_id="op-open", model="m")


@asynccontextmanager
async def _rig(
    tmp_path: Path, config: Any, control: Path, store: ResultStore, run_dir: Path, *, visible: bool | None = None,
    opener: bool = True,
) -> AsyncIterator[Rig]:  # fmt: skip
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.csi._tools import CsiToolPort

    base._seeded(control)
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"openorig", clock)
    workspace = Workspace(root=tmp_path / "idws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    original = tmp_path / "original.EDB"
    original.write_bytes(b"model-v1")
    inspector = LaunchInspector(control)
    guard = ProcessGuard(inspector, run_dir, host_exes=[ETABS_EXE])
    locks = HostLocks(
        tmp_path / "locks", run_id="b550", engine=ProcessIdentity(os.getpid(), "t0", "python"), clock=clock
    )
    manager = ServerManager(config, run_dir, helpers=guard)
    extra: dict[str, Any] = {} if visible is None else {"visible": visible}
    host = AdapterHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids), states=states, sessions=manager,
        guard=guard, inspector=inspector, locks=locks, clock=clock, ids=ids, run_dir=run_dir, product="ETABS",
        program="ETABS", exe_name=ETABS_EXE, files={"m": original}, **extra,
    )  # fmt: skip
    async with manager:
        port = CsiToolPort(
            binder=HostBinder(host), opener=host.open_original if opener else None, config=config, server="csi",
            caller=manager, store=store, ledger=WriteLedger(run_dir), clock=clock, ids=ids, check=CHECK,
            errors=CsiErrorMapper(ids),
        )  # fmt: skip
        yield Rig(host, port, original, control, store)


def _run(
    body: Callable[[Rig], Any], tmp_path: Path, make_config: ConfigFactory, control: Path, run_dir: Path,
    store: ResultStore, **options: Any,
) -> None:  # fmt: skip
    tmp_path.mkdir(exist_ok=True)

    async def scenario() -> None:
        async with _rig(tmp_path, make_config(), control, store, run_dir, **options) as rig:
            await body(rig)

    anyio.run(scenario)


def test_open_original_then_working_copy(
    tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """AC51: the open launches and locks one instance, binds the key, records the units; the copy opens in it."""

    async def body(rig: Rig) -> None:
        assert await rig.host.locate("m") is None
        opened = await rig.open()
        assert isinstance(opened, SuccessEnvelope), opened
        assert opened.kind == "harness.run_output/1"
        record = rig.store.get(opened.result_id)
        assert record.payload == {"value": {"model": "m", "file": "original.EDB"}}
        assert [call["path"] for call in rig.calls("csi_open_model")] == [str(rig.original.resolve())]
        held = await rig.host.locate("m")
        assert held is not None
        assert held.pid == FIRST_PID
        units = await rig.host.read_units("m", held.instance_id)
        assert (units.loaded, units.ok) == (True, True)
        assert units.expected != ""
        state = json.loads((run_dir / "adapter" / "state.json").read_text(encoding="utf-8"))
        assert state["bindings"]["m"]["file"] == str(rig.original.resolve())
        assert state["expected_units"]["m"] == units.expected

        copy_key = await rig.host.working_copy("m", tmp_path / "copies")
        copied = await rig.host.locate(copy_key)
        assert copied is not None
        assert copied.instance_id == held.instance_id  # the copy opens in the same instance
        assert len(rig.calls("csi_launch")) == 1

    _run(body, tmp_path, make_config, control, run_dir, store)


def test_open_refusals_are_envelopes(
    tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """AC51: a named path, a key with no file and a port without an opener are failure envelopes; nothing is sent."""

    async def body(rig: Rig) -> None:
        named = await rig.open(path="x.EDB")
        assert isinstance(named, FailureEnvelope), named
        assert named.error.code is ErrorCode.INVALID_ARGUMENT
        unknown = await rig.port.call("csi_open_model", {"model": "nope"}, op_id="op-open", model="nope")
        assert isinstance(unknown, FailureEnvelope), unknown
        assert unknown.error.code is ErrorCode.NOT_FOUND
        assert rig.calls("csi_launch") == []
        assert rig.calls("csi_open_model") == []
        assert await rig.host.locate("m") is None

    _run(body, tmp_path, make_config, control, run_dir, store)

    async def without(rig: Rig) -> None:
        refused = await rig.open()
        assert isinstance(refused, FailureEnvelope), refused
        assert refused.error.code is ErrorCode.INTERNAL
        assert rig.calls("csi_launch") == []

    _run(without, tmp_path / "bare", make_config, control, tmp_path / "bare" / "run", store, opener=False)


def test_visible_launch(
    tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """AC51: `visible` true sends `csi_launch` with `visible: true` and records it; the default sends false."""

    async def shown(rig: Rig) -> None:
        assert isinstance(await rig.open(), SuccessEnvelope)
        assert [call["visible"] for call in rig.calls("csi_launch")] == [True]
        state = json.loads((run_dir / "adapter" / "state.json").read_text(encoding="utf-8"))
        assert [row["visible"] for row in state["instances"]] == [True]

    _run(shown, tmp_path, make_config, control, run_dir, store, visible=True)

    async def hidden(rig: Rig) -> None:
        assert isinstance(await rig.open(), SuccessEnvelope)
        assert [call["visible"] for call in rig.calls("csi_launch")] == [False]

    _run(hidden, tmp_path / "hidden", make_config, control, tmp_path / "hidden" / "run", store)
