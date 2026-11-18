"""Calc `harness.expected_effects` v1: what the accepted items of a resolved change set should do (spec 0007 4.4.2).

Purpose: project each accepted item onto the model as `set`, `add` and `remove` effects on the reported key of spec 0003
4.7 D2 (list name included), so that the read-back check (spec 0003 4.8) explains every change of a correct write by an
effect on its own key. A property of an object the step 3 state holds is a `set`; an object it lacks is an `add` of the
whole object; a deleted combination is a `remove`. An existing combination is a `set` of its type and one effect per
item key (`set` of the scale, `add`, `remove`). Effects are sorted by section, key and pointer; an item with several
effects gives each the item id, `/` and the position among that item's effects.
Inputs: `check` (status PASS), `approval_items` (the accepted ids), `change_set` and `basis` (the check holds
references only), and the step 3 read set as the flat fields `sections`, `loads` and `restraints`.
Units: a literal is converted to the canonical unit the check names by `eng_contract.units`, exactly; a basis value is
taken as stored (its name carries the canonical unit suffix). Booleans and names are not quantities.
Errors: `ContractError` `INVALID_ARGUMENT` (with `field`) for an input given without a record, a state that is not one
host model revision, a check that is not `PASS`, an accepted id the check, the change set or the effect ids cannot hold,
a value the check did not resolve, and a basis field that is missing, unconfirmed or not a number.
"""

from fractions import Fraction
from typing import Any

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.basis import DesignBasis
from eng_contract.kinds.model import AreaSectionKind, JointRestraints, LoadSet, Sections
from eng_contract.params import eng_param
from eng_contract.refs import RefString
from eng_contract.units import unit
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import as_fraction
from eng_harness.calcs.edit_cycle.change_set_check import ANSWER_FIELD
from eng_harness.kinds.calcs import Effect
from eng_harness.kinds.edit_cycle import ChangeSetCheck, ResolvedItem
from eng_harness.workflows.model_edit_cycle._change_set import ChangeSetDraft

__all__ = ["EffectsBody", "EffectsInput", "expected_effects"]

_STATE = ("sections", "loads", "restraints")
_REFS = ("check", "change_set", *_STATE, "basis")
_FP, _AP = "model.frame_placements/1", "model.area_placements/1"
_SECTIONS, _LOADS, _JOINTS = "model.sections/1", "model.load_set/1", "model.joint_restraints/1"
_GRAVITY = "gravity"
_FLAGS = ("ux", "uy", "uz", "rx", "ry", "rz")
_LOAD_KINDS = (
    ("frame_uniform_load", "frame_loads", "frame", "w", "w_kN_m"),
    ("area_uniform_load", "area_loads", "area", "q", "q_kPa"),
)
"""The load kinds: kind, list of the load set, member naming the target, field of the value, property of the row."""


def _ref(kind: str, default: Any = ...) -> Any:
    return eng_param(default, ref_capable=True, ref_kinds={kind}, engineering_quantity=True)


class EffectsInput(CalcInput):
    """The check, the accepted item ids, the change set, the basis and the step 3 read set."""

    check: ChangeSetCheck = _ref("harness.change_set_check/1")
    approval_items: list[str]
    change_set: ChangeSetDraft = _ref("basis.engineer_input/1")
    sections: Sections | None = _ref(_SECTIONS, None)
    loads: LoadSet = _ref(_LOADS)
    restraints: JointRestraints = _ref(_JOINTS)
    basis: DesignBasis = _ref("basis.design_basis/1")


class EffectsBody(BaseModel):
    """The payload of `harness.expected_effects/1` without `calc`, `draft` and `trace`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    change_set: RefString
    model_id: str
    effects: list[Effect]


def _refuse(field: str, message: str) -> ContractError:
    return ContractError(ErrorCode.INVALID_ARGUMENT, message, field=field)


def _member(case: str, case_type: str, step: str | None) -> list[str]:
    """The D2 key members of a combination item: case, case type, and the step when it is not null."""
    return [case, case_type] if step is None else [case, case_type, step]


class _Projection:
    """The step 3 lookups of one run and the effects found so far."""

    def __init__(self, inp: EffectsInput, basis_id: str, trace: TraceBuilder) -> None:
        self.inp, self.basis_id, self.trace = inp, basis_id, trace
        self.traced: list[str] = []
        self.effects: list[Effect] = []
        loads = inp.loads
        self.sections = None if inp.sections is None else {section.name for section in inp.sections.area_sections}
        self.joints = {row.joint for row in inp.restraints.joints}
        self.combinations = {combination.name: combination for combination in loads.combinations}
        self.rows = {("frame_loads", r.frame, r.pattern, str(r.direction)) for r in loads.frame_loads} | {
            ("area_loads", r.area, r.pattern, str(r.direction)) for r in loads.area_loads
        }

    def put(self, item: str, section: str, key: list[str], pointer: str, value: Any, uom: str | None = None) -> None:
        self.effects.append(
            Effect(item_id=item, section=section, key=key, op="set", pointer=pointer, value=value, unit=uom)
        )

    def new(self, item: str, section: str, key: list[str], value: dict[str, Any]) -> None:
        self.effects.append(Effect(item_id=item, section=section, key=key, op="add", value=value))

    def drop(self, item: str, section: str, key: list[str]) -> None:
        self.effects.append(Effect(item_id=item, section=section, key=key, op="remove"))

    def number(self, resolved: ResolvedItem, pointer: str, value: Any) -> tuple[float, str]:
        """The item's value and its canonical unit: a literal converted exactly, a basis value as stored."""
        canonical = next((row.unit for row in resolved.values if row.pointer == pointer), None)
        if canonical is None:
            raise _refuse("check", f"item {resolved.item_id} has no resolved value at {pointer}")
        if value.source == "input":
            return float(Fraction(value.value) * unit(value.unit).factor / unit(canonical).factor), canonical
        path = value.path
        stored = self.inp.basis.fields.get(path)
        if stored is None or not stored.confirmed or (exact := as_fraction(stored.value)) is None:
            raise _refuse(f"basis.fields.{path}", f"basis field {path} is missing, not confirmed or not a number")
        name = path.replace(".", "_")
        if name not in self.traced:
            self.traced.append(name)
            self.trace.input(name, float(exact), unit=stored.unit, ref=f"{self.basis_id}#/fields/{path}")
        return float(exact), canonical

    def project(self, item: Any, resolved: ResolvedItem) -> None:
        """The effects of one accepted item (spec 0007 4.4.2 per kind)."""
        kind, name = item.kind, item.id
        if kind in ("frame_section", "area_section"):
            section, member = (_FP, "frames") if kind == "frame_section" else (_AP, "areas")
            for target in resolved.targets:
                self.put(name, section, [member, target], "/section", item.section)
        elif kind in ("frame_uniform_load", "area_uniform_load"):
            self.load(item, resolved)
        elif kind == "wall_section":
            thickness, uom = self.number(resolved, "/thickness_mm", item.thickness)
            key = ["area_sections", item.name]
            if self.sections is None or item.name in self.sections:  # no record: as on a held section (4.4.2)
                self.put(name, _SECTIONS, key, "/material", item.material)
                self.put(name, _SECTIONS, key, "/thickness_mm", thickness, uom)
            else:
                row = {"name": item.name, "material": item.material, "kind": str(AreaSectionKind.WALL)}
                self.new(name, _SECTIONS, key, row | {"thickness_mm": thickness})
        elif kind == "load_pattern_add":
            weight, _ = self.number(resolved, "/self_weight_ratio", item.self_weight)
            self.new(
                name,
                _LOADS,
                ["patterns", item.name],
                {"name": item.name, "type": item.type, "self_weight_ratio": weight},
            )
        elif kind == "load_combination_delete":
            self.drop(name, _LOADS, ["combinations", item.name])
        elif kind == "load_combination_set":
            self.combination(item, resolved)
        elif kind == "joint_restraints":
            self.restraints(item, resolved)
        else:
            raise _refuse("check", f"item {name} of kind {kind} has no projection")

    def load(self, item: Any, resolved: ResolvedItem) -> None:
        """A uniform load per target: a `set` of the value on a row the state holds, else an `add` of the row."""
        _, listing, member, field, prop = next(row for row in _LOAD_KINDS if row[0] == item.kind)
        value, uom = self.number(resolved, f"/{prop}", getattr(item, field))
        for target in resolved.targets:
            key = [listing, target, item.pattern, _GRAVITY]
            if tuple(key) in self.rows:
                self.put(item.id, _LOADS, key, f"/{prop}", value, uom)
            else:
                row = {member: target, "pattern": item.pattern, "direction": _GRAVITY, prop: value}
                self.new(item.id, _LOADS, key, row)

    def restraints(self, item: Any, resolved: ResolvedItem) -> None:
        """Restraints per joint: a `set` per property on a row the state holds, else an `add` of the row."""
        flags = {flag: getattr(item, flag) for flag in _FLAGS}
        for target in resolved.targets:
            if target not in self.joints:
                self.new(item.id, _JOINTS, ["joints", target], {"joint": target, **flags})
                continue
            for flag, value in flags.items():
                self.put(item.id, _JOINTS, ["joints", target], f"/{flag}", value)

    def combination(self, item: Any, resolved: ResolvedItem) -> None:
        """A combination: the whole object when new, else its type and one effect per item key (D2)."""
        terms: list[tuple[list[str], dict[str, Any], float, str]] = []
        for number, term in enumerate(item.items):
            scale, uom = self.number(resolved, f"/items/{number}/scale_ratio", term.scale)
            case = term.case
            row = {"case": {"case": case.case, "case_type": case.case_type, "step": case.step}, "scale_ratio": scale}
            terms.append((_member(case.case, case.case_type, case.step), row, scale, uom))
        base, combination = ["combinations", item.name], self.combinations.get(item.name)
        if combination is None:
            self.new(
                item.id, _LOADS, base, {"name": item.name, "type": item.type, "items": [row for _, row, *_ in terms]}
            )
            return
        self.put(item.id, _LOADS, base, "/type", item.type)
        held = {tuple(_member(i.case.case, str(i.case.case_type), i.case.step)) for i in combination.items}
        for member, row, scale, uom in terms:
            key = [*base, "items", *member]
            if tuple(member) in held:
                self.put(item.id, _LOADS, key, "/scale_ratio", scale, uom)
            else:
                self.new(item.id, _LOADS, key, row)
        for left_out in held - {tuple(member) for member, *_ in terms}:
            self.drop(item.id, _LOADS, [*base, "items", *left_out])


def _numbered(effects: list[Effect]) -> list[Effect]:
    """Sort by section, key and pointer; an item with several effects numbers them by position in that order."""
    ordered = sorted(effects, key=lambda effect: (effect.section, effect.key, effect.pointer or "", effect.item_id))
    groups: dict[str, list[Effect]] = {}
    for effect in ordered:
        groups.setdefault(effect.item_id, []).append(effect)
    taken: dict[str, list[Effect]] = {}
    numbered: list[Effect] = []
    for effect in ordered:
        own = taken.setdefault(effect.item_id, [])
        own.append(effect)
        several = len(groups[effect.item_id]) > 1
        numbered.append(effect.model_copy(update={"item_id": f"{effect.item_id}/{len(own)}"}) if several else effect)
    return numbered


@calc(
    id="harness.expected_effects",
    version=1,
    output_kind="harness.expected_effects/1",
    title="Expected effects of the accepted items of a resolved change set",
    method_source="eng-harness spec 0007 §4.4.2; 18 §4 step 6",
    verification="draft",
)
def expected_effects(inp: EffectsInput, meta: InputMeta, trace: TraceBuilder) -> EffectsBody:
    """Project every accepted item (4.4.2), number the effect ids and sort the effects."""
    refs: dict[str, str] = {}
    for name in _REFS:
        if name == "sections" and inp.sections is None:  # optional (spec 0007 4.4.2)
            continue
        if (ref := meta.refs.get(name)) is None:
            raise _refuse(name, "each input must be a record reference")
        refs[name] = ref.result_id
    given = [name for name in _STATE if name in refs]  # the state records supplied
    identities = {(meta.refs[name].model_id, meta.refs[name].model_revision) for name in given}
    model_id, revision = identities.pop()
    if identities or model_id is None or revision is None:
        raise _refuse(given[0], "the state records must be reads of one host model revision")
    if inp.check.status != "PASS":
        raise _refuse("check", "the check must have status PASS")
    resolved = {row.item_id: row for row in inp.check.resolved}
    accepted = sorted(set(inp.approval_items))
    if unknown := [item for item in accepted if item not in resolved]:
        raise _refuse("approval_items", f"accepted items not in the check: {', '.join(unknown)}")
    items = {item.id: item for item in inp.change_set.items}
    for item_id in accepted:
        if "/" in item_id:
            raise _refuse("approval_items", f"item id {item_id} contains a slash (INVALID_ITEM_ID, spec 0007 4.4.1 K3)")
        if item_id not in items:
            raise _refuse("change_set", f"item {item_id} of the check is not in the change set")
    trace.input("items", len(accepted), ref=f"{refs['check']}#/resolved")
    projection = _Projection(inp, refs["basis"], trace)
    for item_id in accepted:
        projection.project(items[item_id], resolved[item_id])
    effects = _numbered(projection.effects)
    formula = "one effect per target and property of each accepted item, sorted by section, key and pointer"
    trace.step("effects", len(effects), formula=formula, source="spec 0007 4.4.2", uses=["items", *projection.traced])
    trace.output("effects")
    return EffectsBody(change_set=f"{refs['change_set']}#/{ANSWER_FIELD}", model_id=model_id, effects=effects)
