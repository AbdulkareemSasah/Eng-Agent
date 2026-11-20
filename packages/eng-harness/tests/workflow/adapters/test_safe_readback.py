"""SAFE check_model read-back of joint loads and integrity (plan 0008 T6; spec 0008 AC18, section 4.7).

Adapter imports sit inside the tests so a missing module fails the test.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, ResultStore, Workspace

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.ports import ServerCheck
from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

from .test_csi_session_ops import LaunchInspector
from .test_safe_session_ops import SAFE_EXE
from .test_safe_state import JOINT_LOADS, _seed

ConfigFactory = Callable[..., ServersConfig]
_START = 1_700_000_000_000
SHA = "d" * 64
CHECK = ServerCheck(
    server="csi_safe",
    build="0123456789ab+fedcba987654",
    min_build="",
    fingerprint=SHA,
    expected_fingerprint=SHA,
    ok=True,
    reason=None,
)
TOLERANCE = 0.001


def _issues(envelope: Any) -> list[tuple[str, str, str, str]]:
    assert isinstance(envelope, SuccessEnvelope)
    data: Any = envelope.data
    return [(i["severity"], i["code"], i["subject"]["kind"], i["subject"]["id"]) for i in data["issues"]]


def _seed_control(control: Path, seed: dict[str, Any] | None = None) -> None:
    control.write_text(json.dumps({"faults": [], "seed": seed if seed is not None else _seed(), "product": "SAFE"}))


@dataclass
class Rig:
    host: Any
    port: Any
    manager: ServerManager
    key: str
    store: ResultStore
    pid: int
    count: int = 0

    def value(self, name: str, number: float) -> dict[str, str]:
        producer = Provenance(
            tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0
        )
        record = self.store.put("harness.run_input/1", {"value": {name: number}}, producer)
        return {"$ref": f"{record.result_id}#/value/{name}"}

    async def write(self, tool: str, **arguments: Any) -> None:
        self.count += 1
        reply = await self.port.call(tool, {"model": self.key, **arguments}, op_id=f"op-{self.count}", model=self.key)
        assert isinstance(reply, SuccessEnvelope), reply

    async def engineer(self, tool: str, **arguments: Any) -> None:
        target = {"target": {"product": "SAFE", "pid": self.pid}}
        await self.manager.call("csi_safe", "main", tool, {**target, **arguments}, CallEffect.WRITE)


class _Binder:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    async def binding(self, host_key: str, model: str | None, descriptor: Any) -> Binding:
        return Binding(
            target=HostTarget(product="SAFE", pid=self.pid),
            host=HostInfo(
                program="SAFE", version="22.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0
            ),
            owned=True,
        )

    def revision(self, model_id: str) -> int | None:
        return None


@asynccontextmanager
async def _rig(
    tmp_path: Path, config: ServersConfig, control: Path, store: ResultStore, *, seed: dict[str, Any] | None = None
) -> AsyncIterator[Rig]:
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.csi._checks import ReadBack, WrittenItems
    from eng_harness.adapters.csi._tools import CsiToolPort

    _seed_control(control, seed)
    clock = FixedClock(_START, 1)
    ids = SeededIdSource(b"safe-rb", clock)
    workspace = Workspace(root=tmp_path / "idws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    original = tmp_path / "footing.FDB"
    original.write_bytes(b"safe-model-v1")
    run_dir = tmp_path / "run"
    inspector = LaunchInspector(control, exe_name=SAFE_EXE)
    guard = ProcessGuard(inspector, run_dir, host_exes=[SAFE_EXE])
    locks = HostLocks(
        tmp_path / "locks", run_id="b215", engine=ProcessIdentity(os.getpid(), "t0", "python"), clock=clock
    )
    base = config.servers["csi"].model_copy(update={"product": "SAFE", "host_key": "csi_safe"})
    safe_config = ServersConfig(servers={"csi_safe": base})
    manager = ServerManager(safe_config, run_dir, helpers=guard)
    written = WrittenItems()
    readback = ReadBack(written=written, store=store, check=CHECK, tolerance_ratio=TOLERANCE)
    host = AdapterHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids),
        states=states,
        sessions=manager,
        guard=guard,
        inspector=inspector,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=run_dir,
        product="SAFE",
        program="safe",
        exe_name=SAFE_EXE,
        server="csi_safe",
        host_key="csi_safe",
        files={"m": original},
        readback=readback,
    )
    async with manager:
        key = await host.working_copy("m", tmp_path / "copies")
        held = await host.locate(key)
        assert held is not None and held.pid is not None
        port = CsiToolPort(
            binder=_Binder(held.pid),
            written=written,
            wrote=host.wrote,
            config=safe_config,
            server="csi_safe",
            caller=manager,
            store=store,
            ledger=WriteLedger(run_dir),
            clock=clock,
            ids=ids,
            check=CHECK,
            errors=CsiErrorMapper(ids),
        )
        yield Rig(host, port, manager, key, store, held.pid)


@pytest.fixture
def store(tmp_path: Path) -> ResultStore:
    from eng_harness._kinds import HARNESS_KINDS

    clock = FixedClock(_START, 1)
    ids = SeededIdSource(b"safe-rb-store", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS, ids, clock)


def test_load_mismatch(tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore) -> None:
    """AC18: a written point load that the host later changes is READBACK_MISMATCH."""

    async def body() -> None:
        async with _rig(tmp_path, make_config(), control, store, seed=_seed(joint_loads=0)) as rig:
            await rig.write(
                "csi_set_point_load",
                joint="P1",
                pattern="DEAD",
                FX_kN=rig.value("FX_kN", 0.0),
                FY_kN=rig.value("FY_kN", 0.0),
                FZ_kN=rig.value("FZ_kN", -55.0),
                MX_kNm=rig.value("MX_kNm", 0.0),
                MY_kNm=rig.value("MY_kNm", 0.0),
                MZ_kNm=rig.value("MZ_kNm", 0.0),
            )
            clean = await rig.host.check_model(rig.key)
            assert [i for i in _issues(clean) if i[1] == "READBACK_MISMATCH"] == []

            await rig.write(
                "csi_set_point_load",
                joint="P1",
                pattern="DEAD",
                FX_kN=rig.value("FX_kN", 0.0),
                FY_kN=rig.value("FY_kN", 0.0),
                FZ_kN=rig.value("FZ_kN", -55.0),
                MX_kNm=rig.value("MX_kNm", 0.0),
                MY_kNm=rig.value("MY_kNm", 0.0),
                MZ_kNm=rig.value("MZ_kNm", 0.0),
            )
            await rig.engineer(
                "csi_set_point_load",
                name="P1",
                load_pattern="DEAD",
                force=[0.0, 0.0, -99.0],
                moment=[0.0, 0.0, 0.0],
                units="kN_m_C",
            )
            bad = await rig.host.check_model(rig.key)
            codes = [i for i in _issues(bad) if i[1] == "READBACK_MISMATCH"]
            assert codes
            assert codes[0][2] == "joint"
            assert codes[0][3] == "P1"

    anyio.run(body)


def test_punch_dimension_change_detected(
    tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore
) -> None:
    """AC18: a replace that changes XDim/YDim is READBACK_MISMATCH naming punch_x_mm or punch_y_mm."""
    seed = _seed(joint_loads=1)
    _seed_control(control, seed)

    async def body() -> None:
        async with _rig(tmp_path, make_config(), control, store, seed=seed) as rig:
            await rig.write(
                "csi_set_point_load",
                joint="P1",
                pattern="DEAD",
                FX_kN=rig.value("FX_kN", 0.0),
                FY_kN=rig.value("FY_kN", 0.0),
                FZ_kN=rig.value("FZ_kN", -120.0),
                MX_kNm=rig.value("MX_kNm", 0.0),
                MY_kNm=rig.value("MY_kNm", 0.0),
                MZ_kNm=rig.value("MZ_kNm", 0.0),
            )
            # Corrupt the punching dimensions after the write (host quirk SG-7 guards against).
            data = json.loads(control.read_text())
            rows = data["seed"]["tables"][JOINT_LOADS]
            for row in rows:
                if row.get("UniqueName") == "P1" and row.get("LoadPattern") == "DEAD":
                    row["XDim"] = 0.9
            control.write_text(json.dumps(data))
            bad = await rig.host.check_model(rig.key)
            messages = [i["message"] for i in bad.data["issues"] if i["code"] == "READBACK_MISMATCH"]
            assert any("punch_x_mm" in m or "punch_y_mm" in m for m in messages)

    anyio.run(body)


def test_safe_integrity_issues(tmp_path: Path, make_config: ConfigFactory, control: Path, store: ResultStore) -> None:
    """AC18 / §4.7: JOINT_LOAD_ON_MISSING_JOINT and AREA_WITHOUT_SOIL_SUPPORT appear without tolerance."""
    seed = _seed(joint_loads=0)
    seed["tables"][JOINT_LOADS] = [
        {
            "UniqueName": "GONE",
            "LoadPattern": "DEAD",
            "FX": 0.0,
            "FY": 0.0,
            "FZ": -1.0,
            "MX": 0.0,
            "MY": 0.0,
            "MZ": 0.0,
            "XDim": 0.4,
            "YDim": 0.4,
        }
    ]
    seed["tables"]["Area Assignments - Area Springs"] = [
        {"UniqueName": "A1", "SpringProp": "K1"},
        {"UniqueName": "A2", "SpringProp": "None"},
    ]

    async def body() -> None:
        async with _rig(tmp_path, make_config(), control, store, seed=seed) as rig:
            checked = await rig.host.check_model(rig.key)
            found = {(i[1], i[3]) for i in _issues(checked)}
            assert ("JOINT_LOAD_ON_MISSING_JOINT", "GONE") in found
            assert ("AREA_WITHOUT_SOIL_SUPPORT", "A2") in {
                (i[1], i[3]) for i in _issues(checked) if i[0] == "warning"
            } or ("AREA_WITHOUT_SOIL_SUPPORT", "A2") in found

    anyio.run(body)
