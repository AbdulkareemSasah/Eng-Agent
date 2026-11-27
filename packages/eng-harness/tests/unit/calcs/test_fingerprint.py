"""Calc 1, model fingerprint (plan 0003 T7; spec 0003 4.6, AC19 to AC23): rules F1 to F6 on synthetic read sets."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from eng_contract.envelope import FailureEnvelope, HostInfo, Provenance, RefInput, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from pydantic import JsonValue, ValidationError

from eng_harness._calc._approvals import ApprovalsFile
from eng_harness._calc._hash import read_lock
from eng_harness._calc._port import CalcSettings, HarnessCalcPort
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.calc import InputMeta, TraceBuilder
from eng_harness.calcs import REGISTRY, same_state
from eng_harness.calcs.model_fingerprint import FingerprintBody, FingerprintInput, StateMatch
from eng_harness.kinds.calcs import ModelFingerprint
from eng_harness.ports import RunClass

CALC_ID = "harness.model_fingerprint"
MDL = "mdl_00000000000000000000000000"
OTHER_MDL = "mdl_00000000000000000000000009"
GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden" / "calcs"
KINDS = {
    "frames": "model.frame_placements/1",
    "areas": "model.area_placements/1",
    "restraints": "model.joint_restraints/1",
    "stories": "model.stories/1",
}


def _point(x: float, y: float, z: float) -> dict[str, JsonValue]:
    return {"x_mm": x, "y_mm": y, "z_mm": z}


FRAMES: dict[str, JsonValue] = {
    "frames": [
        {
            "id": "F1",
            "kind": "column",
            "section": "S1",
            "i": _point(0, 0, 0),
            "j": _point(0, 0, 3000),
            "rotation_deg": 0,
        }
    ]
}
AREAS: dict[str, JsonValue] = {
    "areas": [
        {
            "id": "A1",
            "kind": "slab",
            "section": "SL1",
            "points": [_point(0, 0, 0), _point(1, 0, 0), _point(1, 1, 0), _point(0, 1, 0)],
            "joints": ["J1", "J2", "J3", "J4"],
        }
    ]
}
RESTRAINTS: dict[str, JsonValue] = {
    "joints": [{"joint": "J1", "ux": True, "uy": True, "uz": True, "rx": False, "ry": False, "rz": False}]
}


def _meta(
    fields: dict[str, Any], *, model: dict[str, tuple[str | None, int | None]] | None = None, **flags: bool
) -> InputMeta:
    refs = {}
    for n, name in enumerate(fields, start=1):
        model_id, revision = (model or {}).get(name, (MDL, 3))
        result_id = f"res_0000000000000000000000000{n}"
        refs[name] = {
            "result_id": result_id,
            "ref": result_id,
            "kind": KINDS[name],
            "complete": flags.get(name, True),
            "model_id": model_id,
            "model_revision": revision,
            "parents": [],
            "producer_tool": "csi",
        }
    return InputMeta.model_validate({"refs": refs})


def _run(fields: dict[str, Any], meta: InputMeta | None = None, trace: TraceBuilder | None = None) -> FingerprintBody:
    inp = FingerprintInput.model_validate(fields)
    body = REGISTRY[CALC_ID](inp, meta or _meta(fields), trace or TraceBuilder())
    assert isinstance(body, FingerprintBody)
    return body


def test_registered_as_draft_with_its_lock_entry() -> None:
    definition = REGISTRY[CALC_ID]
    assert (definition.version, definition.verification, definition.output_kind) == (
        1,
        "draft",
        "harness.model_fingerprint/1",
    )
    entries = {e["id"]: e for e in read_lock()["calcs"]}
    entry = entries[CALC_ID]
    assert (entry["id"], entry["version"]) == (CALC_ID, 1)
    assert re.fullmatch(r"[0-9a-f]{64}", entry["content_sha256"])


def test_incomplete_read() -> None:
    fields = {"frames": FRAMES, "restraints": RESTRAINTS}
    whole = _run(fields)
    partial = _run(fields, _meta(fields, restraints=False))
    assert whole.complete is True
    assert partial.complete is False
    assert [s.complete for s in partial.sections] == [True, False]  # frame_placements, joint_restraints
    assert same_state(partial, partial) is StateMatch.UNKNOWN  # never same (F6, AC22)
    assert same_state(whole, partial) is StateMatch.UNKNOWN
    assert same_state(partial, whole) is StateMatch.UNKNOWN


def test_same_state() -> None:
    a = _run({"frames": FRAMES, "restraints": RESTRAINTS})
    moved = json.loads(json.dumps(FRAMES))
    moved["frames"][0]["j"]["x_mm"] = 0.5
    b = _run({"frames": moved, "restraints": RESTRAINTS})
    fewer = _run({"frames": FRAMES})
    assert same_state(a, a) is StateMatch.SAME
    assert same_state(a, b) is StateMatch.DIFFERENT
    assert same_state(a, fewer) is StateMatch.UNKNOWN  # covered lists differ
    assert [m.value for m in StateMatch] == ["same", "different", "unknown"]


@pytest.mark.parametrize(
    ("model", "field"),
    [
        ({"restraints": (OTHER_MDL, 3)}, "restraints"),
        ({"restraints": (MDL, 4)}, "restraints"),
        ({"frames": (None, None)}, "frames"),
    ],
)
def test_mixed_models_refused(model: dict[str, tuple[str | None, int | None]], field: str) -> None:
    fields = {"frames": FRAMES, "restraints": RESTRAINTS}
    with pytest.raises(ContractError) as caught:
        _run(fields, _meta(fields, model=model))
    assert caught.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert caught.value.detail.field == field


def test_literal_without_record_refused() -> None:
    with pytest.raises(ContractError) as caught:
        _run({"frames": FRAMES}, InputMeta(refs={}))
    assert (caught.value.detail.code, caught.value.detail.field) == (ErrorCode.INVALID_ARGUMENT, "frames")


def test_no_section_refused() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        FingerprintInput.model_validate({})


def test_empty_list_is_hashed() -> None:
    body = _run({"frames": {"frames": []}})
    assert [(s.kind, s.items) for s in body.sections] == [("model.frame_placements/1", 0)]
    assert body.sections[0].sha256 == hashlib.sha256(b'{"frames":[]}').hexdigest()


def test_area_points_and_joints_keep_their_order() -> None:
    base = _run({"areas": AREAS})
    rotated = json.loads(json.dumps(AREAS))
    area = rotated["areas"][0]
    area["points"] = area["points"][1:] + area["points"][:1]
    joints = json.loads(json.dumps(AREAS))
    joints["areas"][0]["joints"] = ["J2", "J1", "J3", "J4"]
    assert _run({"areas": rotated}).fingerprint != base.fingerprint  # (d): rotated by one vertex
    assert _run({"areas": joints}).fingerprint != base.fingerprint


def test_stories_keep_their_order_and_sections_are_sorted() -> None:
    stories = {
        "base_elevation_mm": 0,
        "stories": [
            {"name": "L1", "elevation_mm": 3000, "height_mm": 3000, "master_story": True},
            {"name": "L2", "elevation_mm": 6000, "height_mm": 3000, "master_story": False},
        ],
    }
    body = _run({"stories": stories, "frames": FRAMES})
    assert body.covered == ["model.frame_placements/1", "model.stories/1"]
    expected = (
        b'{"base_elevation_mm":0,"stories":[{"elevation_mm":3000,"height_mm":3000,"master_story":true,"name":"L1",'
        b'"similar_to":null},{"elevation_mm":6000,"height_mm":3000,"master_story":false,"name":"L2","similar_to":null}]}'
    )
    assert body.sections[1].sha256 == hashlib.sha256(expected).hexdigest()


def test_trace_records_each_section_and_the_fingerprint() -> None:
    trace = TraceBuilder()
    fields = {"frames": FRAMES, "restraints": RESTRAINTS}
    body = _run(fields, trace=trace)
    built = trace.build(REGISTRY[CALC_ID], REGISTRY.content_hash(CALC_ID))
    assert [(i.name, i.ref) for i in built.inputs] == [
        ("frames", "res_00000000000000000000000001"),
        ("restraints", "res_00000000000000000000000002"),
    ]
    # one row each, so the record's payload hash equals the section hash
    assert [i.value for i in built.inputs] == [s.sha256 for s in body.sections]
    assert [(s.name, s.value, s.source) for s in built.steps] == [
        ("frames_sha256", body.sections[0].sha256, "§4.6 F2, F3"),
        ("restraints_sha256", body.sections[1].sha256, "§4.6 F2, F3"),
        ("fingerprint", body.fingerprint, "§4.6 F4"),
    ]
    assert built.steps[2].uses == ["frames_sha256", "restraints_sha256"]
    assert built.outputs == ["fingerprint"]


_BYTES = re.compile(r"^bytes\[(?P<name>[^\]]+)\] = (?P<bytes>.+)$", re.MULTILINE)


@pytest.mark.parametrize("path", sorted(GOLDEN.glob("fingerprint-*.json")), ids=lambda p: p.stem)
def test_golden_hashes_match_the_hand_written_bytes(path: Path) -> None:
    """AC21: the expected hashes are SHA-256 (hashlib) of the bytes the golden file writes by hand."""
    case = json.loads(path.read_text(encoding="utf-8"))
    written = {m["name"]: hashlib.sha256(m["bytes"].encode()).hexdigest() for m in _BYTES.finditer(case["derivation"])}
    expected = case["expected"]
    assert written.pop("fingerprint") == expected["fingerprint"].removeprefix("fp1:")
    assert written == {s["kind"]: s["sha256"] for s in expected["sections"]}


def test_runs_through_the_calc_port(tmp_path: Path) -> None:
    clock = FixedClock(1_767_225_600_000, 1)
    ids = SeededIdSource(b"harness", clock)
    store = ResultStore(Workspace(root=tmp_path / "ws", classification=LocationClass.LOCAL), HARNESS_KINDS, ids, clock)
    host = HostInfo(program="fake", version="1", model_id=MDL, model_revision=3)
    producer = Provenance(
        tool="fake-host/read_model", tool_version="t", host=host, inputs={}, started_at=clock.now(), duration_ms=0
    )
    frames = store.put("model.frame_placements/1", FRAMES, producer).result_id
    restraints = store.put("model.joint_restraints/1", RESTRAINTS, producer, complete=False).result_id
    approvals = ApprovalsFile.model_validate({"schema": 1, "approvals": [], "withdrawn": []})
    port = HarnessCalcPort(REGISTRY, approvals, store, CalcSettings(max_items=100), RunClass.TRIAL, clock, ids)
    envelope = port.run(CALC_ID, {"frames": {"$ref": frames}, "restraints": {"$ref": restraints}})
    assert isinstance(envelope, SuccessEnvelope), envelope
    record = store.get(envelope.result_id)
    stored = ModelFingerprint.model_validate(store.payload(record.result_id))
    assert (stored.complete, stored.draft, record.complete) == (False, True, False)
    assert stored.covered == ["model.frame_placements/1", "model.joint_restraints/1"]
    assert record.producer.inputs == {"frames": RefInput(ref=frames), "restraints": RefInput(ref=restraints)}
    literal = port.run(CALC_ID, {"frames": FRAMES})
    assert isinstance(
        literal, FailureEnvelope
    )  # engineering_quantity: a literal read set is refused under require_refs
