"""CSI model-state reader, fingerprint and units read (plan 0002 T11b; spec 0002 AC27, sections 4.5.4, 4.6.4).

The list reads carry the token `kN_mm_C`, so the seeded list values below are millimetres and map to themselves; the
table reads carry no token and are labelled with the model's present units (`kN_m_C`: `kN/m` and `kN/m2` map to
`kN/m` and `kPa` by factor one). The adapter imports are inside the tests so a missing module fails the test.
"""

import hashlib
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.errors import ContractError, ErrorCode, Precondition, WarningCode
from eng_contract.ids import FixedClock, IdSource, SeededIdSource
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.store import LocationClass, ModelStateStore, Workspace

from eng_harness.servers import CallEffect, ServerManager, ServersConfig
from eng_harness.servers._guard import ProcessGuard
from eng_harness.servers._hostlock import HostLocks
from eng_harness.servers._procinfo import ProcessIdentity

from .test_csi_session_ops import ETABS_EXE, LaunchInspector

ConfigFactory = Callable[..., ServersConfig]
_START = 1_700_000_000_000
LIMIT = 2000  # S-12 section 2: every list tool and table read is capped at 2000
KINDS = (
    "model.stories/1",
    "model.grid_system/1",
    "model.frame_placements/1",
    "model.area_placements/1",
    "model.load_set/1",
    "model.joint_restraints/1",
)
STATUS_KIND = "harness.csi_model_status/1"
RESTRAINTS = "Joint Assignments - Restraints"  # the ETABS table key of the product profile (spec 0002 section 4.6.4)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed(*, stories: int = 2, restraints: int = 1) -> dict[str, Any]:
    """A model in the fake: list values in `kN_mm_C` (millimetres), table values in the present `kN_m_C`."""
    return {
        "stories": [
            {
                "name": f"S{n}",
                "elevation": 3000.0 * n,
                "height": 3000.0,
                "is_master": n == 1,
                "similar_to": None if n == 1 else "S1",
            }
            for n in range(1, stories + 1)
        ],
        "grids": [
            {
                "name": "G1",
                "type": "Cartesian",
                "origin": [0.0, 0.0],
                "rotation_deg": 0.0,
                "x_lines": [{"id": "1", "ordinate": 0.0, "visible": True}, {"id": "2", "ordinate": 5000.0}],
                "y_lines": [{"id": "A", "ordinate": 0.0, "visible": True}],
            }
        ],
        "frames": [
            {
                "name": "F1",
                "label": "F1",
                "point1": [0.0, 0.0, 0.0],
                "point2": [0.0, 0.0, 3000.0],
                "section": "C30",
                "story": "S1",
            }
        ],
        "areas": [{"name": "A1", "points": [[0.0, 0.0, 0.0], [5000.0, 0.0, 0.0], [0.0, 5000.0, 0.0]], "section": "SL"}],
        "area_sections": [{"name": "SL", "type": "slab"}],
        "load_patterns": [{"name": "DEAD", "type": "Dead", "self_weight": 1.0}],
        "load_combos": [{"name": "C1", "type": 0, "items": [{"name": "DEAD", "factor": 1.4, "kind": "case"}]}],
        "tables": {
            RESTRAINTS: [
                {"UniqueName": f"P{n}", "Ux": True, "Uy": True, "Uz": True, "Rx": False, "Ry": False, "Rz": False}
                for n in range(restraints)
            ],
            "Load Pattern Definitions": [{"Name": "DEAD", "Type": "Dead", "SelfWtMultpl": 1.0}],
            "Load Combination Definitions": [{"Name": "C1", "Type": "Linear Add"}],
            "Frame Loads Assignments - Distributed": [{"Frame": "F1", "LoadPattern": "DEAD", "Value": 12.5}],
            "Area Load Assignments - Uniform": [{"UniqueName": "A1", "LoadPattern": "DEAD", "Value": 6.25}],
        },
    }


def _seeded(control: Path, **seed: int) -> None:
    control.write_text(json.dumps({"faults": [], "seed": _seed(**seed)}))


def _fault(control: Path, fault: str, tool: str) -> None:
    data = json.loads(control.read_text())
    data["faults"].append({"fault": fault, "tool": tool})
    control.write_text(json.dumps(data))


def _port(
    tmp_path: Path, config: ServersConfig, control: Path, clock: FixedClock, ids: IdSource
) -> tuple[Any, ServerManager, ModelStateStore]:
    """The port with a model-state store, its server and the store, to use inside `async with`."""
    from eng_harness.adapters._hostport import AdapterHostPort
    from eng_harness.adapters._identity import IdentityStore

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    original = tmp_path / "original.EDB"
    original.write_bytes(b"model-v1")
    run_dir = tmp_path / "run"
    inspector = LaunchInspector(control)
    guard = ProcessGuard(inspector, run_dir, host_exes=[ETABS_EXE])
    locks = HostLocks(
        tmp_path / "locks", run_id="b451", engine=ProcessIdentity(os.getpid(), "t0", "python"), clock=clock
    )
    manager = ServerManager(config, run_dir, helpers=guard)
    port = AdapterHostPort(
        identity=IdentityStore(workspace=workspace, states=states, ids=ids),
        states=states,
        sessions=manager,
        guard=guard,
        inspector=inspector,
        locks=locks,
        clock=clock,
        ids=ids,
        run_dir=run_dir,
        product="ETABS",
        program="ETABS",
        exe_name=ETABS_EXE,
        files={"m": original},
    )
    return port, manager, states


async def _write(manager: ServerManager, pid: int, tool: str, **arguments: Any) -> None:
    """An edit sent straight to the fake, as an engineer in the host program would make it."""
    await manager.call("csi", "main", tool, {"target": {"product": "ETABS", "pid": pid}, **arguments}, CallEffect.WRITE)


def test_kinds_and_fingerprint(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """The six kinds and the status validate; one state has one fingerprint; every edit changes it."""
    from eng_harness.adapters.csi._replies import CSI_KINDS

    _seeded(control)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager, _states = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"state", clock))
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            first = await port.model_state(key, held.instance_id)
            assert await port.model_state(key, held.instance_id) == first
            assert first.loaded
            assert re.fullmatch("[0-9a-f]{64}", first.fingerprint or "")
            assert first.file_sha256 == _sha(port.model_files(key)[0])
            assert first.revision == 0

            read = port.last_read(key)
            assert read is not None
            assert read.fingerprint == first.fingerprint
            assert sorted(read.payloads) == sorted(KINDS)
            for kind in KINDS:
                NEUTRAL_KINDS[kind].model_validate(read.payloads[kind].model_dump(mode="json"))
            CSI_KINDS[STATUS_KIND].model_validate(read.status.model_dump(mode="json"))

            stories = read.payloads["model.stories/1"].model_dump(mode="json")
            assert stories["base_elevation_mm"] == 0.0  # lowest story: elevation 3000 - height 3000
            assert [s["elevation_mm"] for s in stories["stories"]] == [3000.0, 6000.0]
            frame = read.payloads["model.frame_placements/1"].model_dump(mode="json")["frames"][0]
            assert frame["j"]["z_mm"] == 3000.0
            loads = read.payloads["model.load_set/1"].model_dump(mode="json")
            assert loads["frame_loads"][0]["w_kN_m"] == 12.5
            assert loads["area_loads"][0]["q_kPa"] == 6.25
            joints = read.payloads["model.joint_restraints/1"].model_dump(mode="json")["joints"]
            assert [(j["joint"], j["ux"], j["rx"]) for j in joints] == [("P0", True, False)]
            assert read.status.units == "kN_m_C"
            assert read.status.locked is False
            assert read.status.file_name == port.model_files(key)[0].name
            assert read.status.object_counts["stories"] == 2

            seen = {first.fingerprint}
            edits: list[tuple[str, dict[str, Any]]] = [
                ("csi_add_point", {"x": 1.0, "y": 2.0, "z": 3.0}),
                ("csi_add_load_pattern", {"name": "LIVE", "type": "Live"}),
                ("csi_add_load_combo", {"name": "C2", "combo_type": 0, "components": []}),
                ("csi_delete_load_combo", {"name": "C1", "confirm": True}),
            ]
            for tool, arguments in edits:
                await _write(manager, held.pid, tool, **arguments)
                port.wrote(key)
                fingerprint = (await port.model_state(key, held.instance_id)).fingerprint
                assert fingerprint not in seen
                seen.add(fingerprint)

    anyio.run(body)


def test_outside_edit_raises_the_revision(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """A fingerprint that changed with no adapter write, or a file saved outside, is a new revision with a warning."""
    _seeded(control)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager, states = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"outside", clock))
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            first = await port.model_state(key, held.instance_id)
            assert port.take_warnings() == []

            await _write(manager, held.pid, "csi_add_point", x=1.0, y=2.0, z=3.0)  # not through the port
            second = await port.model_state(key, held.instance_id)
            assert second.fingerprint != first.fingerprint
            assert second.revision == (first.revision or 0) + 1
            assert port.take_warnings() == [(key, WarningCode.MODEL_CHANGED_OUTSIDE)]
            assert port.take_warnings() == []
            stored = states.get(second.model_id or "")
            assert stored is not None
            assert (stored.revision, stored.fingerprint, stored.file_sha256) == (second.revision, second.fingerprint, None)
            assert await port.model_state(key, held.instance_id) == second  # nothing changed: nothing raised
            assert port.take_warnings() == []

            await _write(manager, held.pid, "csi_add_point", x=4.0, y=5.0, z=6.0)
            port.wrote(key)  # the adapter's own write is not an outside edit
            third = await port.model_state(key, held.instance_id)
            assert third.fingerprint != second.fingerprint
            assert third.revision == second.revision
            assert port.take_warnings() == []
            await _write(manager, held.pid, "csi_add_point", x=7.0, y=8.0, z=9.0)  # the mark covers one read only
            assert (await port.model_state(key, held.instance_id)).revision == third.revision + 1
            assert port.take_warnings() == [(key, WarningCode.MODEL_CHANGED_OUTSIDE)]

            saved = await port.save(key, "baseline")
            after_save = await port.model_state(key, held.instance_id)
            assert after_save.revision == saved.revision
            assert after_save.file_sha256 == saved.file_sha256
            assert port.take_warnings() == []

            path = port.model_files(key)[0]
            path.write_bytes(path.read_bytes() + b"saved by the engineer")
            outside = await port.model_state(key, held.instance_id)
            assert outside.revision == saved.revision + 1
            assert outside.file_sha256 == _sha(path)
            assert port.take_warnings() == [(key, WarningCode.MODEL_CHANGED_OUTSIDE)]

            restored = await port.restore(key, saved.model_copy(update={"file_sha256": _sha(path)}))
            await _write(manager, restored.pid, "csi_add_point", x=1.0, y=1.0, z=1.0)
            again = await port.model_state(key, restored.instance_id)
            assert again.loaded  # a restore starts a new baseline: the first read after it raises nothing
            assert port.take_warnings() == []

    anyio.run(body)


@pytest.mark.parametrize(
    ("seed", "where"), [({"stories": LIMIT + 1}, "csi_list_stories"), ({"restraints": LIMIT + 1}, RESTRAINTS)]
)
def test_truncated_read_is_limit_exceeded(
    tmp_path: Path, make_config: ConfigFactory, control: Path, seed: dict[str, int], where: str
) -> None:
    """A list or a table cut at 2000 rows raises `LIMIT_EXCEEDED` with the count, and the exact limit passes."""
    _seeded(control, **seed)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager, _states = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"limit", clock))
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            with pytest.raises(ContractError, match=where) as refused:
                await port.model_state(key, held.instance_id)
            assert refused.value.detail.code is ErrorCode.LIMIT_EXCEEDED
            assert refused.value.detail.received == LIMIT

    anyio.run(body)


def test_exactly_the_limit_is_read(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """Exactly 2000 stories are not truncated."""
    _seeded(control, stories=LIMIT)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager, _states = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"exact", clock))
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            assert (await port.model_state(key, held.instance_id)).loaded

    anyio.run(body)


def test_units_and_the_units_trap(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """`read_units` compares the present units with those at open; a read that leaves them changed is refused."""
    _seeded(control)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager, _states = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"units", clock))
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            ok = await port.read_units(key, held.instance_id)
            assert (ok.loaded, ok.ok, ok.present, ok.expected) == (True, True, "kN_m_C", "kN_m_C")

            _fault(control, "units_left_changed", "csi_list_stories")
            with pytest.raises(ContractError) as trapped:
                await port.model_state(key, held.instance_id)
            assert trapped.value.detail.code is ErrorCode.PRECONDITION_FAILED
            assert trapped.value.detail.precondition is Precondition.units_verified
            assert trapped.value.detail.received == "kN_mm_C"
            bad = await port.read_units(key, held.instance_id)
            assert (bad.loaded, bad.ok, bad.present, bad.expected) == (True, False, "kN_mm_C", "kN_m_C")

    anyio.run(body)


def test_not_loaded_never_raises(tmp_path: Path, make_config: ConfigFactory, control: Path) -> None:
    """An unbound model, another instance or a closed instance gives `loaded` false from both reads."""
    _seeded(control)
    clock = FixedClock(_START)

    async def body() -> None:
        port, manager, _states = _port(tmp_path, make_config(), control, clock, SeededIdSource(b"absent", clock))
        async with manager:
            key = await port.working_copy("m", tmp_path / "run" / "copies")
            held = await port.locate(key)
            assert held is not None
            for model, instance in (("missing", held.instance_id), (key, "another")):
                state = await port.model_state(model, instance)
                assert state.loaded is False
                assert state.fingerprint is None
                units = await port.read_units(model, instance)
                assert (units.loaded, units.ok, units.present) == (False, True, None)
            assert (await port.read_units(key, "another")).expected == "kN_m_C"
            assert (await port.read_units("missing", "x")).expected == ""
            await port.close_started("csi", [held])
            assert (await port.model_state(key, held.instance_id)).loaded is False
            assert (await port.read_units(key, held.instance_id)).loaded is False

    anyio.run(body)


def _recorder(
    replies: dict[str, dict[str, Any]],
) -> tuple[list[tuple[str, dict[str, Any], CallEffect]], Callable[..., Any]]:
    calls: list[tuple[str, dict[str, Any], CallEffect]] = []

    async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        calls.append((tool, arguments, effect))
        return replies.get(tool, {"items": [], "rows": [], "truncated": False})

    return calls, call


_INFO = {"units": "kN_m_C", "locked": None, "object_counts": {"frames": 3}, "program_version": "22.0.0"}


def test_reads_are_capped_tokened_and_targeted() -> None:
    """Spec 4.6.4: limit 2000 on every list, row limit 2000 on every table, a token only where the tool takes one."""
    from eng_harness.adapters.csi import products
    from eng_harness.adapters.csi._state import CsiStateReader

    calls, call = _recorder({"csi_model_info": _INFO})

    async def body() -> None:
        read = await CsiStateReader(product="ETABS", call=call).read(77, Path("/runs/tower.EDB"))
        assert read.status.locked is None
        assert read.status.object_counts == {"frames": 3}

    anyio.run(body)

    assert all(effect is CallEffect.READ for _, _, effect in calls)
    assert all(arguments["target"] == {"product": "ETABS", "pid": 77} for _, arguments, _ in calls)
    assert [tool for tool, _, _ in calls] == [
        "csi_model_info",
        "csi_list_stories",
        "csi_list_grids",
        "csi_list_frames",
        "csi_list_areas",
        "csi_list_load_patterns",
        "csi_list_load_combos",
        "csi_list_area_sections",
        *["csi_db_table_read"] * 5,
        "csi_model_info",
    ]
    for tool, arguments, _ in calls:
        if tool.startswith("csi_list_"):
            tokened = tool in {"csi_list_stories", "csi_list_grids", "csi_list_frames", "csi_list_areas"}
            assert arguments.get("units") == ("kN_mm_C" if tokened else None)
            assert arguments["limit"] == LIMIT
    tables = products.profile("ETABS").tables
    read_tables = [args["table"] for tool, args, _ in calls if tool == "csi_db_table_read"]
    assert sorted(read_tables) == sorted(tables.values())
    assert all(args["row_limit"] == LIMIT for tool, args, _ in calls if tool == "csi_db_table_read")


def test_unusable_reply_is_refused() -> None:
    """A list reply without `items` is `HOST_ERROR` with `UNEXPECTED_REPLY`, not an empty list."""
    from eng_harness.adapters.csi._state import CsiStateReader

    _calls, call = _recorder({"csi_model_info": _INFO, "csi_list_grids": {"count": 0, "truncated": False}})

    async def body() -> None:
        with pytest.raises(ContractError) as refused:
            await CsiStateReader(product="ETABS", call=call).read(1, None)
        assert refused.value.detail.code is ErrorCode.HOST_ERROR
        assert refused.value.detail.host_code == "UNEXPECTED_REPLY"
        assert refused.value.detail.field == "items"
        assert "csi_list_grids" in refused.value.detail.message

    anyio.run(body)


def test_fingerprint_layout() -> None:
    """The fingerprint is the SHA-256 of the canonical JSON of the sections and the counts, rows ordered."""
    from eng_harness.adapters.csi._state import fingerprint

    sections = {
        "model.stories/1": {"stories": [{"name": "b", "elevation": 2.0}, {"name": "a", "elevation": 1.0}]},
        "model.frame_placements/1": {"frames": [{"name": "f", "point": [3.0, 1.0, 2.0]}]},
    }
    # By hand (RFC 8785): keys sorted, 1.0 written 1, the two story objects ordered by their canonical text
    # ({"elevation":1,"name":"a"} before {"elevation":2,"name":"b"}), the coordinate list kept as [3,1,2].
    text = (
        '{"object_counts":{"frames":1,"points":2},"sections":{"model.frame_placements/1":'
        '{"frames":[{"name":"f","point":[3,1,2]}]},"model.stories/1":'
        '{"stories":[{"elevation":1,"name":"a"},{"elevation":2,"name":"b"}]}}}'
    )
    assert fingerprint(sections, {"points": 2, "frames": 1}) == hashlib.sha256(text.encode()).hexdigest()
