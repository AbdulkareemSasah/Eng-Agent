"""Sessions on the synthetic CSI fake, plain or recorded (plan 0002 T17; spec 0002 sections 4.8.1, 4.8.3).

`record_synthetic` runs a short scripted session on the synthetic fake process through `RecordMode`, which gives the
contract tests a recording to work on until the owner commits real ones. `replay_on_fake` sends the requests of a
recording to a fresh fake and returns what the fake answers.
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


@asynccontextmanager
async def fake_client(
    run_dir: Path, seed: Mapping[str, Any] = SEED, *, recording: Recording | None = None
) -> AsyncIterator[Client]:
    """A client on a fresh synthetic fake process (seeded); with `recording` every exchange is recorded."""
    control = run_dir / "control.json"
    control.write_text(json.dumps({"faults": [], "seed": dict(seed)}))
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


async def scripted_session(client: Client, home: str) -> None:
    """Launch, open a model under `home`, read the model state as the adapter does, analysis and results, two errors."""
    await client.list_tools()
    await _body(client, "csi_status", {})
    pid = (await _body(client, "csi_launch", {"product": "ETABS"}))["pid"]
    target = {"target": {"product": "ETABS", "pid": pid}}
    model = f"{home}/Clients/Acme Tower/Tower-A.EDB"
    await _body(client, "csi_open_model", {"path": model, "confirm": True, **target})

    async def call(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        body = await _body(client, tool, arguments)
        assert "code" not in body, body
        return body

    await CsiStateReader(product="ETABS", call=call).read(pid, Path(model))
    await _body(client, "csi_db_table_read", {"table": "Project Information", **target})  # dropped by record mode
    await _body(client, "csi_results_joint_reactions", {"cases": ["DEAD"], "units": "kN_m_C", **target})
    await _body(client, "csi_run_analysis", target)  # no `confirm`: the host refuses
    await _body(client, "csi_design_results", {"kind": "steel", **target})  # no design run: a `csi_error` reply
    await _body(client, "csi_analysis_status", target)


def record_synthetic(directory: Path, run_dir: Path, *, tool_names: frozenset[str] | None = None) -> Path:
    """Record the scripted session on the synthetic fake into `directory`; returns the manifest path."""
    home = "/home/" + USER
    recording = Recording(
        directory, run_dir, adapter="sasaah-csi-mcp", build="synthetic", tool_names=tool_names, user=USER, home=home
    )

    async def session() -> None:
        async with fake_client(run_dir, recording=recording) as client:
            await scripted_session(client, home)

    anyio.run(session)
    return directory / "manifest.json"


def replay_on_fake(host: Any, run_dir: Path, seed: Mapping[str, Any] = SEED) -> list[tuple[Any, dict[str, Any]]]:
    """Send every recorded `tools/call` of `host` to a fresh synthetic fake, in recorded order; pairs with the reply."""
    answers: list[tuple[Any, dict[str, Any]]] = []

    async def session() -> None:
        async with fake_client(run_dir, seed) as client:
            for exchange in host.calls:
                reply = await client.call_tool(exchange.tool, exchange.arguments)
                answers.append((exchange, reply.model_dump(mode="json", by_alias=True, exclude_none=True)))

    anyio.run(session)
    return answers
