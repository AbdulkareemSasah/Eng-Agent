"""Column-workflow kind payloads (spec 0013 sections 4.2 and 4.4). Errors: `pydantic.ValidationError`."""

from types import GenericAlias
from typing import Annotated, Literal, cast

from eng_contract.refs import RefString
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator

from eng_harness.kinds.calcs import CalcPayload, SummaryChanges, Top
from eng_harness.kinds.edit_cycle import Label

_Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Count = Annotated[int, Field(ge=0)]
_Origin = Literal["preexisting", "changed_in_design"]
_Opt = (Label | None, None)
_Float = (float | None, None)
_CHECKS = ["aci318_14.22_4_2_1.max_axial_strength", "aci318_14.22_4_1_1.axial_flexure_uniaxial"]
_CHECKS += ["aci318_14.10_6_1_1.longitudinal_reinforcement_limits"]  # spec 0013 section 4.5
_LIMITS = _CHECKS[2]
_SEL = Literal["UNKNOWN_FRAME", "UNKNOWN_STORY", "UNKNOWN_SECTION"]
_MISS = Literal["FORCES_MISSING", "AXES_UNDECLARED", "SHAPE_NOT_CHECKED", "LAYOUT_MISSING"]
_BLOCK = Literal["SHAPE_NOT_SUPPORTED", "SECTION_ROLES_UNMAPPED", "TYPE_AMBIGUOUS", "NAME_CONFLICT"]
_READ = Literal["ELEMENT_MISSING", "TYPE_MISMATCH", "VALUE_MISMATCH", "UNEXPECTED_TYPE_CHANGE", "NOT_READ"]
_SHAPE = Literal["rectangular", "circular", "other"]
_MATCH = Literal["matched", "no_section_in_model", "ambiguous"]
_FP = Annotated[str, StringConstraints(pattern=r"^fp1:[0-9a-f]{64}$")]


class _P(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


def _ann(model: type[BaseModel], form: str = "list") -> object:
    listed = GenericAlias(list, (model,))
    if form == "map":
        return GenericAlias(dict, (str, listed))
    if form == "opt":
        return (model.__or__(type(None)), None)
    return listed


def _check(self: BaseModel) -> BaseModel:
    data = self.__dict__
    match type(self).__name__:
        case "ColumnSelection":
            failed = bool(data["issues"]) or not data["columns"]
            if (data["status"] == "FAIL") != failed:
                raise ValueError("status is FAIL on an error issue or an empty selection")
        case "ColumnCheckItems":
            if set(data["items"]) != set(_CHECKS):
                raise ValueError("items must hold the three check ids")
            for check_id, group in data["items"].items():
                for row in group:
                    subject = row.__dict__["subject"].__dict__
                    bare = subject["case"] is None and subject["station_mm"] is None
                    if bare != (check_id == _LIMITS):
                        raise ValueError("case and station_mm are null exactly for the reinforcement limits")
        case "_ReviewRow":
            if data["not_checked"] and data["status"] is not VerdictStatus.NEEDS_ENGINEER:
                raise ValueError("status is NEEDS_ENGINEER when not_checked is set")
        case "ColumnMatch":
            one = data["section"] is not None and data["names"] == [data["section"]]
            none = data["section"] is None and not data["names"]
            several = data["section"] is None and len(data["names"]) > 1  # spec 0013 section 4.4.4: several
            agreed = {"matched": one, "no_section_in_model": none, "ambiguous": several}[data["status"]]
            if not agreed:
                raise ValueError("section and names must agree with status")
        case "GeneratedChangeSet":
            frames = [item.__dict__["frames"] for item in data["items"]]
            keys = [row[0] for row in frames if row]
            if len(keys) != len(frames) or keys != sorted(keys):
                raise ValueError("items must name one frame and be sorted by frame id")
        case "_Assign":
            if (data["type_id"] is None) == (data["new_type_name"] is None):
                raise ValueError("give type_id or new_type_name, not both and not neither")
        case "RevitColumnReadback":
            later = data["after_revision"] > data["before_revision"]
            if data["status"] != ("PASS" if not data["issues"] and later else "FAIL"):
                raise ValueError("status is PASS only without issues and with a later revision")
        case "ColumnDesignRecord":
            ids = [row.__dict__["frame_id"] for row in data["changed"]]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate frame id in changed")
    return self


def _model(model_name: str, base: type[BaseModel], /, **fields: object) -> type[BaseModel]:
    annotations: dict[str, object] = {}
    namespace: dict[str, object] = {"__annotations__": annotations, "_check": model_validator(mode="after")(_check)}
    for key, value in fields.items():
        if isinstance(value, tuple):
            annotations[key], namespace[key] = value[0], value[1]
        else:
            annotations[key] = value
    return cast(type[BaseModel], type(model_name, (base,), namespace))


def _row(model_name: str, /, **fields: object) -> type[BaseModel]:
    return _model(model_name, _P, **fields)


A = _ann
C = CalcPayload
L = Label
V = VerdictStatus
R = RefString
_PF = Literal["PASS", "FAIL"]
_Column = _row("_Column", frame_id=L, section=L, shape=_SHAPE, material=L, story=L, length_mm=float)
_Excluded = _row("_Excluded", frame_id=L, reason=Literal["NOT_VERTICAL"])
_SelIssue = _row("_SelIssue", code=_SEL, name=L)
_Subject = _row("_Subject", kind=Literal["frame"], id=L, station_mm=_Float, case=_Opt)
_Item = _row("_Item", subject=_Subject, inputs=dict[L, R])
_Miss = _row("_Miss", frame_id=L, code=_MISS, gap=_Opt)
_Gov = _row("_Gov", ref=R, ratio=_Float)
_FrameItem = _row("_FrameItem", id=L, kind=Literal["frame_section"], frames=list[L], section=L)
_ChangeIssue = _row("_ChangeIssue", frame_id=L, code=Literal["NOT_IMPLEMENTED"], gap=Literal["CW-G3"])
_NewType = _row("_NewType", family=L, section=L, name=L, from_unique_id=L, origins=list[_Origin], roles=dict[L, R])
_Same = _row("_Same", unique_id=L, type_id=L)
_Blocked = _row("_Blocked", frame_id=L, code=_BLOCK)
_Orient = _row("_Orient", frame_id=L, rotations=tuple[R, R])
_ExpectEl = _row("_ExpectEl", unique_id=L, type_name=L)
_ExpectType = _row("_ExpectType", name=L, roles=dict[L, R])
_Expected = _row("_Expected", elements=A(_ExpectEl), types=A(_ExpectType))
_RbIssue = _row("_RbIssue", unique_id=L, code=_READ)
_Changed = _row("_Changed", frame_id=L, from_section=L, to_section=L)
_row_kw = {"frame_id": L, "status": V, "host_status": V, "code_status": V}
_ReviewRow = _model("_ReviewRow", _P, governing=A(_Gov, "opt"), not_checked=list[L], gaps=list[L], **_row_kw)
_sel = {"status": _PF, "columns": A(_Column), "excluded": A(_Excluded), "issues": A(_SelIssue)}
ColumnSelection = _model("ColumnSelection", C, **_sel)
ColumnCheckItems = _model("ColumnCheckItems", C, items=A(_Item, "map"), not_checked=A(_Miss))
_rev_kw = {"columns": A(_ReviewRow), "failing": list[L], "attention": list[L], "top": Top}
ColumnReview = _model("ColumnReview", C, changes=SummaryChanges, complete=StrictBool, **_rev_kw)
ColumnMatch = _model("ColumnMatch", C, status=_MATCH, section=_Opt, names=list[L])
_set_kw = {"source": L, "items": A(_FrameItem), "note": _Opt, "benchmark_request": _Opt}
GeneratedChangeSet = _model("GeneratedChangeSet", C, issues=A(_ChangeIssue), **_set_kw)
_asg_kw = {"unique_id": L, "element_id": L, "from_type_id": L, "type_id": _Opt}
_Assign = _model("_Assign", _P, new_type_name=_Opt, origin=_Origin, **_asg_kw)
_upd_kw = {"new_types": A(_NewType), "assignments": A(_Assign), "no_change": A(_Same)}
_upd_kw |= {"not_updatable": A(_Blocked), "orientation": A(_Orient), "expected": _Expected, "complete": StrictBool}
RevitColumnUpdate = _model("RevitColumnUpdate", C, **_upd_kw)
_rb = {"status": _PF, "issues": A(_RbIssue), "before_revision": _Count, "after_revision": _Count}
RevitColumnReadback = _model("RevitColumnReadback", C, **_rb)
_rec_kw = {"revision": L, "fingerprint": _FP, "file_sha256": _Sha, "changed": A(_Changed)}
ColumnDesignRecord = _model("ColumnDesignRecord", _P, selection=R, review=R, **_rec_kw)
_KIND_NAMES: tuple[str, ...] = ("harness.column_selection/1", "harness.column_check_items/1", "harness.column_review/1")
_KIND_NAMES += ("harness.column_match/1", "harness.generated_change_set/1", "harness.revit_column_update/1")
_KIND_NAMES += ("harness.revit_column_readback/1", "harness.column_design_record/1")
_MODELS: tuple[type[BaseModel], ...] = (ColumnSelection, ColumnCheckItems, ColumnReview, ColumnMatch)
_MODELS += (GeneratedChangeSet, RevitColumnUpdate, RevitColumnReadback, ColumnDesignRecord)
COLUMN_DESIGN_KINDS: dict[str, type[BaseModel]] = dict(zip(_KIND_NAMES, _MODELS, strict=True))
