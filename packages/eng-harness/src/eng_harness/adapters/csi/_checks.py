"""CSI read-back helpers and the model check (plan 0002 T12b; spec 0002 sections 4.5.8, 4.6.2, AC24).

Every item written since the last check is read back and compared with the requested state: a float within
`ReadBack.tolerance_ratio` (the frozen basis field `checks.readback_relative_tolerance_ratio`, never a constant here;
without it a quantity is `READBACK_UNAVAILABLE`), anything else exactly. The helpers' tables and columns are the
product profile's, host facts for the first local run (OQ-G10).
"""

from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from eng_contract.envelope import HostInfo, Provenance, SuccessEnvelope, make_success
from eng_contract.errors import ContractError, ContractWarning
from eng_contract.ids import Timestamp
from eng_contract.issues import CheckModelSummary, ModelIssue, Severity
from eng_contract.kinds.issues import ModelCheck
from eng_contract.quantity import Quantity
from eng_contract.store import ResultStore
from eng_contract.units import convert, csi_unit_system
from eng_contract.verdicts import Subject, SubjectKind

from eng_harness.adapters.csi import _edits as edits
from eng_harness.adapters.csi._state import LIST_LIMIT, StateRead
from eng_harness.adapters.csi.products import ProductProfile
from eng_harness.adapters.csi.products import _safe_loads as safe_loads
from eng_harness.adapters.csi.products import _sap2000_edits as sap2000_edits
from eng_harness.ports import ServerCheck

Want = dict[str, Any]
Rows = Callable[[str, str, dict[str, Any], str], Awaitable[list[dict[str, Any]]]]
_ERROR = Severity.ERROR
_FLAGS = ("ux", "uy", "uz", "rx", "ry", "rz")


@dataclass(frozen=True)
class Expect:
    """One written item: the read-back `helper`, its `subject` (row id, pattern as `case`) and the `want`ed fields."""

    helper: str
    subject: Subject
    want: Want | None


@dataclass
class Snapshot:
    """What a check reads: the model state, the section names and the read-back tables (absent: not readable)."""

    state: StateRead
    profile: ProductProfile
    frame_sections: set[str]
    area_sections: set[str]
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


def _num(value: Any) -> float:
    return float(value.value if isinstance(value, Quantity) else value)


def _factors(kind: str, parts: list[tuple[str, float]]) -> Want:
    """A combination as flat fields: its type, its item names and one factor per item, by name (stable)."""
    ordered = sorted(parts, key=lambda part: part[0])
    return {"type": kind, "items": [name for name, _ in ordered]} | {
        f"factor {i}": f for i, (_, f) in enumerate(ordered)
    }


def _item(helper: str, kind: SubjectKind, name: str, want: Want | None, case: str | None = None) -> Expect:
    return Expect(helper, Subject(kind=kind, id=name, case=case), want)


def expect(model: Any) -> Expect:
    """What a written call (its canonical model) must show on read-back; `TypeError` for a model with no helper."""
    kind, m = SubjectKind, model
    if isinstance(m, edits.AssignFrameSectionArgs):
        return _item("frame_section", kind.FRAME, m.frame, {"section": m.section})
    if isinstance(m, edits.AssignAreaSectionArgs):
        return _item("area_section_table", kind.AREA, m.area, {"section": m.section})
    if isinstance(m, edits.DefineWallSectionArgs):
        return _item("wall_section_table", kind.SECTION, m.name, {"thickness_mm": _num(m.thickness_mm)})
    if isinstance(m, edits.SetFrameLoadDistributedArgs):
        return _item("frame_load_table", kind.FRAME, m.frame, {"w_kN_m": _num(m.w_kN_m)}, m.pattern)
    if isinstance(m, edits.SetAreaLoadUniformArgs):
        return _item("area_load_table", kind.AREA, m.area, {"q_kPa": _num(m.q_kPa)}, m.pattern)
    if isinstance(m, edits.AddLoadPatternArgs):
        want = {"type": m.type.value, "self_weight_ratio": _num(m.self_weight_ratio)}
        return _item("load_pattern", kind.LOAD_PATTERN, m.name, want)
    if isinstance(m, edits.AddLoadComboArgs):
        want = _factors(m.type.value, [(i.case.case, _num(i.scale_ratio)) for i in m.items])
        return _item("load_combo", kind.LOAD_COMBINATION, m.name, want)
    if isinstance(m, edits.DeleteLoadComboArgs):
        return _item("load_combo", kind.LOAD_COMBINATION, m.name, None)
    if isinstance(m, edits.SetPointRestraintArgs):
        return _item("restraint_table", kind.JOINT, m.joint, {n: getattr(m, n) for n in _FLAGS})
    if isinstance(m, safe_loads.SetPointLoadArgs):
        point_want: Want = {
            "FX_kN": _num(m.FX_kN),
            "FY_kN": _num(m.FY_kN),
            "FZ_kN": _num(m.FZ_kN),
            "MX_kNm": _num(m.MX_kNm),
            "MY_kNm": _num(m.MY_kNm),
            "MZ_kNm": _num(m.MZ_kNm),
        }
        if m.punch_x_mm is not None:
            point_want["punch_x_mm"] = _num(m.punch_x_mm)
        if m.punch_y_mm is not None:
            point_want["punch_y_mm"] = _num(m.punch_y_mm)
        return _item("point_load_table", kind.JOINT, m.joint, point_want, m.pattern)
    if isinstance(m, sap2000_edits.AddFrameByCoordArgs):
        # Subject id starts as the requested name; CsiToolPort.retargets it to the host reply (spec 0012 AC11).
        subject = m.name or ""
        want = {
            "section": m.section,
            "xi_mm": _num(m.xi_mm),
            "yi_mm": _num(m.yi_mm),
            "zi_mm": _num(m.zi_mm),
            "xj_mm": _num(m.xj_mm),
            "yj_mm": _num(m.yj_mm),
            "zj_mm": _num(m.zj_mm),
        }
        return _item("frame_geometry", kind.FRAME, subject, want)
    if isinstance(m, sap2000_edits.AddAreaByCoordArgs):
        subject = m.name or ""
        return _item("area_geometry", kind.AREA, subject, {"section": m.section, "points_mm": m.points})
    raise TypeError(f"no read-back for {type(m).__name__}")


class WrittenItems:
    """The items written since the last check, per model key: `prepare` before the send, `commit` after the reply.

    The pair is matched by the model key of the canonical model (one write at a time to a model); an item prepared for
    a call that then failed is replaced by the next `prepare`, never committed.
    """

    def __init__(self) -> None:
        self._prepared: dict[str, Expect] = {}
        self._written: dict[str, list[Expect]] = {}

    def prepare(self, model: Any) -> None:
        self._prepared[model.model] = expect(model)

    def retarget(self, key: str, host_id: str) -> None:
        """Replace the prepared subject's id with the host-assigned name (spec 0012 AC11)."""
        item = self._prepared.get(key)
        if item is not None:
            self._prepared[key] = Expect(
                item.helper, Subject(kind=item.subject.kind, id=host_id, case=item.subject.case), item.want
            )

    def commit(self, key: str) -> None:
        item = self._prepared.pop(key, None)
        if item is not None:
            self._written.setdefault(key, []).append(item)

    def items(self, key: str) -> list[Expect]:
        return list(self._written.get(key, ()))

    def clear(self, key: str) -> None:
        self._written.pop(key, None)


@dataclass(frozen=True)
class ReadBack:
    """What `check_model` needs besides the host: the book of written items, the result store, the server build.

    `tolerance_ratio` is the frozen value of the basis field `checks.readback_relative_tolerance_ratio`, handed over
    when the port is wired for a run (OQ-Q65); `None` while the workflow gives none.
    """

    written: WrittenItems
    store: ResultStore
    check: ServerCheck
    tolerance_ratio: float | None = None


def _row(rows: list[dict[str, Any]], match: Mapping[str, str | None]) -> dict[str, Any] | None:
    return next((row for row in rows if all(row.get(name) == value for name, value in match.items())), None)


def _payload(
    kind: str, part: str, column: str, shape: Callable[[Want], Want] = lambda row: row
) -> Callable[[Snapshot, Subject], Want | None]:
    def read(s: Snapshot, subject: Subject) -> Want | None:
        match = {column: subject.id} | ({"pattern": subject.case} if subject.case else {})
        row = _row(s.state.payloads[kind].model_dump(mode="json")[part], match)
        return None if row is None else shape(row)

    return read


def _table(name: str, output: str, scale: Callable[[Snapshot, Any], Any]) -> Callable[[Snapshot, Subject], Want | None]:
    def read(s: Snapshot, subject: Subject) -> Want | None:
        _, key_column, value_column = s.profile.readback[name]
        row = _row(s.tables[name], {key_column: subject.id})
        return None if row is None else {output: scale(s, row[value_column])}

    return read


def _combo(row: Want) -> Want:
    return _factors(row["type"], [(i["case"]["case"], i["scale_ratio"]) for i in row["items"]])


def _millimetres(s: Snapshot, raw: Any) -> float:  # a table has no units token: its length is in the present units
    return convert(float(raw), csi_unit_system(s.state.status.units).length, "mm")


def _point_load(row: Want) -> Want:
    """Canonical force/moment fields; punch dims when the table carried them (spec 0008 AC18)."""
    want = {name: row[name] for name in ("FX_kN", "FY_kN", "FZ_kN", "MX_kNm", "MY_kNm", "MZ_kNm")}
    if row.get("punch_x_mm") is not None:
        want["punch_x_mm"] = row["punch_x_mm"]
    if row.get("punch_y_mm") is not None:
        want["punch_y_mm"] = row["punch_y_mm"]
    return want


def _frame_geometry(s: Snapshot, subject: Subject) -> Want | None:
    """Points and section of one frame from `model.frame_placements/1` (spec 0012 AC11)."""
    frames = s.state.payloads["model.frame_placements/1"].model_dump(mode="json")["frames"]
    row = _row(frames, {"id": subject.id})
    if row is None:
        return None
    i_pt, j_pt = row["i"], row["j"]
    return {
        "section": row["section"],
        "xi_mm": i_pt["x_mm"],
        "yi_mm": i_pt["y_mm"],
        "zi_mm": i_pt["z_mm"],
        "xj_mm": j_pt["x_mm"],
        "yj_mm": j_pt["y_mm"],
        "zj_mm": j_pt["z_mm"],
    }


def _area_geometry(s: Snapshot, subject: Subject) -> Want | None:
    """Section and boundary points of one area from `model.area_placements/1` (spec 0012 AC13)."""
    areas = s.state.payloads["model.area_placements/1"].model_dump(mode="json")["areas"]
    row = _row(areas, {"id": subject.id})
    if row is None:
        return None
    points = [[p["x_mm"], p["y_mm"], p["z_mm"]] for p in row["points"]]
    return {"section": row["section"], "points_mm": points}


OBSERVE: dict[str, Callable[[Snapshot, Subject], Want | None]] = {  # by the allowlist's `readback` name
    "frame_section": _payload("model.frame_placements/1", "frames", "id"),
    "frame": _frame_geometry,  # allowlist readback for csi_add_frame_by_coord
    "frame_geometry": _frame_geometry,
    "area": _area_geometry,  # allowlist readback for csi_add_area_by_coord
    "area_geometry": _area_geometry,
    "area_section_table": _table("area_section", "section", lambda s, raw: raw),
    "wall_section_table": _table("wall_section", "thickness_mm", _millimetres),
    "frame_load_table": _payload("model.load_set/1", "frame_loads", "frame"),
    "area_load_table": _payload("model.load_set/1", "area_loads", "area"),
    "load_pattern": _payload("model.load_set/1", "patterns", "name"),
    "load_combo": _payload("model.load_set/1", "combinations", "name", _combo),
    "restraint_table": _payload("model.joint_restraints/1", "joints", "joint"),
    "point_load_table": _payload("harness.joint_loads/1", "loads", "joint", _point_load),
}


def _differs(got: Want, want: Want, tolerance: float) -> bool:
    """True when a field of `want` is not in `got`: a float must lie within `tolerance` of it, any other be equal."""
    for name, wanted in want.items():
        seen = got.get(name)
        if isinstance(wanted, float):
            if not isinstance(seen, int | float) or not abs(seen - wanted) <= tolerance * abs(wanted):
                return True
        elif seen != wanted:
            return True
    return False


def compare(item: Expect, snap: Snapshot, tolerance: float | None) -> ModelIssue | None:
    """The read-back issue of one written item, or `None` when it shows the requested state."""

    def issue(code: str, message: str, severity: Severity = _ERROR) -> ModelIssue:
        return ModelIssue(severity=severity, code=code, subject=item.subject, message=message)

    observe, name = OBSERVE[item.helper], item.subject.id
    try:
        got = observe(snap, item.subject)
    except KeyError, TypeError, ValueError:  # a table not read, or rows not as assumed (OQ-G10): nothing to compare
        return issue("READBACK_UNAVAILABLE", f"the read-back of {item.helper} could not be read")
    if item.want is None:
        return None if got is None else issue("READBACK_MISMATCH", f"{name} is still present")
    if got is None:
        return issue("READBACK_MISMATCH", f"{name} is absent")
    # Spec 0012 AC13: without a pattern-defs table, presence by name is enough; type and self-weight are unchecked.
    if item.helper == "load_pattern" and "pattern_defs" not in snap.profile.tables:
        return None
    if tolerance is None and any(isinstance(wanted, float) for wanted in item.want.values()):
        return issue("READBACK_UNAVAILABLE", "no read-back tolerance (checks.readback_relative_tolerance_ratio)")
    if _differs(got, item.want, tolerance or 0.0):
        return issue(
            "READBACK_MISMATCH", f"{name} reads { ({k: got.get(k) for k in item.want}) }, requested {item.want}"
        )
    return None


def pattern_partial(item: Expect, snap: Snapshot) -> ModelIssue | None:
    """`READBACK_PARTIAL` warning when a pattern's type and self-weight were not table-checked (spec 0012 AC13)."""
    if item.helper != "load_pattern" or "pattern_defs" in snap.profile.tables:
        return None
    return ModelIssue(
        severity=Severity.WARNING,
        code="READBACK_PARTIAL",
        subject=item.subject,
        message=f"{item.subject.id}: type and self-weight unchecked until the pattern table is keyed",
    )


def integrity(snap: Snapshot) -> list[ModelIssue]:
    """The checks that need no tolerance (spec 4.5.8 / 0008 §4.7): sections, combos, lock, SAFE joint/soil issues."""

    def issue(code: str, kind: SubjectKind, name: str, message: str, severity: Severity = _ERROR) -> ModelIssue:
        return ModelIssue(severity=severity, code=code, subject=Subject(kind=kind, id=name), message=message)

    payloads = snap.state.payloads
    frames = payloads["model.frame_placements/1"].model_dump(mode="json")["frames"]
    areas = payloads["model.area_placements/1"].model_dump(mode="json")["areas"]
    loads = payloads["model.load_set/1"].model_dump(mode="json")
    defined = {  # a load case (analysis case) is not defined by the neutral kinds, so it is not checked
        "load_pattern": {row["name"] for row in loads["patterns"]},
        "load_combination": {row["name"] for row in loads["combinations"]},
    }
    found = [
        issue("SECTION_UNDEFINED", kind, row["id"], f"the section {row['section']} is not defined")
        for kind, rows, sections in (
            (SubjectKind.FRAME, frames, snap.frame_sections),
            (SubjectKind.AREA, areas, snap.area_sections),
        )
        for row in rows
        if row["section"] not in sections
    ]
    found += [
        issue("COMBO_REFERENCE_MISSING", SubjectKind.LOAD_COMBINATION, combo["name"], f"{ref['case']} is not defined")
        for combo in loads["combinations"]
        for ref in (part["case"] for part in combo["items"])
        if ref["case"] not in defined.get(ref["case_type"], {ref["case"]})
    ]
    if snap.state.status.locked:
        found.append(issue("MODEL_LOCKED", SubjectKind.MODEL, "model", "the model is locked", Severity.INFO))
    # SAFE integrity (spec 0008 section 4.7): present when the state carried joint loads / soil supports.
    if "harness.joint_loads/1" in payloads and "harness.model_points/1" in payloads:
        point_names = {str(row["name"]) for row in payloads["harness.model_points/1"].model_dump(mode="json")["points"]}
        for row in payloads["harness.joint_loads/1"].model_dump(mode="json")["loads"]:
            if row["joint"] not in point_names:
                found.append(
                    issue(
                        "JOINT_LOAD_ON_MISSING_JOINT",
                        SubjectKind.JOINT,
                        str(row["joint"]),
                        f"joint load on missing joint {row['joint']}",
                    )
                )
    if "harness.safe_soil_supports/1" in payloads:
        soil = payloads["harness.safe_soil_supports/1"].model_dump(mode="json")
        supported = {str(row["area"]) for row in soil.get("assignments", []) if row.get("property") is not None}
        for row in areas:
            if row["id"] not in supported:
                found.append(
                    issue(
                        "AREA_WITHOUT_SOIL_SUPPORT",
                        SubjectKind.AREA,
                        str(row["id"]),
                        f"area {row['id']} has no soil support",
                        Severity.WARNING,
                    )
                )
    return found


async def snapshot(rows: Rows, target: dict[str, Any], state: StateRead, profile: ProductProfile) -> Snapshot:
    """Read the section names and the read-back tables with `rows`; a table whose read fails is left out of `tables`.

    A section list the host cut or garbled raises `ContractError` (`LIMIT_EXCEEDED`, `HOST_ERROR`); a table never does.
    """

    async def names(tool: str) -> set[str]:
        return {str(row.get("name")) for row in await rows(tool, "items", {**target, "limit": LIST_LIMIT}, tool)}

    snap = Snapshot(state, profile, await names("csi_list_frame_sections"), await names("csi_list_area_sections"))
    for name, (table, key_column, value_column) in profile.readback.items():
        try:
            found = await rows("csi_db_table_read", "rows", {**target, "table": table, "row_limit": LIST_LIMIT}, table)
        except ContractError:  # any failure: the table is left out, its items read READBACK_UNAVAILABLE
            continue
        if all({key_column, value_column} <= row.keys() for row in found):
            snap.tables[name] = found
    return snap


def issues_of(read_back: ReadBack, model_key: str, snap: Snapshot) -> list[ModelIssue]:
    """The read-back issues of `model_key`'s items, then the tolerance-free ones; the caller clears the items later."""
    items = read_back.written.items(model_key)
    found = [issue for item in items if (issue := compare(item, snap, read_back.tolerance_ratio)) is not None]
    found += [issue for item in items if (issue := pattern_partial(item, snap)) is not None]
    return [*found, *integrity(snap)]


def check_envelope(
    read_back: ReadBack, issues: list[ModelIssue], warnings: list[ContractWarning], host: HostInfo, started: Timestamp,
    duration_ms: int,
) -> SuccessEnvelope:  # fmt: skip
    """Store the `issues.model_check/1` of `issues` and answer its envelope, with `warnings` of the adapter."""
    tally = Counter(issue.severity for issue in issues)
    counts = {"errors": tally[_ERROR], "warnings": tally[Severity.WARNING], "infos": tally[Severity.INFO]}
    summary = CheckModelSummary(**counts, clean=not tally[_ERROR])
    payload = ModelCheck(summary=summary, issues=issues).model_dump(mode="json")
    producer = Provenance(
        tool="harness/check_model", tool_version=read_back.check.build, host=host, inputs={}, started_at=started,
        duration_ms=duration_ms,
    )  # fmt: skip
    record = read_back.store.put("issues.model_check/1", payload, producer)
    return make_success(record, summary.model_dump(mode="json"), warnings)
