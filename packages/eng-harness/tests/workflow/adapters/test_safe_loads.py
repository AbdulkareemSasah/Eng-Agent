"""SAFE joint-load import (plan 0008 T6; spec 0008 AC14 to AC17, section 4.3).

Adapter imports sit inside the tests so a missing module fails the test. Expected host arguments and units follow
spec 0008 AC14 (token always `kN_m_C`) and the S-12 `csi_set_point_load` schema.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import HostInfo
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ModelStateStore, ResultStore, Workspace

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.errors import HarnessCode, NotImplementedGap
from eng_harness.ports import ServerCheck
from eng_harness.servers import ServerManager, ServersConfig
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


def _calls(control: Path) -> list[dict[str, Any]]:
    data = json.loads(control.read_text())
    calls = data.get("calls", [])
    assert isinstance(calls, list)
    return calls


def _seed_control(
    control: Path,
    seed: dict[str, Any] | None = None,
    *,
    faults: list[dict[str, Any]] | None = None,
) -> None:
    control.write_text(
        json.dumps({"faults": faults or [], "seed": seed if seed is not None else _seed(), "product": "SAFE"})
    )


def test_set_point_load_mapping() -> None:
    """AC14: each row maps to `csi_set_point_load` with force, moment and units token `kN_m_C`."""
    from eng_harness.adapters.csi import csi_allowlist
    from eng_harness.adapters.csi.products import _safe_loads as loads

    binding = Binding(target=HostTarget(product="SAFE", pid=4242), units_system="kN_m_C")
    model = loads.SetPointLoadArgs(
        model="m",
        joint="P1",
        pattern="DEAD",
        FX_kN=1.0,
        FY_kN=2.0,
        FZ_kN=-100.0,
        MX_kNm=0.5,
        MY_kNm=0.0,
        MZ_kNm=-1.25,
    )
    built = loads.EDIT_BUILDERS["csi_set_point_load"](
        model, csi_allowlist().for_product("SAFE").descriptor("csi_set_point_load"), binding
    )
    assert built == {
        "name": "P1",
        "load_pattern": "DEAD",
        "force": [1.0, 2.0, -100.0],
        "moment": [0.5, 0.0, -1.25],
    }
    assert loads.TOKENS["csi_set_point_load"] == "kN_m_C"


def test_zero_rows(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC15: all-zero with no table row → skip + ZERO_LOAD_SKIPPED; with a row → SG-8, no write."""
    from eng_harness._kinds import JointLoad, JointLoads
    from eng_harness.adapters.csi.products import _safe_loads as loads

    async def skip_when_absent() -> None:
        seed = _seed(joint_loads=0)
        seed["load_patterns"].append({"name": "LIVE", "type": "Live", "self_weight": 0.0})
        seed["tables"]["Load Pattern Definitions"].append({"Name": "LIVE", "Type": "Live", "SelfWtMultpl": 0.0})
        seed["tables"][JOINT_LOADS] = []
        _seed_control(control, seed)
        async with _import_rig(tmp_path / "skip", make_config(), control) as rig:
            skip = JointLoads(
                loads=[
                    JointLoad(
                        joint="P1",
                        pattern="LIVE",
                        fx_kn=0.0,
                        fy_kn=0.0,
                        fz_kn=0.0,
                        mx_knm=0.0,
                        my_knm=0.0,
                        mz_knm=0.0,
                    )
                ]
            )
            result = await loads.import_joint_loads(rig.port, rig.host, rig.key, skip, op_id_prefix="s")
            assert [w.code for w in result.warnings] == ["ZERO_LOAD_SKIPPED"]
            assert [c["tool"] for c in _calls(control) if c["tool"] == "csi_set_point_load"] == []

    async def gap_when_present() -> None:
        seed = _seed(joint_loads=0)
        seed["tables"][JOINT_LOADS] = [
            {
                "UniqueName": "P1",
                "LoadPattern": "DEAD",
                "FX": 1.0,
                "FY": 0.0,
                "FZ": 0.0,
                "MX": 0.0,
                "MY": 0.0,
                "MZ": 0.0,
                "XDim": 0.4,
                "YDim": 0.4,
            }
        ]
        _seed_control(control, seed)
        async with _import_rig(tmp_path / "gap", make_config(), control) as rig:
            clear = JointLoads(
                loads=[
                    JointLoad(
                        joint="P1",
                        pattern="DEAD",
                        fx_kn=0.0,
                        fy_kn=0.0,
                        fz_kn=0.0,
                        mx_knm=0.0,
                        my_knm=0.0,
                        mz_knm=0.0,
                    )
                ]
            )
            with pytest.raises(NotImplementedGap) as caught:
                await loads.import_joint_loads(rig.port, rig.host, rig.key, clear, op_id_prefix="z")
            assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
            assert caught.value.evidence == ("SG-8",)
            assert [c["tool"] for c in _calls(control) if c["tool"] == "csi_set_point_load"] == []

    async def body() -> None:
        await skip_when_absent()
        await gap_when_present()

    anyio.run(body)


def test_missing_joint_no_partial_write(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC16: missing joint or pattern → NOT_FOUND before any write; no partial batch."""
    from eng_harness._kinds import JointLoad, JointLoads
    from eng_harness.adapters.csi.products import _safe_loads as loads

    _seed_control(control, _seed(joint_loads=0))

    async def body() -> None:
        async with _import_rig(tmp_path, make_config(), control) as rig:
            payload = JointLoads(
                loads=[
                    JointLoad(
                        joint="P1",
                        pattern="DEAD",
                        fx_kn=0.0,
                        fy_kn=0.0,
                        fz_kn=-50.0,
                        mx_knm=0.0,
                        my_knm=0.0,
                        mz_knm=0.0,
                    ),
                    JointLoad(
                        joint="MISSING",
                        pattern="DEAD",
                        fx_kn=0.0,
                        fy_kn=0.0,
                        fz_kn=-10.0,
                        mx_knm=0.0,
                        my_knm=0.0,
                        mz_knm=0.0,
                    ),
                ]
            )
            with pytest.raises(ContractError) as refused:
                await loads.import_joint_loads(rig.port, rig.host, rig.key, payload, op_id_prefix="b")
            assert refused.value.detail.code is ErrorCode.NOT_FOUND
            assert refused.value.detail.field is not None
            assert [c["tool"] for c in _calls(control) if c["tool"] == "csi_set_point_load"] == []

            bad_pattern = JointLoads(
                loads=[
                    JointLoad(
                        joint="P1",
                        pattern="NOPE",
                        fx_kn=0.0,
                        fy_kn=0.0,
                        fz_kn=-10.0,
                        mx_knm=0.0,
                        my_knm=0.0,
                        mz_knm=0.0,
                    )
                ]
            )
            with pytest.raises(ContractError) as refused_pat:
                await loads.import_joint_loads(rig.port, rig.host, rig.key, bad_pattern, op_id_prefix="p")
            assert refused_pat.value.detail.code is ErrorCode.NOT_FOUND
            assert [c["tool"] for c in _calls(control) if c["tool"] == "csi_set_point_load"] == []

    anyio.run(body)


def test_punch_dimensions_gap() -> None:
    """AC16: a non-null punch dimension on a write row is gap SG-7."""
    from eng_harness._kinds import JointLoad, JointLoads
    from eng_harness.adapters.csi.products import _safe_loads as loads

    payload = JointLoads(
        loads=[
            JointLoad(
                joint="P1",
                pattern="DEAD",
                fx_kn=0.0,
                fy_kn=0.0,
                fz_kn=-10.0,
                mx_knm=0.0,
                my_knm=0.0,
                mz_knm=0.0,
                punch_x_mm=400.0,
                punch_y_mm=None,
            )
        ]
    )
    with pytest.raises(NotImplementedGap) as caught:
        loads.validate_import(payload, joints={"P1"}, patterns={"DEAD"}, existing={})
    assert caught.value.evidence == ("SG-7",)


def test_units_token_independent_of_present_units(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """AC17: with present units mm, the import still passes `kN_m_C` and read-back matches."""
    from eng_harness._kinds import JointLoad, JointLoads
    from eng_harness.adapters.csi.products import _safe_loads as loads

    # Seed one existing load so Replace keeps XDim/YDim (field map requires them; fake preserves them).
    _seed_control(
        control,
        _seed(joint_loads=1),
        faults=[{"fault": "present_units_mm", "tool": "csi_set_point_load"}],
    )

    async def body() -> None:
        async with _import_rig(tmp_path, make_config(), control) as rig:
            payload = JointLoads(
                loads=[
                    JointLoad(
                        joint="P1",
                        pattern="DEAD",
                        fx_kn=0.0,
                        fy_kn=0.0,
                        fz_kn=-80.0,
                        mx_knm=1.0,
                        my_knm=0.0,
                        mz_knm=0.0,
                    )
                ]
            )
            result = await loads.import_joint_loads(rig.port, rig.host, rig.key, payload, op_id_prefix="u")
            assert result.written == 1
            assert [c["tool"] for c in _calls(control)].count("csi_set_point_load") == 1
            # Token always `kN_m_C` (TOKENS): with present units mm the read-back still matches in kN / kN.m.
            assert loads.TOKENS["csi_set_point_load"] == "kN_m_C"
            held = await rig.host.locate(rig.key)
            assert held is not None
            await rig.host.model_state(rig.key, held.instance_id)
            read = rig.host.last_read(rig.key)
            assert read is not None
            joint = read.payloads["harness.joint_loads/1"].model_dump(mode="json")["loads"]
            row = next(r for r in joint if r["joint"] == "P1" and r["pattern"] == "DEAD")
            assert abs(row["FZ_kN"] - (-80.0)) <= 0.001 * 80.0
            assert abs(row["MX_kNm"] - 1.0) <= 0.001 * 1.0

    anyio.run(body)


class _Binder:
    def __init__(self, pid: int) -> None:
        self.pid = pid

    async def binding(self, host_key: str, model: str | None, descriptor: Any) -> Binding:
        return Binding(
            target=HostTarget(product="SAFE", pid=self.pid),
            units_system=None,
            host=HostInfo(
                program="SAFE", version="22.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0
            ),
            owned=True,
        )

    def revision(self, model_id: str) -> int | None:
        return None


class _ImportRig:
    def __init__(self, host: Any, port: Any, key: str, manager: ServerManager) -> None:
        self.host, self.port, self.key, self.manager = host, port, key, manager


@asynccontextmanager
async def _import_rig(tmp_path: Path, config: ServersConfig, control: Path) -> AsyncIterator[_ImportRig]:
    from eng_harness._kinds import HARNESS_KINDS
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore
    from eng_harness.adapters.csi._checks import ReadBack, WrittenItems
    from eng_harness.adapters.csi._tools import CsiToolPort

    clock = FixedClock(_START, 1)
    ids = SeededIdSource(b"safe-loads", clock)
    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    store = ResultStore(workspace, HARNESS_KINDS, ids, clock)
    tmp_path.mkdir(parents=True, exist_ok=True)
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
    readback = ReadBack(written=written, store=store, check=CHECK, tolerance_ratio=0.001)
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
        assert held is not None
        assert held.pid is not None
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
        yield _ImportRig(host, port, key, manager)
