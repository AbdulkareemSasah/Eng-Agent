"""HostPort lease, preflight, epoch and run-state reload on the synthetic fake (plan 0002 T19c; spec 0002 AC47).

Two `AdapterHostPort`s share one `run_dir`, server manager and inspector, as an engine and its resumed successor do;
each has its own `HostLocks` (another run id), so the lock file shows which of them holds an instance.
"""

import json
import os
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock, FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, Workspace

from eng_harness.servers import ServerManager
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

from ..conftest import COMMIT
from .test_csi_session_ops import ETABS_EXE, FIRST_PID, ConfigFactory, LaunchInspector, _calls

_START = 1_700_000_000_000


def _port(tmp_path: Path, manager: ServerManager, guard: ProcessGuard, inspector: LaunchInspector, clock: Clock,
          run_id: str, files: dict[str, Path]) -> tuple[Any, HostLocks]:  # fmt: skip
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    ids = SeededIdSource(run_id.encode(), clock)
    locks = HostLocks(
        tmp_path / "locks", run_id=run_id, engine=ProcessIdentity(os.getpid(), "t0", "python"), clock=clock
    )
    port = AdapterHostPort(
        identity=IdentityStore(workspace=workspace, states=ModelStateStore(workspace, clock), ids=ids),
        sessions=manager, guard=guard, inspector=inspector, locks=locks, clock=clock, ids=ids,
        run_dir=tmp_path / "run", product="ETABS", program="ETABS", exe_name=ETABS_EXE, files=files,
    )  # fmt: skip
    return port, locks


def _setup(
    tmp_path: Path, make_config: ConfigFactory, control: Path
) -> tuple[ServerManager, ProcessGuard, LaunchInspector, Path]:
    original = tmp_path / "original.EDB"
    original.write_bytes(b"model-v1")
    inspector = LaunchInspector(control)
    guard = ProcessGuard(inspector, tmp_path / "run", host_exes=[ETABS_EXE])
    return ServerManager(make_config(), tmp_path / "run", helpers=guard), guard, inspector, original


def test_lease_preflight_and_epoch(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """`preflight` and `session_epoch` come from the server manager; a lease locks the live instance, `release` frees it."""
    clock = FixedClock(_START)

    async def body() -> None:
        manager, guard, inspector, original = _setup(tmp_path, make_config, control)
        port, locks = _port(tmp_path, manager, guard, inspector, clock, "r1", {"m": original})
        async with manager:
            checks = await port.preflight({"csi": COMMIT})
            assert [(c.server, c.ok) for c in checks] == [("csi", True)]
            assert port.session_epoch("csi") == manager.session_epoch("csi")
            await port.working_copy("m", tmp_path / "run" / "copies")
            identity = inspector.identity(FIRST_PID)
            assert identity is not None
            locks.release_all()  # the lease, not the launch, must lock it again
            lease = await port.acquire("csi")
            assert (lease.host_key, bool(lease.lease_id)) == ("csi", True)
            holder = locks.holder("ETABS", identity)
            assert holder is not None
            assert holder.run_id == "r1"
            other, other_locks = _port(tmp_path, manager, guard, inspector, clock, "r2", {"m": original})
            with pytest.raises(ContractError) as refused:
                await other.acquire("csi")
            assert refused.value.detail.code is ErrorCode.HOST_LOCKED
            assert refused.value.detail.message == "host instance driven by run r1"
            await port.release(lease)
            await other.acquire("csi")
            assert other_locks.holder("ETABS", identity) is not None
            assert (await other.acquire("other")).host_key == "other"  # no instance of another host key is locked

    anyio.run(body)


def test_new_port_restores_from_run_state(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """A port over the same `run_dir` finds the working copy, its units and its instance; the instance is not launch-owned."""
    clock = FixedClock(_START)

    async def body() -> None:
        manager, guard, inspector, original = _setup(tmp_path, make_config, control)
        first, locks = _port(tmp_path, manager, guard, inspector, clock, "r1", {"m": original})
        async with manager:
            key = await first.working_copy("m", tmp_path / "run" / "copies")
            saved = await first.save(key, "pre_analysis")
            held = await first.locate(key)
            assert held is not None
            rows = json.loads((tmp_path / "run" / "adapter" / "state.json").read_text())["instances"]
            assert [(r["pid"], r["exe_name"], r["visible"]) for r in rows] == [(FIRST_PID, ETABS_EXE, False)]
            assert rows[0]["started_at"] == "t1"
            locks.release_all()

            second, second_locks = _port(tmp_path, manager, guard, inspector, clock, "r2", {"m": original})
            assert second.model_files(key) == first.model_files(key)
            found = await second.locate(key)
            assert found == held  # the same instance id, pid and observation time
            assert [i.pid for i in await second.started_instances("csi")] == [FIRST_PID]
            units = await second.read_units(key, held.instance_id)
            assert (units.loaded, units.ok, units.expected == units.present) == (True, True, True)
            await second.acquire("csi")
            holder = second_locks.holder("ETABS", ProcessIdentity(FIRST_PID, "t1", ETABS_EXE))
            assert holder is not None
            assert holder.run_id == "r2"

            restored = await second.restore(key, saved)  # a reloaded instance is never launch-owned: a new one starts
            assert restored.pid != FIRST_PID
            assert len([c for c in _calls(control) if c["tool"] == "csi_launch"]) == 2
            await second.close_started("csi", [found])
            assert [i.pid for i in inspector.terminated] == [FIRST_PID]

    anyio.run(body)
