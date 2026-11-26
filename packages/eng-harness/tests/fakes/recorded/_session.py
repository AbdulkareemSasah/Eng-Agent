"""Sessions on the synthetic CSI and Revit fakes, plain or recorded (plan 0002 T17; plan 0011 T13).

`record_synthetic` / `record_revit_synthetic` run a short scripted session on the synthetic fake process through
`RecordMode`, which gives the contract tests a recording to work on until the owner commits real ones.
`replay_on_fake` / `replay_on_revit_fake` send the requests of a recording to a fresh fake and return what the fake
answers.
"""

import json
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
from mcp import Client
from mcp.client.stdio import get_default_environment

from eng_harness.adapters.csi._state import CsiStateReader
from eng_harness.servers import CallEffect, Recording, RecordMode
from eng_harness.servers._launcher import JobPolicy, LaunchSpec, PosixLauncher
from eng_harness.servers._session import reply_body
from eng_harness.servers._transport import ProcessTransport

SERVER = Path(__file__).resolve().parents[1] / "sasaah_csi" / "server.py"
SEED = {  # a small model: list values in kN_mm_C (millimetres), table values in the present kN_m_C
    "stories": [{"name": "S1", "elevation": 3000.0, "height": 3000.0, "is_master": True, "similar_to": None}],
    "grids": [
        {
            "name": "G1", "type": "Cartesian", "origin": [0.0, 0.0], "rotation_deg": 0.0,
            "x_lines": [{"id": "1", "ordinate": 0.0, "visible": True}, {"id": "2", "ordinate": 5000.0}],
            "y_lines": [{"id": "A", "ordinate": 0.0, "visible": True}],
        }
    ],
    "frames": [
        {
            "name": "F1", "label": "F1", "point1": [0.0, 0.0, 0.0], "point2": [0.0, 0.0, 3000.0], "section": "C30",
            "story": "S1",
        }
    ],
    "areas": [{"name": "A1", "points": [[0.0, 0.0, 0.0], [5000.0, 0.0, 0.0], [0.0, 5000.0, 0.0]], "section": "SL"}],
    "area_sections": [{"name": "SL", "type": "slab"}],
    "load_patterns": [{"name": "DEAD", "type": "Dead", "self_weight": 1.0}],
    "load_cases": [{"name": "DEAD"}, {"name": "LIVE"}],
    "load_combos": [{"name": "C1", "type": 0, "items": [{"name": "DEAD", "factor": 1.4, "kind": "case"}]}],
    "tables": {
        "Joint Assignments - Restraints": [
            {"UniqueName": "P1", "Ux": True, "Uy": True, "Uz": True, "Rx": False, "Ry": False, "Rz": False}
        ],
        "Load Pattern Definitions": [{"Name": "DEAD", "Type": "Dead", "SelfWtMultpl": 1.0}],
        "Load Combination Definitions": [{"Name": "C1", "Type": "Linear Add"}],
        "Frame Loads Assignments - Distributed": [{"Frame": "F1", "LoadPattern": "DEAD", "Value": 12.5}],
        "Area Load Assignments - Uniform": [{"UniqueName": "A1", "LoadPattern": "DEAD", "Value": 6.25}],
    },
    "results": {
        "csi_results_joint_reactions": [
            {"joint": "J1", "case": "DEAD", "F1": 1.5, "F2": -2.0, "F3": 120.25, "M1": 0.5, "M2": -0.25, "M3": 0.0},
        ],
    },
}  # fmt: skip
USER = "jdoe"  # the stand-in user and home of the scripted session: the sanitizer must remove both
# SAFE synthetic seed: state tables of plan 0008 T5 plus soil pressures and reaction results (spec 0008 §4.4, §4.6).
SAFE_SEED: dict[str, Any] = {
    "grids": [
        {
            "name": "G1", "type": "Cartesian", "origin": [0.0, 0.0], "rotation_deg": 0.0,
            "x_lines": [{"id": "1", "ordinate": 0.0, "visible": True}, {"id": "2", "ordinate": 4000.0}],
            "y_lines": [{"id": "A", "ordinate": 0.0, "visible": True}],
        }
    ],
    "points": [{"name": "P1", "x": 1000.0, "y": 500.0, "z": 0.0}],
    "frames": [
        {
            "name": "B1", "label": "B1", "point1": [0.0, 0.0, 0.0], "point2": [4000.0, 0.0, 0.0],
            "section": "GB", "story": "",
        }
    ],
    "areas": [
        {
            "name": "A1",
            "points": [[0.0, 0.0, 0.0], [4000.0, 0.0, 0.0], [4000.0, 4000.0, 0.0], [0.0, 4000.0, 0.0]],
            "section": "FOOT",
        }
    ],
    "load_patterns": [{"name": "DEAD", "type": "Dead", "self_weight": 1.0}],
    "load_combos": [{"name": "C1", "type": 0, "items": [{"name": "DEAD", "factor": 1.4, "kind": "case"}]}],
    "tables": {
        "Slab Property Definitions": [
            {"Name": "FOOT", "PropType": "Footing", "Material": "C30", "Thickness": 0.5},
        ],
        "Material Properties - General": [{"Material": "C30", "Type": "Concrete"}],
        "Material Properties - Basic Mechanical Properties": [
            {"Material": "C30", "UnitWeight": 24.0, "E1": 30_000.0, "U12": 0.2}
        ],
        "Material Properties - Concrete Data": [{"Material": "C30", "Fc": 30_000.0}],
        "Load Pattern Definitions": [{"Name": "DEAD", "Type": "Dead", "SelfWtMultpl": 1.0}],
        "Load Combination Definitions": [{"Name": "C1", "Type": "Linear Add"}],
        "Joint Loads Assignments - Force": [
            {
                "UniqueName": "P1", "LoadPattern": "DEAD", "FX": 0.0, "FY": 0.0, "FZ": -100.0,
                "MX": 0.0, "MY": 0.0, "MZ": 0.0, "XDim": 0.4, "YDim": 0.4,
            }
        ],
        "Spring Property Definitions - Area Springs": [
            {
                "Name": "K1", "StiffOpt": "Link", "StiffU1": 0.0, "StiffU2": 0.0, "StiffU3": 20000.0,
                "NonlinOpt3": "Compression Only",
            }
        ],
        "Area Assignments - Area Springs": [{"UniqueName": "A1", "SpringProp": "K1"}],
        "Soil Pressures": [
            {
                "UniqueName": "A1", "ShellElm": "E1", "Joint": "J1", "OutputCase": "DEAD",
                "StepType": "Max", "CaseType": "LinStatic", "Pressure": 12.5,
            }
        ],
    },
    "results": {
        "csi_results_base_reactions": [
            {"case": "DEAD", "F1": 1.0, "F2": -2.0, "F3": 50.0, "M1": 0.5, "M2": -0.25, "M3": 0.0}
        ],
        "csi_results_joint_reactions": [
            {"joint": "P1", "case": "DEAD", "F1": 0.0, "F2": 0.0, "F3": -100.0, "M1": 0.0, "M2": 0.0, "M3": 0.0}
        ],
    },
}  # fmt: skip
# SAP2000 synthetic seed: state of plan 0012 T4 plus force/reaction results of T6 (spec 0012 §4.3, AC15).
# Values match test_sap2000_state._seed and test_sap2000_results._SEED (no invented numbers or table keys).
SAP2000_SEED: dict[str, Any] = {
    "points": [{"name": "P1", "x": 1000.0, "y": 500.0, "z": 0.0}],
    "frames": [
        {"name": "F1", "point1": [0.0, 0.0, 0.0], "point2": [0.0, 0.0, 3000.0], "section": "C300"},
    ],
    "areas": [
        {
            "name": "A1",
            "points": [[0.0, 0.0, 0.0], [4000.0, 0.0, 0.0], [4000.0, 4000.0, 0.0], [0.0, 4000.0, 0.0]],
            "section": "SLAB1",
        }
    ],
    "frame_sections": [{"name": "C300"}, {"name": "C400"}],
    "area_sections": [{"name": "SLAB1", "type": "slab"}],
    "materials": [{"name": "C30"}],
    "load_patterns": [{"name": "DEAD", "type": "Dead", "self_weight": 1.0}],
    "load_cases": [{"name": "DEAD"}, {"name": "LIVE"}],
    "load_combos": [{"name": "C1", "type": 0, "items": [{"name": "DEAD", "factor": 1.4, "kind": "case"}]}],
    "tables": {},
    "results": {
        "csi_results_joint_reactions": [
            {"joint": "J1", "case": "DEAD", "F1": 1.5, "F2": -2.0, "F3": 120.25, "M1": 0.5, "M2": -0.25, "M3": 0.0},
        ],
        "csi_results_frame_forces": [
            {
                "frame": "B1",
                "case": "1.4D",
                "kind": "combo",
                "station": 1.25,
                "step": "Max",
                "P": -10.0,
                "V2": 4.5,
                "V3": 0.0,
                "T": 0.0,
                "M2": 0.0,
                "M3": -7.75,
            },
            {
                "frame": "B1",
                "case": "1.4D",
                "kind": "combo",
                "station": 1.25,
                "step": "Min",
                "P": -8.0,
                "V2": 3.0,
                "V3": 0.0,
                "T": 0.0,
                "M2": 0.0,
                "M3": -5.0,
            },
        ],
        "csi_results_base_reactions": [
            {"case": "DEAD", "F1": 1.0, "F2": -2.0, "F3": 50.0, "M1": 0.5, "M2": -0.25, "M3": 0.0},
        ],
    },
}  # fmt: skip


@asynccontextmanager
async def fake_client(
    run_dir: Path,
    seed: Mapping[str, Any] = SEED,
    *,
    recording: Recording | None = None,
    product: str = "ETABS",
) -> AsyncIterator[Client]:
    """A client on a fresh synthetic fake process (seeded); with `recording` every exchange is recorded."""
    control = run_dir / "control.json"
    control.write_text(json.dumps({"faults": [], "seed": dict(seed), "product": product}))
    spec = LaunchSpec(
        argv=[sys.executable, str(SERVER)],
        env={**get_default_environment(), "SASAAH_CSI_FAKE_CONTROL": str(control)},
        cwd=run_dir, stderr_path=run_dir / "servers" / "fake.stderr.log", job=JobPolicy.SERVER,
    )  # fmt: skip
    transport = ProcessTransport(PosixLauncher().start(spec), grace_s=5.0)
    async with Client(
        transport if recording is None else RecordMode(transport, recording), mode="legacy", cache=None,
        read_timeout_seconds=None,
    ) as client:  # fmt: skip
        yield client


async def _body(client: Client, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """The reply body of a call; an error reply is the body too (the scripted session provokes some)."""
    body = reply_body(await client.call_tool(tool, arguments))
    assert body is not None
    return body


async def scripted_session(client: Client, home: str, *, product: str = "ETABS") -> None:
    """Launch, open a model under `home`, read the model state as the adapter does, analysis and results, two errors."""
    await client.list_tools()
    await _body(client, "csi_status", {})
    pid = (await _body(client, "csi_launch", {"product": product}))["pid"]
    target = {"target": {"product": product, "pid": pid}}
    extension = {"ETABS": ".EDB", "SAFE": ".FDB", "SAP2000": ".SDB"}[product]
    model = f"{home}/Clients/Acme Tower/Tower-A{extension}"
    await _body(client, "csi_open_model", {"path": model, "confirm": True, **target})

    async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        body = await _body(client, tool, arguments)
        assert "code" not in body, body
        return body

    if product == "SAFE":
        from eng_harness.adapters.csi.products._safe_state import SafeStateReader

        await SafeStateReader(product=product, call=call).read(pid, Path(model))
        await _body(client, "csi_db_table_read", {"table": "Project Information", **target})  # dropped by record mode
        await _body(client, "csi_results_joint_reactions", {"cases": ["DEAD"], "units": "kN_m_C", **target})
        await _body(client, "csi_results_base_reactions", {"cases": ["DEAD"], "units": "kN_m_C", **target})
        await _body(client, "csi_run_analysis", target)  # no `confirm`: the host refuses
        await _body(client, "csi_analysis_status", target)
        return

    if product == "SAP2000":
        from eng_harness.adapters.csi.products._sap2000_state import Sap2000StateReader

        # No Project Information read: SAP2000 table names beyond Analysis Messages are OQ-Q102 (keep unknown).
        await Sap2000StateReader(product=product, call=call).read(pid, Path(model))
        await _body(client, "csi_results_joint_reactions", {"cases": ["DEAD"], "units": "kN_m_C", **target})
        await _body(client, "csi_results_frame_forces", {"cases": ["1.4D"], "units": "kN_m_C", **target})
        await _body(client, "csi_run_analysis", target)  # no `confirm`: the host refuses
        await _body(client, "csi_analysis_status", target)
        return

    await CsiStateReader(product=product, call=call).read(pid, Path(model))
    await _body(client, "csi_db_table_read", {"table": "Project Information", **target})  # dropped by record mode
    await _body(client, "csi_results_joint_reactions", {"cases": ["DEAD"], "units": "kN_m_C", **target})
    await _body(client, "csi_run_analysis", target)  # no `confirm`: the host refuses
    await _body(client, "csi_design_results", {"kind": "steel", **target})  # no design run: a `csi_error` reply
    await _body(client, "csi_analysis_status", target)


def _seed_for(product: str) -> Mapping[str, Any]:
    """Synthetic seed for the product's scripted session (ETABS / SAFE / SAP2000)."""
    if product == "SAFE":
        return SAFE_SEED
    if product == "SAP2000":
        return SAP2000_SEED
    return SEED


def record_synthetic(
    directory: Path, run_dir: Path, *, tool_names: frozenset[str] | None = None, product: str = "ETABS"
) -> Path:
    """Record the scripted session on the synthetic fake into `directory`; returns the manifest path."""
    home = "/home/" + USER
    recording = Recording(
        directory, run_dir, adapter="sasaah-csi-mcp", build="synthetic", tool_names=tool_names, user=USER, home=home
    )
    seed: Mapping[str, Any] = _seed_for(product)

    async def session() -> None:
        async with fake_client(run_dir, seed, recording=recording, product=product) as client:
            await scripted_session(client, home, product=product)

    anyio.run(session)
    return directory / "manifest.json"


def replay_on_fake(
    host: Any,
    run_dir: Path,
    seed: Mapping[str, Any] | None = None,
    *,
    product: str = "ETABS",
) -> list[tuple[Any, dict[str, Any]]]:
    """Send every recorded `tools/call` of `host` to a fresh synthetic fake, in recorded order; pairs with the reply."""
    answers: list[tuple[Any, dict[str, Any]]] = []
    used = _seed_for(product) if seed is None else seed

    async def session() -> None:
        async with fake_client(run_dir, used, product=product) as client:
            for exchange in host.calls:
                reply = await client.call_tool(exchange.tool, exchange.arguments)
                answers.append((exchange, reply.model_dump(mode="json", by_alias=True, exclude_none=True)))

    anyio.run(session)
    return answers


# --- Revit synthetic record mode (plan 0011 T13; spec 0011 AC31, section 4.13) ---

REVIT_SERVER = Path(__file__).resolve().parents[1] / "sasaah_revit" / "server.py"
# Seed used by the scripted Revit session: default fake model is enough; open_model sets path and title.
REVIT_SEED: dict[str, Any] = {}


@asynccontextmanager
async def revit_fake_client(
    run_dir: Path,
    seed: Mapping[str, Any] = REVIT_SEED,
    *,
    recording: Recording | None = None,
) -> AsyncIterator[Client]:
    """A client on a fresh synthetic Revit fake process; with `recording` every exchange is recorded."""
    control = run_dir / "control.json"
    control.write_text(json.dumps({"faults": [], "seed": dict(seed)}))
    spec = LaunchSpec(
        argv=[sys.executable, str(REVIT_SERVER)],
        env={**get_default_environment(), "SASAAH_REVIT_FAKE_CONTROL": str(control)},
        cwd=run_dir, stderr_path=run_dir / "servers" / "revit-fake.stderr.log", job=JobPolicy.SERVER,
    )  # fmt: skip
    transport = ProcessTransport(PosixLauncher().start(spec), grace_s=5.0)
    async with Client(
        transport if recording is None else RecordMode(transport, recording), mode="legacy", cache=None,
        read_timeout_seconds=None,
    ) as client:  # fmt: skip
        yield client


async def scripted_revit_session(client: Client, home: str) -> None:
    """Open a model under `home` and read the model state as the adapter does (spec 0011 section 4.9).

    Connection status is read inside `RevitStateReader` after open, so the default fake document path is not
    recorded before the working-copy path (and does not take the first model placeholder).
    """
    from eng_harness.adapters.revit._parameters import load_role_map
    from eng_harness.adapters.revit._state import RevitStateReader

    await client.list_tools()
    model = f"{home}/Clients/Acme Tower/Tower-A.rvt"
    await _body(client, "revit_open_model", {"path": model, "activate": True})

    async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        reply = await client.call_tool(tool, arguments)
        dump = reply.model_dump(mode="json", by_alias=True, exclude_none=True)
        assert not reply.is_error, dump
        return dump

    await RevitStateReader(call=call, role_map=load_role_map({}), catalog_version="synthetic").read(
        bound_path=Path(model)
    )


def record_revit_synthetic(directory: Path, run_dir: Path, *, tool_names: frozenset[str] | None = None) -> Path:
    """Record the scripted Revit session on the synthetic fake into `directory`; returns the manifest path."""
    home = "/home/" + USER
    recording = Recording(
        directory, run_dir, adapter="sasaah-revit-mcp", build="synthetic", tool_names=tool_names, user=USER, home=home
    )

    async def session() -> None:
        async with revit_fake_client(run_dir, REVIT_SEED, recording=recording) as client:
            await scripted_revit_session(client, home)

    anyio.run(session)
    return directory / "manifest.json"


def replay_on_revit_fake(
    host: Any, run_dir: Path, seed: Mapping[str, Any] | None = None
) -> list[tuple[Any, dict[str, Any]]]:
    """Send every recorded Revit `tools/call` to a fresh synthetic fake; pairs with the reply."""
    answers: list[tuple[Any, dict[str, Any]]] = []
    used = REVIT_SEED if seed is None else seed

    async def session() -> None:
        async with revit_fake_client(run_dir, used) as client:
            for exchange in host.calls:
                reply = await client.call_tool(exchange.tool, exchange.arguments)
                answers.append((exchange, reply.model_dump(mode="json", by_alias=True, exclude_none=True)))

    anyio.run(session)
    return answers
