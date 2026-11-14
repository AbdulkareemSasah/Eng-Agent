"""CSI reconciliation by reading model state against the synthetic fake (plan 0002 T14; spec 0002 AC23, 4.5.7).

A write is cut off by a server `timeout` that the fake raises either after the write was applied
(`timeout_after_apply`) or before it was (`timeout_before_apply`); the adapter then reads the object back and decides.
The pre-image of a write is the `observed` value of a `read_back` taken before it, as the binder of the host port would
point to (`Binding.pre_image_ref`). Expected outcomes are derived from the spec table of 4.5.7 by hand: a setter whose
state equals the request is `applied`, one whose state equals the pre-image is `not_applied`; a new pattern or
combination is `applied` when present as requested and `not_applied` when absent (and absent before, for a
combination); `csi_delete_load_combo` is `applied` when absent and `not_applied` when present. Analysis and design are
`unknown` whatever the host answers while no proof of end of the abandoned call exists (gap H-G7). The adapter imports
are inside the tests so a missing module fails the test.
"""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import anyio
import pytest
from eng_contract.envelope import FailureEnvelope, HostInfo, Provenance, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from mcp import types

from eng_harness.adapters._args import HostTarget
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._ledger import WriteLedger
from eng_harness.adapters._toolport import Binding
from eng_harness.adapters.csi._errors import CsiErrorMapper
from eng_harness.ports import Reconciliation, ServerCheck
from eng_harness.servers import CallEffect, ServerManager, ServersConfig

from .test_csi_session_ops import ConfigFactory
from .test_csi_state import _seed

HOST = HostInfo(program="ETABS", version="22.0.0", model_id="mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", model_revision=0)
SHA = "d" * 64
CHECK = ServerCheck(
    server="csi", build="0123456789ab+fedcba987654", min_build="", fingerprint=SHA, expected_fingerprint=SHA, ok=True,
    reason=None,
)  # fmt: skip
TOLERANCE = 0.001  # a test input: the value a workflow's frozen basis would hand over
AFTER, BEFORE = "timeout_after_apply", "timeout_before_apply"
_ALL = {"ux": True, "uy": True, "uz": True, "rx": True, "ry": True, "rz": True}


def _seeded() -> dict[str, Any]:
    seed = _seed()
    seed["frame_sections"] = [{"name": "C30"}, {"name": "C40"}]
    seed["area_sections"] = [{"name": "SL", "type": "slab"}, {"name": "SL20", "type": "slab"}]
    seed["load_cases"] = [{"name": "DEAD"}]
    return seed


class Binder:
    """The bound instance of the only model; `pre_image` is the ref the next call's binding carries."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.pre_image: str | None = None
        self.current: int | None = None

    async def binding(self, host_key: str, model: str | None, descriptor: ToolDescriptor) -> Binding:
        target = HostTarget(product="ETABS", pid=self.pid)
        return Binding(target=target, host=HOST, owned=True, pre_image_ref=self.pre_image)

    def revision(self, model_id: str) -> int | None:
        return self.current


class Recorder:
    """The session side: the manager, noting the role and the tool of each call."""

    def __init__(self, manager: ServerManager) -> None:
        self.manager = manager
        self.sent: list[tuple[str, str]] = []

    async def call(self, server: str, role: str, tool: str, arguments: Any, effect: CallEffect) -> types.CallToolResult:
        self.sent.append((role, tool))
        return await self.manager.call(server, role, tool, arguments, effect)


@dataclass
class Rig:
    """The tool port over the fake with its binder, recorder and the fault control file."""

    port: Any
    binder: Binder
    recorder: Recorder
    store: ResultStore
    control: Path
    manager: ServerManager
    pid: int
    count: int = 0

    def value(self, name: str, number: float, host: HostInfo | None = None) -> dict[str, str]:
        producer = Provenance(
            tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0, host=host
        )
        record = self.store.put("harness.run_input/1", {"value": {name: number}}, producer)
        return {"$ref": f"{record.result_id}#/value/{name}"}

    def arm(self, fault: str, tool: str) -> None:
        data = json.loads(self.control.read_text())
        data["faults"].append({"fault": fault, "tool": tool})
        self.control.write_text(json.dumps(data))

    async def engineer(self, tool: str, **arguments: Any) -> None:
        target = {"target": {"product": "ETABS", "pid": self.pid}}
        await self.manager.call("csi", "main", tool, {**target, **arguments}, CallEffect.WRITE)

    async def before(self, tool: str, args: dict[str, Any]) -> None:
        """Take the pre-image: the state of the object before the write, as `read_back` shows it."""
        envelope = await self.port.read_back(tool, {"model": "m", **args})
        assert isinstance(envelope, SuccessEnvelope), envelope
        self.binder.pre_image = f"{envelope.result_id}#/value/observed"

    async def cut_off(self, tool: str, args: dict[str, Any], fault: str, op_id: str = "op-1") -> None:
        """Send the write with `fault` armed: it comes back as a timeout of unknown outcome."""
        self.arm(fault, tool)
        reply = await self.port.call(tool, {"model": "m", **args}, op_id=op_id, model="m")
        assert isinstance(reply, FailureEnvelope), reply
        assert reply.error.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME

    async def reconcile(self, tool: str, args: dict[str, Any], op_id: str = "op-1") -> Reconciliation:
        found: Reconciliation = await self.port.reconcile(tool, {"model": "m", **args}, op_id)
        return found


@asynccontextmanager
async def _rig(
    config: ServersConfig, control: Path, store: ResultStore, run_dir: Path, *, tolerance: float | None = TOLERANCE,
    wired: bool = True, seed: Callable[[dict[str, Any]], None] | None = None,
) -> AsyncIterator[Rig]:  # fmt: skip
    from eng_harness.adapters.csi._reconcile import CsiReconciler
    from eng_harness.adapters.csi._tools import CsiToolPort

    seeded = _seeded()
    if seed is not None:
        seed(seeded)
    control.write_text(json.dumps({"faults": [], "seed": seeded}))
    clock = FixedClock(1_700_000_000_000, 1)
    ids = SeededIdSource(b"reconcile", clock)
    async with ServerManager(config, run_dir) as manager:
        launched = await manager.call("csi", "main", "csi_launch", {"product": "ETABS"}, CallEffect.WRITE)
        block = launched.content[0]
        assert isinstance(block, types.TextContent)
        pid = json.loads(block.text)["pid"]
        manager.bind_instance("csi", pid=pid, product="ETABS")  # the long role attaches to it by process id
        binder, recorder = Binder(pid), Recorder(manager)
        extra: dict[str, Any] = (
            {"reconciler": CsiReconciler(product="ETABS", tolerance_ratio=tolerance)} if wired else {}
        )
        port = CsiToolPort(
            binder=binder, config=config, server="csi", caller=recorder, store=store, ledger=WriteLedger(run_dir),
            clock=clock, ids=ids, check=CHECK, errors=CsiErrorMapper(ids), **extra,
        )  # fmt: skip
        yield Rig(port, binder, recorder, store, control, manager, pid)


@pytest.fixture
def store(tmp_path: Path, ids: SeededIdSource) -> ResultStore:
    """A result store that knows the harness kinds and the CSI kinds of the adapter."""
    from eng_harness._kinds import HARNESS_KINDS
    from eng_harness.adapters.csi._replies import CSI_KINDS

    workspace = Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL)
    return ResultStore(workspace, HARNESS_KINDS.extend(CSI_KINDS), ids, FixedClock(1_767_225_600_000, 1))


def _combo(rig: Rig) -> dict[str, Any]:
    items = [{"case": {"case": "DEAD", "case_type": "load_pattern"}, "scale_ratio": 1.2}]
    return {"name": "C2", "type": "envelope", "items": items}


WRITES: dict[str, Callable[[Rig], dict[str, Any]]] = {
    "csi_assign_frame_section": lambda r: {"frame": "F1", "section": "C40"},
    "csi_assign_area_section": lambda r: {"area": "A1", "section": "SL20"},
    "csi_define_wall_section": lambda r: {
        "name": "W1", "material": "C30", "thickness_mm": r.value("thickness_mm", 250.0)
    },
    "csi_set_frame_load_distributed": lambda r: {
        "frame": "F1", "pattern": "DEAD", "w_kN_m": r.value("w_kN_m", 20.0)
    },
    "csi_set_area_load_uniform": lambda r: {"area": "A1", "pattern": "DEAD", "q_kPa": r.value("q_kPa", 8.0)},
    "csi_add_load_pattern": lambda r: {
        "name": "SNOW1", "type": "snow", "self_weight_ratio": r.value("w_ratio", 0.0)
    },
    "csi_add_load_combo": _combo,
    "csi_delete_load_combo": lambda r: {"name": "C1"},
    "csi_set_point_restraint": lambda r: {"joint": "P0", **_ALL},
}  # fmt: skip
CASES = [(tool, fault, outcome) for tool in WRITES for fault, outcome in ((AFTER, "applied"), (BEFORE, "not_applied"))]


@pytest.mark.parametrize(("tool", "fault", "expected"), CASES, ids=[f"{t}-{f}" for t, f, _ in CASES])
def test_outcomes_per_tool(
    tool: str, fault: str, expected: str, make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """Each write tool is reconciled from the state read back: applied after the write, not applied before it."""

    async def body() -> None:
        async with _rig(make_config(), control, store, run_dir) as rig:
            args = WRITES[tool](rig)
            await rig.before(tool, args)
            await rig.cut_off(tool, args, fault)
            found = await rig.reconcile(tool, args)
            assert found.outcome == expected
            assert found.missing == ()
            assert len(found.evidence) == 1  # the reads, stored as a result and referenced

    anyio.run(body)


LONG = [
    ("csi_run_analysis", {}, AFTER, True, 4),
    ("csi_run_analysis", {}, BEFORE, False, 1),
    ("csi_design_run", {"kind": "steel"}, AFTER, False, None),
    ("csi_design_run", {"kind": "steel"}, BEFORE, False, None),
]


@pytest.mark.parametrize(("tool", "args", "fault", "locked", "code"), LONG, ids=[f"{t}-{f}" for t, _, f, _, _ in LONG])
def test_long_tools_unknown_without_proof_of_end(
    tool: str, args: dict[str, Any], fault: str, locked: bool, code: int | None, make_config: ConfigFactory,
    control: Path, store: ResultStore, run_dir: Path,
) -> None:  # fmt: skip
    """Analysis and design are `unknown` whatever the host answers; the adapter sends no re-run."""

    async def body() -> None:
        async with _rig(make_config(), control, store, run_dir) as rig:
            await rig.cut_off(tool, args, fault)
            found = await rig.reconcile(tool, args)
            assert found.outcome == "unknown"
            assert found.missing == ()
            evidence = _evidence(store, found)
            assert evidence["locked"] is locked
            assert evidence["proof_of_end"] is False
            if code is None:
                assert "analysis_status" not in evidence
            else:
                assert evidence["analysis_status"] == {"cases": [{"case": "DEAD", "status_code": code}]}
            assert [t for role, t in rig.recorder.sent if role == "long"] == [tool]  # no second run was sent

    anyio.run(body)


FRAME = {"frame": "F1", "section": "C40"}
WALL = "csi_define_wall_section"


def _run(config: ServersConfig, control: Path, store: ResultStore, run_dir: Path, body: Any, **rig: Any) -> None:
    async def scenario() -> None:
        async with _rig(config, control, store, run_dir, **rig) as active:
            await body(active)

    anyio.run(scenario)


def _evidence(store: ResultStore, found: Reconciliation) -> dict[str, Any]:
    return cast(dict[str, Any], store.payload(found.evidence[0].ref)["value"])


def test_ledger_find(run_dir: Path) -> None:
    """The last entry of an op id, nothing for an unknown id or a missing file; a torn line is skipped."""
    from eng_harness.adapters._ledger import LedgerEntry

    ledger = WriteLedger(run_dir)
    assert ledger.find("op-1") is None  # no file yet

    def entry(op_id: str, tool: str) -> LedgerEntry:
        return LedgerEntry(
            op_id=op_id, tool=tool, args_sha256=SHA, target=HostTarget(product="ETABS", pid=7), pre_image_ref=None,
            sent_at="2026-01-01T00:00:00.000Z",
        )  # fmt: skip

    ledger.append(entry("op-1", "first"))
    ledger.append(entry("op-2", "other"))
    ledger.append(entry("op-1", "second"))
    with ledger.path.open("a", encoding="utf-8") as handle:
        handle.write('{"op_id": "op-3", "tool"\n')  # a crash in the middle of a line
    found = ledger.find("op-1")
    assert found is not None
    assert found.tool == "second"
    assert ledger.find("op-3") is None
    assert ledger.find("op-9") is None


def test_support_and_missing_reconciler(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """Writes of the allowlist support reconciliation when a reconciler is wired; reads and other tools do not."""

    async def body(rig: Rig) -> None:
        assert rig.port.supports_reconcile("csi_assign_frame_section") is True
        assert rig.port.supports_reconcile("csi_run_analysis") is True
        assert rig.port.supports_reconcile("csi_analysis_status") is False  # a read
        assert rig.port.supports_reconcile("csi_save_model") is False  # not served by this port
        assert await rig.port.read_back("csi_analysis_status", {"model": "m"}) is None
        assert await rig.port.read_back("csi_run_analysis", {"model": "m"}) is None  # nothing to read back

    _run(make_config(), control, store, run_dir, body)

    async def unwired(rig: Rig) -> None:
        assert rig.port.supports_reconcile("csi_assign_frame_section") is False
        assert await rig.port.read_back("csi_assign_frame_section", {"model": "m", **FRAME}) is None
        with pytest.raises(ContractError) as refused:
            await rig.reconcile("csi_assign_frame_section", FRAME)
        assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT
        assert refused.value.detail.message == "csi_assign_frame_section has no reconciler"
        with pytest.raises(ContractError) as outside:
            await rig.reconcile("csi_save_model", {})
        assert outside.value.detail.code is ErrorCode.INVALID_ARGUMENT

    _run(make_config(), control, store, run_dir, unwired, wired=False)


def test_reconcile_frees_the_wedged_host(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """After a timeout the host answers `HOST_WEDGED` until the write is reconciled."""

    async def body(rig: Rig) -> None:
        await rig.cut_off("csi_assign_frame_section", FRAME, AFTER)
        wedged = await rig.port.call("csi_assign_frame_section", {"model": "m", **FRAME}, op_id="op-2", model="m")
        assert isinstance(wedged, FailureEnvelope)
        assert wedged.error.code is ErrorCode.HOST_WEDGED
        await rig.reconcile("csi_assign_frame_section", FRAME)
        freed = await rig.port.call("csi_assign_frame_section", {"model": "m", **FRAME}, op_id="op-2", model="m")
        assert isinstance(freed, SuccessEnvelope), freed

    _run(make_config(), control, store, run_dir, body)


def test_evidence_is_the_state_read(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """The evidence is a stored result of the request, the state read and the pre-image; its tool names the adapter."""

    async def body(rig: Rig) -> None:
        await rig.before("csi_assign_frame_section", FRAME)
        await rig.cut_off("csi_assign_frame_section", FRAME, AFTER)
        found = await rig.reconcile("csi_assign_frame_section", FRAME)
        stored = store.get(found.evidence[0].ref)
        assert stored.kind == "harness.run_output/1"
        assert stored.producer.tool == "sasaah-csi-mcp/csi_assign_frame_section"
        assert stored.producer.host == HOST
        evidence = _evidence(store, found)
        assert evidence["requested"] == {"section": "C40"}
        assert evidence["observed"]["section"] == "C40"
        assert evidence["pre_image_known"] is True
        assert evidence["pre_image"]["section"] == "C30"  # the seeded section, read before the write

    _run(make_config(), control, store, run_dir, body)


def test_read_back_shows_the_state(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """`read_back` stores the `observed` state (`None`: absent); a table that was not read gives no read-back."""

    async def body(rig: Rig) -> None:
        shown = await rig.port.read_back("csi_assign_frame_section", {"model": "m", **FRAME})
        assert isinstance(shown, SuccessEnvelope)
        assert shown.kind == "harness.run_output/1"
        assert shown.provenance.host == HOST
        data: Any = shown.data
        assert data["value"]["observed"]["section"] == "C30"
        wall = {"model": "m", "name": "W9", "material": "C30", "thickness_mm": rig.value("thickness_mm", 250.0)}
        gone = await rig.port.read_back(WALL, wall)
        assert isinstance(gone, SuccessEnvelope)
        assert gone.data == {"value": {"observed": None}}
        area = await rig.port.read_back("csi_assign_area_section", {"model": "m", "area": "A1", "section": "SL"})
        assert area is None  # the section table has no key column: not readable

    def unreadable(seed: dict[str, Any]) -> None:
        seed["tables"]["Area Assignments - Section Properties"] = [{"Other": 1}]

    _run(make_config(), control, store, run_dir, body, seed=unreadable)


def test_setters_need_the_pre_image_to_be_not_applied(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """Without a pre-image on record, or with a malformed one, an unchanged state is `unknown`, never `not_applied`."""

    async def none_on_record(rig: Rig) -> None:
        await rig.cut_off("csi_assign_frame_section", FRAME, BEFORE)  # the state is the old one, nothing to compare
        found = await rig.reconcile("csi_assign_frame_section", FRAME)
        assert found.outcome == "unknown"
        assert _evidence(store, found)["pre_image_known"] is False

    _run(make_config(), control, store, run_dir, none_on_record)

    async def malformed(rig: Rig) -> None:
        listed = rig.value("pre", 1.0)  # a number, not the state of the object
        rig.binder.pre_image = listed["$ref"]
        await rig.cut_off("csi_assign_frame_section", FRAME, BEFORE)
        assert (await rig.reconcile("csi_assign_frame_section", FRAME)).outcome == "unknown"

    _run(make_config(), control, store, run_dir, malformed)

    async def changed_since(rig: Rig) -> None:
        await rig.before("csi_assign_frame_section", FRAME)
        await rig.cut_off("csi_assign_frame_section", FRAME, BEFORE)
        await rig.engineer("csi_assign_frame_section", name="F1", section="C40")  # someone else made it as requested
        assert (await rig.reconcile("csi_assign_frame_section", FRAME)).outcome == "applied"

    _run(make_config(), control, store, run_dir, changed_since)

    async def another_state(rig: Rig) -> None:
        await rig.before("csi_assign_frame_section", FRAME)
        await rig.cut_off("csi_assign_frame_section", FRAME, BEFORE)
        await rig.engineer(
            "csi_assign_frame_section", name="F1", section="C50"
        )  # neither the request nor the old state
        assert (await rig.reconcile("csi_assign_frame_section", FRAME)).outcome == "unknown"

    _run(make_config(), control, store, run_dir, another_state)


def test_pattern_and_combination_rules(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """A pattern present with other values is `unknown`; a combination is `partial` after half of its replacement."""
    other = {"name": "DEAD", "type": "dead", "self_weight_ratio": 0.0}  # DEAD is seeded with self weight 1.0
    linear = [{"case": {"case": "DEAD", "case_type": "load_pattern"}, "scale_ratio": 1.4}]
    replace = {"name": "C1", "type": "linear_add", "items": linear}  # C1 is seeded as exactly this

    async def pattern(rig: Rig) -> None:
        args = {**other, "self_weight_ratio": rig.value("w_ratio", 0.0)}
        await rig.cut_off("csi_add_load_pattern", args, BEFORE)
        assert (await rig.reconcile("csi_add_load_pattern", args)).outcome == "unknown"

    _run(make_config(), control, store, run_dir, pattern)

    async def half(rig: Rig) -> None:
        await rig.before("csi_add_load_combo", replace)
        await rig.cut_off("csi_add_load_combo", replace, BEFORE)
        await rig.engineer("csi_delete_load_combo", name="C1", confirm=True)  # the delete half ran, the add did not
        found = await rig.reconcile("csi_add_load_combo", replace)
        assert (found.outcome, found.missing) == ("partial", ("C1",))

    _run(make_config(), control, store, run_dir, half)

    async def present(rig: Rig) -> None:
        changed = {**replace, "items": [{**linear[0], "scale_ratio": 2.0}]}
        await rig.before("csi_add_load_combo", changed)
        await rig.cut_off("csi_add_load_combo", changed, BEFORE)  # present with the old components
        found = await rig.reconcile("csi_add_load_combo", changed)
        assert (found.outcome, found.missing) == ("unknown", ())

    _run(make_config(), control, store, run_dir, present)

    async def unrecorded(rig: Rig) -> None:
        args = {**replace, "name": "C9"}
        await rig.cut_off("csi_add_load_combo", args, BEFORE)  # absent, and nothing on record about before
        found = await rig.reconcile("csi_add_load_combo", args)
        assert (found.outcome, found.missing) == ("unknown", ())

    _run(make_config(), control, store, run_dir, unrecorded)


def test_no_tolerance_is_unknown_for_a_quantity(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """Without the frozen read-back tolerance a quantity cannot be compared; a name still can."""

    async def body(rig: Rig) -> None:
        wall = {"name": "W1", "material": "C30", "thickness_mm": rig.value("thickness_mm", 250.0)}
        await rig.cut_off(WALL, wall, AFTER)
        assert (await rig.reconcile(WALL, wall)).outcome == "unknown"
        await rig.cut_off("csi_assign_frame_section", FRAME, AFTER, "op-2")
        assert (await rig.reconcile("csi_assign_frame_section", FRAME, "op-2")).outcome == "applied"

    _run(make_config(), control, store, run_dir, body, tolerance=None)


def test_references_are_read_for_their_values(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """The write itself raised the model's revision: references of an older revision still give their values."""

    async def body(rig: Rig) -> None:
        wall = {"name": "W1", "material": "C30", "thickness_mm": rig.value("thickness_mm", 250.0, HOST)}
        await rig.before(WALL, wall)
        await rig.cut_off(WALL, wall, BEFORE)
        rig.binder.current = 5  # the model is at revision 5 now; the references were made at revision 0
        found = await rig.reconcile(WALL, wall)
        assert found.outcome == "not_applied"

    _run(make_config(), control, store, run_dir, body)


def test_a_read_that_times_out_is_unknown(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """A host that does not answer the first read gives `unknown`; any other failure of a read is raised."""

    async def timed_out(rig: Rig) -> None:
        await rig.cut_off("csi_assign_frame_section", FRAME, AFTER)
        rig.arm(BEFORE, "csi_model_info")
        found = await rig.reconcile("csi_assign_frame_section", FRAME)
        assert found.outcome == "unknown"
        assert _evidence(store, found) == {"read_failed": "TIMEOUT_NO_EFFECT"}

    _run(make_config(), control, store, run_dir, timed_out)

    async def unusable(rig: Rig) -> None:
        await rig.cut_off("csi_assign_frame_section", FRAME, AFTER)
        with pytest.raises(ContractError) as failed:
            await rig.reconcile("csi_assign_frame_section", FRAME)
        assert failed.value.detail.code is ErrorCode.HOST_ERROR
        assert failed.value.detail.host_code == "UNEXPECTED_REPLY"
        wedged = await rig.port.call("csi_assign_frame_section", {"model": "m", **FRAME}, op_id="op-2", model="m")
        assert isinstance(wedged, FailureEnvelope)
        assert wedged.error.code is ErrorCode.HOST_WEDGED  # the host is freed only by a reconciliation that returned

    def stories(seed: dict[str, Any]) -> None:
        seed["stories"] = "S1"  # a list reply with no rows

    _run(make_config(), control, store, run_dir, unusable, seed=stories)
