"""`csi_read_model_state` and `csi_read_analysis_messages` against the synthetic fake (plan 0007 T5; spec 0007 AC31).

Both tools are adapter-local (spec 0007 4.10): each composes host reads that the allowlist already holds. The read set
is stored one result per kind, the answer is the host status and its summary holds the other references; a section the
read-back cannot read (`model.sections/1`, S12-G8) is absent. The adapter imports are inside the tests so a missing
module fails the test.
"""

import json
from pathlib import Path
from typing import Any

import anyio
import pytest
from eng_contract.envelope import FailureEnvelope, SuccessEnvelope
from eng_contract.errors import ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from mcp import types

from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.servers import CallEffect, ServerManager, ServersConfig

from .test_csi_analysis import CHECK, Binder, Recorder
from .test_csi_session_ops import ConfigFactory
from .test_csi_state import _seed

MESSAGES = "Analysis Messages"  # the ETABS table key of products/_etabs.py
LIMIT = 2000
STATUS = "harness.csi_model_status/1"
KINDS = {
    "stories": "model.stories/1",
    "frames": "model.frame_placements/1",
    "areas": "model.area_placements/1",
    "loads": "model.load_set/1",
    "restraints": "model.joint_restraints/1",
    "names": "harness.csi_name_lists/1",
}


@pytest.fixture
def store(tmp_path: Path, ids: SeededIdSource) -> ResultStore:
    """A result store that knows the harness kinds and the CSI kinds of the adapter."""
    from eng_harness._kinds import HARNESS_KINDS

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS, ids, FixedClock(1_767_225_600_000, 1))


def run_port(
    config: ServersConfig, run_dir: Path, store: ResultStore, body: Any, *, revisions: Any = None,
    opened: Path | None = None, reconciler: Any = None,
) -> None:  # fmt: skip
    """Launch the fake, optionally open `opened` on it, and run `body(port, recorder, pid, manager)` on the port."""
    from eng_harness.adapters.csi._tools import CsiToolPort

    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"readstate", clock)

    async def scenario() -> None:
        async with ServerManager(config, run_dir) as manager:
            launched = await manager.call("csi", "main", "csi_launch", {"product": "ETABS"}, CallEffect.WRITE)
            block = launched.content[0]
            assert isinstance(block, types.TextContent)
            pid = json.loads(block.text)["pid"]
            manager.bind_instance("csi", pid=pid, product="ETABS")
            target = {"target": {"product": "ETABS", "pid": pid}}
            if opened is not None:
                await manager.call(
                    "csi", "main", "csi_open_model", {"path": str(opened), "confirm": True, **target}, CallEffect.WRITE
                )
            recorder = Recorder(manager)
            port = CsiToolPort(
                binder=Binder(pid), config=config, server="csi", caller=recorder, store=store,
                ledger=WriteLedger(run_dir), clock=clock, ids=ids, check=CHECK, errors=CsiErrorMapper(ids),
                reconciler=reconciler, **({} if revisions is None else {"revisions": revisions}),
            )  # fmt: skip
            await body(port, recorder, pid, manager)

    anyio.run(scenario)


def _call(port: Any, tool: str, **arguments: Any) -> Any:
    return port.call(tool, {"model": "m", **arguments}, op_id=f"op-{tool}", model="m")


def _seeded(control: Path, **extra: Any) -> None:
    control.write_text(json.dumps({"faults": [], "seed": {**_seed(), **extra}}))


def test_read_set(make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path) -> None:
    """AC31: the read set and the name lists are stored, one result each; the summary holds the references."""
    _seeded(
        control,
        frame_sections=[{"name": "C30"}, {"name": "B1"}, {"name": "C30"}],
        materials=[{"name": "M2"}, {"name": "M1"}],
    )

    async def body(port: Any, recorder: Recorder, pid: int, manager: ServerManager) -> None:
        info = await port.describe("csi_read_model_state")
        assert (info.effect, info.action, info.model_param) == ("read", "plain", "model")
        answer = await _call(port, "csi_read_model_state")
        assert isinstance(answer, SuccessEnvelope), answer
        assert answer.kind == "harness.csi_model_status/1"
        assert answer.provenance.tool == "sasaah-csi-mcp/csi_read_model_state"
        assert set(answer.summary) == set(KINDS)  # no sections (S12-G8) and no grids: spec 0007 4.10 lists neither
        for key, kind in KINDS.items():
            ref = answer.summary[key]
            assert isinstance(ref, str)
            assert store.get(ref).kind == kind, key
        names = store.payload(str(answer.summary["names"]))
        assert names == {
            "frame_sections": ["B1", "C30"],
            "area_sections": ["SL"],
            "materials": ["M1", "M2"],
            "patterns": ["DEAD"],
            "combinations": ["C1"],
        }
        assert isinstance(answer.data, dict)
        assert answer.data["units"] == "kN_m_C"
        assert store.get(answer.result_id).complete
        stories: Any = store.payload(str(answer.summary["stories"]))
        assert [s["name"] for s in stories["stories"]] == ["S1", "S2"]
        tools = {tool for _role, tool, _args in recorder.sent}
        assert "csi_save_model" not in tools
        assert {"csi_model_info", "csi_list_frame_sections", "csi_list_materials", "csi_db_table_read"} <= tools
        lists = {tool: args for _role, tool, args in recorder.sent if tool.startswith("csi_list_")}
        assert lists["csi_list_frame_sections"] == {"limit": LIMIT, "target": {"product": "ETABS", "pid": pid}}

    run_port(make_config(), run_dir, store, body)


@pytest.mark.parametrize("field", ["frame_sections", "area_sections", "materials", "load_patterns", "load_combos"])
def test_truncated_name_list_is_limit_exceeded(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path, field: str
) -> None:
    """AC31: a list the host cuts at 2000 gives `LIMIT_EXCEEDED`; nothing is stored of a partial read set."""
    _seeded(control, **{field: [{"name": f"N{n:04d}", "type": "slab"} for n in range(LIMIT + 1)]})

    async def body(port: Any, recorder: Recorder, pid: int, manager: ServerManager) -> None:
        answer = await _call(port, "csi_read_model_state")
        assert isinstance(answer, FailureEnvelope), answer
        assert answer.error.code is ErrorCode.LIMIT_EXCEEDED
        assert answer.error.received == LIMIT
        assert answer.error.message == f"csi_list_{field} was truncated at {LIMIT} rows"

    run_port(make_config(), run_dir, store, body)


def test_name_row_without_name(make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path) -> None:
    """A name list row that has no `name` is an unusable reply, never a bare `KeyError`."""
    _seeded(control, materials=[{"title": "M1"}])

    async def body(port: Any, recorder: Recorder, pid: int, manager: ServerManager) -> None:
        answer = await _call(port, "csi_read_model_state")
        assert isinstance(answer, FailureEnvelope), answer
        assert answer.error.code is ErrorCode.HOST_ERROR
        assert answer.error.host_code == "UNEXPECTED_REPLY"
        assert answer.error.host_method == "csi_list_materials"
        assert answer.error.message == "a row of csi_list_materials has no name"
        assert answer.error.field == "items"
        assert answer.error.retryable is False

    run_port(make_config(), run_dir, store, body)


def test_state_read_errors_pass_through(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """The reader's own error (a truncated story list) is the tool's error."""
    _seeded(control, stories=[{"name": f"S{n}", "elevation": 3.0 * n, "height": 3.0} for n in range(LIMIT + 1)])

    async def body(port: Any, recorder: Recorder, pid: int, manager: ServerManager) -> None:
        answer = await _call(port, "csi_read_model_state")
        assert isinstance(answer, FailureEnvelope), answer
        assert answer.error.code is ErrorCode.LIMIT_EXCEEDED

    run_port(make_config(), run_dir, store, body)


def test_arguments_are_checked(make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path) -> None:
    """An argument the tool does not have is refused before any host call."""
    _seeded(control)

    async def body(port: Any, recorder: Recorder, pid: int, manager: ServerManager) -> None:
        for tool in ("csi_read_model_state", "csi_read_analysis_messages"):
            answer = await _call(port, tool, limit=5)
            assert isinstance(answer, FailureEnvelope), answer
            assert answer.error.code is ErrorCode.INVALID_ARGUMENT
        assert recorder.sent == []

    run_port(make_config(), run_dir, store, body)


def test_analysis_messages(make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path) -> None:
    """AC31: the `Analysis Messages` table is read through `csi_db_table_read` and stored as the host's rows."""
    rows = [{"Type": "Warning", "Text": "first"}, {"Type": "Error", "Text": "second"}]
    _seeded(control, tables={MESSAGES: rows})

    async def body(port: Any, recorder: Recorder, pid: int, manager: ServerManager) -> None:
        info = await port.describe("csi_read_analysis_messages")
        assert (info.effect, info.action, info.model_param) == ("read", "plain", "model")
        answer = await _call(port, "csi_read_analysis_messages")
        assert isinstance(answer, SuccessEnvelope), answer
        assert answer.kind == "harness.csi_analysis_messages/1"
        assert answer.provenance.tool == "sasaah-csi-mcp/csi_read_analysis_messages"
        assert answer.summary == {}
        assert store.payload(answer.result_id) == {"rows": rows}
        assert recorder.sent == [
            (
                "main",
                "csi_db_table_read",
                {"table": MESSAGES, "row_limit": LIMIT, "target": {"product": "ETABS", "pid": pid}},
            )
        ]

    run_port(make_config(), run_dir, store, body)


def test_analysis_messages_truncated(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """A message table cut at 2000 rows is `LIMIT_EXCEEDED`, so a message is never silently missing."""
    _seeded(control, tables={MESSAGES: [{"Text": str(n)} for n in range(LIMIT + 1)]})

    async def body(port: Any, recorder: Recorder, pid: int, manager: ServerManager) -> None:
        answer = await _call(port, "csi_read_analysis_messages")
        assert isinstance(answer, FailureEnvelope), answer
        assert answer.error.code is ErrorCode.LIMIT_EXCEEDED
        assert answer.error.received == LIMIT
        assert answer.error.message == f"{MESSAGES} was truncated at {LIMIT} rows"

    run_port(make_config(), run_dir, store, body)


def test_parts_of_both_tools(make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path) -> None:
    """The parts, in order, with their keys and kinds; the status names the open file; the reads are host reads."""
    from eng_harness.adapters._args import HostTarget
    from eng_harness.adapters.csi._read_state_tool import READ_TOOLS

    rows = [{"Type": "Warning", "Text": "first"}]
    _seeded(control, tables={MESSAGES: rows})
    opened = run_dir / "Tower.EDB"
    opened.parent.mkdir(parents=True, exist_ok=True)
    opened.write_bytes(b"model")

    async def body(port: Any, recorder: Recorder, pid: int, manager: ServerManager) -> None:
        seen: list[tuple[str, CallEffect]] = []

        async def read(tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
            seen.append((tool, effect))
            reply = await manager.call("csi", "main", tool, arguments, effect)
            block = reply.content[0]
            assert isinstance(block, types.TextContent)
            decoded: dict[str, Any] = json.loads(block.text)
            return decoded

        target = HostTarget(product="ETABS", pid=pid)
        parts = await READ_TOOLS["csi_read_model_state"](read, target)
        assert [(key, kind) for key, kind, _ in parts] == [*KINDS.items(), ("status", STATUS)]
        status = parts[-1][2]
        assert status["file_name"] == "Tower.EDB"
        assert status["units"] == "kN_m_C"
        assert ("csi_model_info", CallEffect.READ) in seen
        assert {effect for _tool, effect in seen} == {CallEffect.READ}
        messages = await READ_TOOLS["csi_read_analysis_messages"](read, target)
        assert messages == [("messages", "harness.csi_analysis_messages/1", {"rows": rows})]

    run_port(make_config(), run_dir, store, body, opened=opened)
