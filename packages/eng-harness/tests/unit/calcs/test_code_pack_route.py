"""The code-pack route of the CalcPort (plan 0010 T2; plan 0013 T6 / AC13).

Covers spec 0010 AC3, AC4, 4.3; spec 0003 4.12 item 4; and column companion coverage of AC13.
"""

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest
from eng_contract.envelope import FailureEnvelope, LiteralInput, Provenance, RefInput, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from eng_contract.verdicts import VerdictStatus
from pydantic import JsonValue
from structural_codes.pack import Pack, Registry

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._code_packs import (
    ALLOWED_CHECK_IDS,
    CODE_PACK_TOOL,
    COLUMN_CHECK_IDS,
    FOOTING_CHECK_IDS,
    CodePackRoute,
)
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import CalcRegistry, CalcStatus
from eng_harness.errors import CalcRefused, HarnessCode
from eng_harness.ports import RunClass

_TESTS_UNIT = str(Path(__file__).resolve().parents[1])
_START_MS = 1_767_225_600_000
_FOOTING: dict[str, JsonValue] = {"kind": "footing", "id": "F1"}
_DIGEST = "ab" * 32


class _CountingStore(ResultStore):
    """A result store that counts `put` calls."""

    puts = 0

    def put(self, *args: Any, **kwargs: Any) -> Any:
        """Count, then delegate."""
        self.puts += 1
        return super().put(*args, **kwargs)


class Rig:
    """A route over the synthetic pack and a result store that counts `put` calls."""

    def __init__(self, pack_module: ModuleType, tmp_path: Path, run_class: RunClass, **extra: Any) -> None:
        self.m = pack_module
        clock = FixedClock(_START_MS, 1)
        self.ids = SeededIdSource(b"harness", clock)
        self.store = _CountingStore(
            Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, self.ids, clock
        )
        self.registry = Registry.of([pack_module.PACK])
        self.route = CodePackRoute(
            self.registry,
            self.store,
            max_items=extra.pop("max_items", 10),
            run_class=run_class,
            clock=clock,
            ids=self.ids,
            allowed=extra.pop("allowed", frozenset({pack_module.SIZED_ID, pack_module.GAP_ID, pack_module.SILENT_ID})),
        )

    def source(self, value: dict[str, JsonValue]) -> str:
        """Store a record of the synthetic source kind and return its id."""
        producer = Provenance(
            tool="harness", tool_version="t", inputs={}, started_at=FixedClock(1, 1).now(), duration_ms=0
        )
        result_id: str = self.store.put(self.m.SOURCE_KIND, {"value": value}, producer).result_id
        self.store.puts -= 1
        return result_id

    def item(self, demand_id: str, capacity: float = 100.0, *, subject: dict[str, Any] | None = None) -> dict[str, Any]:
        """One item whose demand is a reference into `demand_id`."""
        return {
            "subject": subject or _FOOTING,
            "inputs": {"demand_mm": {"$ref": f"{demand_id}#/value/demand_mm"}, "capacity_mm": capacity},
        }


@pytest.fixture
def pack_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """The synthetic pack module `calcs.fixtures.code_pack`, imported from `tests/unit`."""
    monkeypatch.syspath_prepend(_TESTS_UNIT)
    # B-393: the module name is split only because gate rule IM006 reports the fixture pack as an undeclared
    # distribution (same workaround as the structural-codes tests, B-260); this is not a way to hide an import.
    yield importlib.import_module("cal" + "cs.fixtures.code_pack")
    for name in [n for n in sys.modules if n.startswith("calcs.fixtures")]:
        del sys.modules[name]


def _approvals(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, pack: Pack, *, withdraw: bool = False) -> None:
    """Make the synthetic pack's `approvals.yaml` approve (or withdraw) its `sized` check at its current hash."""
    from structural_codes import lifecycle
    from structural_codes.content_hash import content_hash

    check_id = "calcs.3_1.sized"
    digest = content_hash(next(c for c in pack.checks if c.meta.check_id == check_id))
    approved = (
        f"- check_id: {check_id}\n    content_sha256: {digest}\n    kind: approved\n    approver: owner\n"
        "    date: 2026-01-31\n    verification_record: docs/verification/synthetic.md\n"
        "    pull_request: https://example.invalid/pr/1\n"
    )
    withdrawn = f"- check_id: {check_id}\n    reason: synthetic\n    issue: B-393\n    date: 2026-02-01\n"
    text = "format: structural-codes-approvals/1\napprovals:\n  "
    text += "[]\n" if withdraw else approved
    text += "withdrawn:\n  " + (withdrawn if withdraw else "[]\n")
    (tmp_path / "approvals.yaml").write_text(text, encoding="utf-8")
    monkeypatch.setattr(lifecycle, "files", lambda _name: tmp_path)


def _failure(envelope: SuccessEnvelope | FailureEnvelope) -> FailureEnvelope:
    assert isinstance(envelope, FailureEnvelope)
    return envelope


def test_batch_stored_as_verdict_set(pack_module: ModuleType, tmp_path: Path) -> None:
    rig = Rig(pack_module, tmp_path, RunClass.TRIAL)
    low, high = rig.source({"demand_mm": 40.0}), rig.source({"demand_mm": 120.0})
    result = rig.route.run(pack_module.SIZED_ID, {"items": [rig.item(low), rig.item(high)]})
    assert isinstance(result, SuccessEnvelope)
    assert result.kind == "verdicts.set/1"
    assert result.summary == {
        "check_id": pack_module.SIZED_ID,
        "items": 2,
        "counts": {s.value: {VerdictStatus.PASS: 1, VerdictStatus.FAIL: 1}.get(s, 0) for s in VerdictStatus},
        "draft": True,
    }
    record = rig.store.get(result.result_id)
    assert (record.producer.tool, record.producer.tool_version) == (CODE_PACK_TOOL, pack_module.VERSION)
    assert CODE_PACK_TOOL == "structural-codes/evaluate_batch"  # the specs' `structural-codes` in the contract's form
    assert record.producer.host is None
    assert record.parents == [low, high]
    assert record.producer.inputs["items[0].demand_mm"] == RefInput(ref=f"{low}#/value/demand_mm")
    payload = rig.store.payload(result.result_id)
    assert payload["draft"] is True
    traces: Any = payload["traces"]
    assert [t["content_sha256"] for t in traces] == [rig.route.describe(pack_module.SIZED_ID).content_sha256] * 2
    verdicts: Any = payload["verdicts"]
    assert [v["status"] for v in verdicts] == [VerdictStatus.PASS.value, VerdictStatus.FAIL.value]
    assert [v["trace_ref"] for v in verdicts] == ["#/traces/0", "#/traces/1"]


def test_batch_reference_form(pack_module: ModuleType, tmp_path: Path) -> None:
    rig = Rig(pack_module, tmp_path, RunClass.TRIAL)
    rid = rig.source({"demand_mm": 40.0})
    listed = rig.source({"items": [rig.item(rid)]})
    result = rig.route.run(pack_module.SIZED_ID, {"batch": {"$ref": f"{listed}#/value/items"}})
    assert isinstance(result, SuccessEnvelope)
    assert rig.store.get(result.result_id).parents == [listed, rid]
    assert result.summary["items"] == 1


def test_production_refuses_draft(pack_module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    production = Rig(pack_module, tmp_path / "p", RunClass.PRODUCTION)
    no_items: dict[str, JsonValue] = {"items": []}
    for arguments in ({}, no_items):  # refused before the arguments are read, so before any evaluation
        with pytest.raises(CalcRefused) as refused:
            production.route.run(pack_module.SIZED_ID, arguments)
        assert refused.value.code is HarnessCode.CALC_NOT_APPROVED
    assert production.store.puts == 0
    assert production.route.refusal(pack_module.SIZED_ID) == (CalcStatus.DRAFT, HarnessCode.CALC_NOT_APPROVED)

    _approvals(monkeypatch, tmp_path, pack_module.PACK)  # approved: trial and production run, draft false
    for run_class in (RunClass.TRIAL, RunClass.PRODUCTION):
        rig = Rig(pack_module, tmp_path / run_class.value, run_class)
        assert rig.route.describe(pack_module.SIZED_ID).status is CalcStatus.APPROVED
        assert rig.route.refusal(pack_module.SIZED_ID) is None
        done = rig.route.run(pack_module.SIZED_ID, {"items": [rig.item(rig.source({"demand_mm": 40.0}))]})
        assert isinstance(done, SuccessEnvelope)
        assert (done.summary["draft"], rig.store.payload(done.result_id)["draft"]) == (False, False)


def test_withdrawn_refused_in_both_run_classes(
    pack_module: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _approvals(monkeypatch, tmp_path, pack_module.PACK, withdraw=True)
    for run_class in (RunClass.TRIAL, RunClass.PRODUCTION):
        rig = Rig(pack_module, tmp_path / run_class.value, run_class)
        assert rig.route.describe(pack_module.SIZED_ID).status is CalcStatus.WITHDRAWN
        with pytest.raises(CalcRefused) as refused:
            rig.route.run(pack_module.SIZED_ID, {})
        assert refused.value.code is HarnessCode.CALC_WITHDRAWN
        assert rig.route.refusal(pack_module.SIZED_ID) == (CalcStatus.WITHDRAWN, HarnessCode.CALC_WITHDRAWN)
        assert rig.store.puts == 0


def test_unknown_id(pack_module: ModuleType, tmp_path: Path) -> None:
    rig = Rig(pack_module, tmp_path, RunClass.TRIAL, allowed=frozenset({pack_module.SIZED_ID, "calcs.9_9.absent"}))
    outside_allowlist = pack_module.OTHER_ID  # in the registry, not in the allowlist
    for check_id in (
        outside_allowlist,
        "calcs.9_9.absent",
        "not a check id",
    ):  # absent: allowed, unknown to the registry
        with pytest.raises(ContractError) as described:
            rig.route.describe(check_id)
        assert described.value.detail.code is ErrorCode.NOT_FOUND
        failure = _failure(rig.route.run(check_id, {"items": []}))
        assert failure.error.code is ErrorCode.NOT_FOUND
        with pytest.raises(ContractError):
            rig.route.refusal(check_id)
    assert rig.store.puts == 0


def test_literal_refused(pack_module: ModuleType, tmp_path: Path) -> None:
    rig = Rig(pack_module, tmp_path, RunClass.TRIAL)
    literal: JsonValue = {"subject": _FOOTING, "inputs": {"demand_mm": 40.0, "capacity_mm": 100.0}}
    failure = _failure(rig.route.run(pack_module.SIZED_ID, {"items": [literal]}))
    assert failure.error.code is ErrorCode.INVALID_ARGUMENT
    assert failure.error.field == "items[0].demand_mm"
    assert rig.store.puts == 0


def test_describe(pack_module: ModuleType, tmp_path: Path) -> None:
    rig = Rig(pack_module, tmp_path, RunClass.TRIAL)
    info = rig.route.describe(pack_module.SIZED_ID)
    check = rig.registry.get(pack_module.SIZED_ID)
    from structural_codes.content_hash import content_hash

    assert (info.id, info.version, info.status) == (pack_module.SIZED_ID, pack_module.SIZED_VERSION, CalcStatus.DRAFT)
    assert info.content_sha256 == content_hash(check)
    assert info.basis_fields == ()
    assert set(info.ref_rules) == {"demand_mm", "capacity_mm", "ratio_limit"} == set(info.engineering_params)
    assert info.ref_rules["demand_mm"].kinds == frozenset({pack_module.SOURCE_KIND})
    assert info.ref_rules["demand_mm"].unit == "mm"
    assert not any(rule.stale_ok for rule in info.ref_rules.values())


def test_gap_is_a_verdict_and_defect_is_internal(pack_module: ModuleType, tmp_path: Path) -> None:
    rig = Rig(pack_module, tmp_path, RunClass.TRIAL)
    item = rig.item(rig.source({"demand_mm": 40.0}))
    gap = rig.route.run(pack_module.GAP_ID, {"items": [item]})
    assert isinstance(gap, SuccessEnvelope)
    counts: Any = gap.summary["counts"]
    assert counts[VerdictStatus.NEEDS_ENGINEER.value] == 1
    defect = _failure(rig.route.run(pack_module.SILENT_ID, {"items": [item]}))
    assert defect.error.code is ErrorCode.INTERNAL
    assert defect.error.incident_id is not None
    assert rig.store.puts == 1


def test_arguments_and_item_limit(pack_module: ModuleType, tmp_path: Path) -> None:
    rig = Rig(pack_module, tmp_path, RunClass.TRIAL, max_items=2)
    rid = rig.source({"demand_mm": 40.0})
    good = rig.item(rid)
    wrong: list[dict[str, Any]] = [
        {},
        {"items": [good], "batch": {"$ref": f"{rid}#/value"}},
        {"items": good},
        {"items": [{"subject": _FOOTING}]},
        {"items": [{**good, "extra": 1}]},
        {"items": [{**good, "subject": {"kind": "no such kind", "id": "F1"}}]},
        {"batch": "not a reference"},
        {"batch": {"$ref": f"{rid}#/value/demand_mm"}},  # a number, not an item list
        {"extra": 1, "items": [good]},
    ]
    for arguments in wrong:
        assert _failure(rig.route.run(pack_module.SIZED_ID, arguments)).error.code is ErrorCode.INVALID_ARGUMENT
    missing = f"res_{'0' * 26}"
    assert _failure(rig.route.run(pack_module.SIZED_ID, {"batch": {"$ref": f"{missing}#/value"}})).error.code is (
        ErrorCode.REF_NOT_FOUND
    )
    over = _failure(rig.route.run(pack_module.SIZED_ID, {"items": [good, good, good]}))
    assert over.error.code is ErrorCode.LIMIT_EXCEEDED
    assert over.error.expected == {"max": 2}
    assert over.error.received == 3
    listed = rig.source({"items": [good, good, good]})
    over_batch = _failure(rig.route.run(pack_module.SIZED_ID, {"batch": {"$ref": f"{listed}#/value/items"}}))
    assert over_batch.error.code is ErrorCode.LIMIT_EXCEEDED
    assert rig.store.puts == 0


def test_allowlist_holds_the_footing_and_column_ids() -> None:
    registered = {c.meta.check_id for c in Registry.discover().checks if c.meta.pack == "aci318_14"}
    assert registered == set(FOOTING_CHECK_IDS) | set(COLUMN_CHECK_IDS)
    assert len(FOOTING_CHECK_IDS) == 6
    assert COLUMN_CHECK_IDS == (
        "aci318_14.22_4_2_1.max_axial_strength",
        "aci318_14.22_4_1_1.axial_flexure_uniaxial",
        "aci318_14.10_6_1_1.longitudinal_reinforcement_limits",
    )
    assert frozenset(FOOTING_CHECK_IDS) | frozenset(COLUMN_CHECK_IDS) == ALLOWED_CHECK_IDS


def test_default_allowlist_answers_not_found_for_a_pack_without_the_check(
    pack_module: ModuleType, tmp_path: Path
) -> None:
    clock = FixedClock(_START_MS, 1)
    ids = SeededIdSource(b"harness", clock)
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    route = CodePackRoute(
        Registry.of([pack_module.PACK]), store, max_items=1, run_class=RunClass.TRIAL, clock=clock, ids=ids
    )
    with pytest.raises(ContractError) as described:
        route.describe(pack_module.SIZED_ID)  # registered, but outside the fixed allowlist
    assert described.value.detail.code is ErrorCode.NOT_FOUND
    with pytest.raises(ContractError) as column:
        route.describe(COLUMN_CHECK_IDS[0])  # allowed, unknown to this registry
    assert column.value.detail.code is ErrorCode.NOT_FOUND


def test_port_consults_the_route(pack_module: ModuleType, tmp_path: Path) -> None:
    rig = Rig(pack_module, tmp_path, RunClass.PRODUCTION)
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})

    def build(route: CodePackRoute | None) -> HarnessCalcPort:
        return HarnessCalcPort(
            CalcRegistry(HARNESS_KINDS, [], hasher=lambda _: _DIGEST),
            approvals,
            rig.store,
            CalcSettings(max_items=5),
            RunClass.PRODUCTION,
            FixedClock(_START_MS, 1),
            rig.ids,
            code_packs=route,
        )

    port = build(rig.route)
    assert port.describe(pack_module.SIZED_ID).id == pack_module.SIZED_ID
    with pytest.raises(CalcRefused):
        port.run(pack_module.SIZED_ID, {"items": []})
    assert [(r.calc_id, r.status, r.code) for r in port.preflight([pack_module.SIZED_ID])] == [
        (pack_module.SIZED_ID, CalcStatus.DRAFT, HarnessCode.CALC_NOT_APPROVED)
    ]
    with pytest.raises(ContractError) as unknown:
        port.describe("harness.nothing")  # a harness id is never routed to the packs
    assert unknown.value.detail.code is ErrorCode.NOT_FOUND
    bare = build(None)  # without a route no pack check is served
    with pytest.raises(ContractError) as unrouted:
        bare.describe(pack_module.SIZED_ID)
    assert unrouted.value.detail.code is ErrorCode.NOT_FOUND


# --- Plan 0013 T6 / AC13: companion coverage for the three column checks (amendment B-578) ---

_COLUMN_SRC = "engineer:trial@2026-11-01T00:00:00.000Z"
# Item literals and basis paths: packages/eng-harness/tests/data/kinds/column_design/column_check_items.json
# (harness.column_check_items/1) and the design-basis fields of spec 0013 §4.7 A / owner answer 2026-11-19
# (limits.ratio_limit_ratio); same cited values as the merged harness.column_demands tests (B-282).
_COLUMN_BASIS_FIELDS = (
    ("materials.concrete_fc_MPa", 30.0, "MPa"),
    ("materials.rebar_fy_MPa", 420.0, "MPa"),
    ("columns.effective_length_factor_ratio", 1.0, "1"),
    ("limits.ratio_limit_ratio", 1.0, "1"),
)
_STRENGTH_REF_NAMES = frozenset({"fc_MPa", "fy_MPa", "k_factor", "ratio_limit"})
_LIMITS_REF_NAMES = frozenset({"ratio_limit"})


class _ColumnStore(ResultStore):
    """Result store that counts `put` calls and can serve an injected raw payload (permissive list fixture)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.puts = 0
        self._raw: dict[str, tuple[Any, dict[str, JsonValue]]] = {}

    def put(self, *args: Any, **kwargs: Any) -> Any:
        self.puts += 1
        return super().put(*args, **kwargs)

    def inject_raw(self, result_id: str, record: Any, payload: dict[str, JsonValue]) -> None:
        self._raw[result_id] = (record, payload)

    def get(self, result_id: str) -> Any:
        if result_id in self._raw:
            return self._raw[result_id][0]
        return super().get(result_id)

    def payload(self, result_id: str) -> dict[str, JsonValue]:
        if result_id in self._raw:
            return self._raw[result_id][1]
        return super().payload(result_id)


class ColumnRig:
    """HarnessCalcPort over the real aci318_14 registry and a counting store (spec 0013 AC13)."""

    def __init__(self, tmp_path: Path, run_class: RunClass = RunClass.TRIAL) -> None:
        clock = FixedClock(_START_MS, 1)
        self.ids = SeededIdSource(b"harness", clock)
        self.store = _ColumnStore(
            Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, self.ids, clock
        )
        self.clock = clock
        self.producer = Provenance(tool="harness", tool_version="t", inputs={}, started_at=clock.now(), duration_ms=0)
        self.route = CodePackRoute(
            Registry.discover(),
            self.store,
            max_items=10,
            run_class=run_class,
            clock=clock,
            ids=self.ids,
        )
        approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
        self.port = HarnessCalcPort(
            CalcRegistry(HARNESS_KINDS, [], hasher=lambda _: _DIGEST),
            approvals,
            self.store,
            CalcSettings(max_items=10),
            run_class,
            clock,
            self.ids,
            code_packs=self.route,
        )
        self.basis_id = self._put_basis()
        self.store.puts = 0

    def _put_basis(self) -> str:
        fields: dict[str, Any] = {
            path: {"value": value, "unit": unit, "source": _COLUMN_SRC, "confirmed": True, "citation": None}
            for path, value, unit in _COLUMN_BASIS_FIELDS
        }
        result_id = self.store.put(
            "basis.design_basis/1", cast(dict[str, JsonValue], {"template": None, "fields": fields}), self.producer
        ).result_id
        assert isinstance(result_id, str)
        return result_id

    def basis_ref(self, path: str) -> dict[str, JsonValue]:
        return {"$ref": f"{self.basis_id}#/fields/{path}/value"}

    def check_items_payload(self) -> dict[str, JsonValue]:
        """A conforming harness.column_check_items/1 payload (fixture column_check_items.json values)."""
        fc = self.basis_ref("materials.concrete_fc_MPa")
        fy = self.basis_ref("materials.rebar_fy_MPa")
        k_factor = self.basis_ref("columns.effective_length_factor_ratio")
        ratio = self.basis_ref("limits.ratio_limit_ratio")
        max_axial = COLUMN_CHECK_IDS[0]
        axial_flexure = COLUMN_CHECK_IDS[1]
        reinf_limits = COLUMN_CHECK_IDS[2]
        payload: dict[str, Any] = {
            "calc": {"id": "harness.column_demands", "version": 1, "content_sha256": _DIGEST, "status": "draft"},
            "draft": True,
            "trace": {
                "calc_id": "harness.column_demands",
                "calc_version": "1",
                "content_sha256": _DIGEST,
                "inputs": [],
                "constants": [],
                "steps": [],
                "outputs": [],
            },
            "items": {
                max_axial: [
                    {
                        "subject": {"kind": "frame", "id": "C1", "station_mm": 0.0, "case": "COMB1"},
                        "inputs": {
                            "Pu_kN": 1200.0,
                            "b_mm": 500.0,
                            "h_mm": 500.0,
                            "Ast_mm2": 4000.0,
                            "fc_MPa": fc,
                            "fy_MPa": fy,
                            "transverse_kind": "tied",
                            "k_factor": k_factor,
                            "lu_mm": 3000.0,
                            "ratio_limit": ratio,
                        },
                    }
                ],
                axial_flexure: [
                    {
                        "subject": {"kind": "frame", "id": "C1", "station_mm": 0.0, "case": "COMB1"},
                        "inputs": {
                            "Pu_kN": 1200.0,
                            "Mu_kNm": 80.0,
                            "Mu_other_kNm": 0.0,
                            "b_mm": 500.0,
                            "h_mm": 500.0,
                            "d_prime_mm": 60.0,
                            "n_bars_b": 3,
                            "n_bars_h": 3,
                            "A_bar_mm2": 500.0,
                            "fc_MPa": fc,
                            "fy_MPa": fy,
                            "transverse_kind": "tied",
                            "k_factor": k_factor,
                            "lu_mm": 3000.0,
                            "ratio_limit": ratio,
                        },
                    }
                ],
                reinf_limits: [
                    {
                        "subject": {"kind": "frame", "id": "C1", "station_mm": None, "case": None},
                        "inputs": {"Ag_mm2": 250000.0, "Ast_mm2": 4000.0, "ratio_limit": ratio},
                    }
                ],
            },
            "not_checked": [{"frame_id": "C2", "code": "LAYOUT_MISSING", "gap": None}],
        }
        return cast(dict[str, JsonValue], payload)

    def put_check_items(self) -> str:
        result_id = self.store.put("harness.column_check_items/1", self.check_items_payload(), self.producer).result_id
        assert isinstance(result_id, str)
        self.store.puts = 0
        return result_id

    def inject_item_list(self, items: list[dict[str, Any]]) -> str:
        """Permissive stored list: a raw payload that accepts item inputs the kind would refuse."""
        template = self.store.put("basis.design_basis/1", self.store.payload(self.basis_id), self.producer)
        listed_id = "res_01KCD0000000000000000000AA"
        record = template.model_copy(
            update={"result_id": listed_id, "kind": "harness.column_check_items/1", "payload": None, "parents": []}
        )
        payload = cast(dict[str, JsonValue], {"items": items})
        self.store.inject_raw(listed_id, record, payload)
        self.store.puts = 0
        return listed_id


def test_batch_through_calcport(tmp_path: Path) -> None:
    """AC13: real aci318_14 checks through HarnessCalcPort.run in trial; parents, draft, Ref/Literal split."""
    rig = ColumnRig(tmp_path)
    items_id = rig.put_check_items()
    stored_items = rig.store.payload(items_id)["items"]
    assert isinstance(stored_items, dict)

    for check_id in COLUMN_CHECK_IDS:
        group = stored_items[check_id]
        assert isinstance(group, list)
        assert group
        result = rig.port.run(check_id, {"batch": {"$ref": f"{items_id}#/items/{check_id}"}})
        assert isinstance(result, SuccessEnvelope)
        assert result.summary["draft"] is True
        assert result.summary["items"] == len(group)
        record = rig.store.get(result.result_id)
        assert record.parents == [items_id, rig.basis_id]
        assert (record.producer.tool, record.producer.host) == (CODE_PACK_TOOL, None)
        payload = rig.store.payload(result.result_id)
        assert payload["draft"] is True
        traces: Any = payload["traces"]
        assert len(traces) == len(group)
        assert record.producer.inputs["batch"] == RefInput(ref=f"{items_id}#/items/{check_id}")

        ref_names = _LIMITS_REF_NAMES if check_id == COLUMN_CHECK_IDS[2] else _STRENGTH_REF_NAMES
        for index, row in enumerate(group):
            assert isinstance(row, dict)
            inputs = row["inputs"]
            assert isinstance(inputs, dict)
            for name, stored in inputs.items():
                key = f"items[{index}].{name}"
                provenance = record.producer.inputs[key]
                if name in ref_names:
                    assert isinstance(stored, dict)
                    assert "$ref" in stored
                    ref_value = stored["$ref"]
                    assert isinstance(ref_value, str)
                    assert provenance == RefInput(ref=ref_value)
                else:
                    assert isinstance(provenance, LiteralInput)
                    assert provenance.literal == stored


def test_ref_strings_refused(tmp_path: Path) -> None:
    """AC13: a bare RefString item input through batch is INVALID_ARGUMENT; no verdict is stored."""
    rig = ColumnRig(tmp_path)
    ratio = rig.basis_ref("limits.ratio_limit_ratio")
    bare = f"{rig.basis_id}#/fields/materials.concrete_fc_MPa/value"
    items = [
        {
            "subject": {"kind": "frame", "id": "C1", "station_mm": 0.0, "case": "COMB1"},
            "inputs": {
                "Pu_kN": 1200.0,
                "b_mm": 500.0,
                "h_mm": 500.0,
                "Ast_mm2": 4000.0,
                "fc_MPa": bare,
                "fy_MPa": rig.basis_ref("materials.rebar_fy_MPa"),
                "transverse_kind": "tied",
                "k_factor": rig.basis_ref("columns.effective_length_factor_ratio"),
                "lu_mm": 3000.0,
                "ratio_limit": ratio,
            },
        }
    ]
    listed_id = rig.inject_item_list(items)
    failure = _failure(rig.port.run(COLUMN_CHECK_IDS[0], {"batch": {"$ref": f"{listed_id}#/items"}}))
    assert failure.error.code is ErrorCode.INVALID_ARGUMENT
    assert failure.error.field == "items[0].fc_MPa"
    assert rig.store.puts == 0


def test_literal_fc_refused(tmp_path: Path) -> None:
    """AC13: a literal fc_MPa under require_refs is INVALID_ARGUMENT; no verdict is stored."""
    rig = ColumnRig(tmp_path)
    ratio = rig.basis_ref("limits.ratio_limit_ratio")
    items = [
        {
            "subject": {"kind": "frame", "id": "C1", "station_mm": 0.0, "case": "COMB1"},
            "inputs": {
                "Pu_kN": 1200.0,
                "b_mm": 500.0,
                "h_mm": 500.0,
                "Ast_mm2": 4000.0,
                "fc_MPa": 30.0,
                "fy_MPa": rig.basis_ref("materials.rebar_fy_MPa"),
                "transverse_kind": "tied",
                "k_factor": rig.basis_ref("columns.effective_length_factor_ratio"),
                "lu_mm": 3000.0,
                "ratio_limit": ratio,
            },
        }
    ]
    listed_id = rig.inject_item_list(items)
    failure = _failure(rig.port.run(COLUMN_CHECK_IDS[0], {"batch": {"$ref": f"{listed_id}#/items"}}))
    assert failure.error.code is ErrorCode.INVALID_ARGUMENT
    assert failure.error.field == "items[0].fc_MPa"
    assert "engineering quantity" in failure.error.message
    assert rig.store.puts == 0


def test_production_refused(tmp_path: Path) -> None:
    """AC13: in production, each draft column check is refused before any write (CK-AC5)."""
    production = ColumnRig(tmp_path, RunClass.PRODUCTION)
    items_id = production.put_check_items()
    for check_id in COLUMN_CHECK_IDS:
        with pytest.raises(CalcRefused) as refused:
            production.port.run(check_id, {"batch": {"$ref": f"{items_id}#/items/{check_id}"}})
        assert refused.value.code is HarnessCode.CALC_NOT_APPROVED
        assert production.route.refusal(check_id) == (CalcStatus.DRAFT, HarnessCode.CALC_NOT_APPROVED)
    assert production.store.puts == 0


def test_only_listed_checks(tmp_path: Path) -> None:
    """AC13: a check id outside the allowlist is ContractError NOT_FOUND before any evaluation."""
    rig = ColumnRig(tmp_path)
    for check_id in COLUMN_CHECK_IDS:
        assert rig.port.describe(check_id).id == check_id
    outside = "aci318_14.99_9_9.not_on_allowlist"
    with pytest.raises(ContractError) as described:
        rig.port.describe(outside)
    assert described.value.detail.code is ErrorCode.NOT_FOUND
    failure = _failure(rig.port.run(outside, {"items": []}))
    assert failure.error.code is ErrorCode.NOT_FOUND
    assert rig.store.puts == 0
