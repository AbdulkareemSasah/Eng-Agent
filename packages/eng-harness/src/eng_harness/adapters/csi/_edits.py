"""CSI edit kinds: canonical argument models, host-argument builders and the gaps (plan 0002 T12; spec 0002 4.6.2).

Units: canonical in (`thickness_mm`, `w_kN_m`, `q_kPa`); the builders convert to the token the call passes
(`eng_contract.units`). Errors: `NotImplementedGap` (evidence: the gap id) for an edit kind or direction the spec marks
not implemented; nothing is sent then.
"""

# ruff: noqa: N815  # B-131: field names are fixed by the contract's unit suffixes (w_kN_m, q_kPa), as in kinds/model.py

from collections.abc import Callable
from enum import StrEnum
from typing import NoReturn

from eng_contract.kinds.model import CombinationItem, CombinationType, LoadDirection, PatternType
from eng_contract.params import ParamModel, eng_param
from eng_contract.quantity import Quantity
from pydantic import JsonValue

from eng_harness.adapters._args import convert_quantities
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._toolport import Binding, Builder
from eng_harness.errors import NotImplementedGap

GAPS = {  # the edit kinds that have no tool, or whose tool the spec does not map (spec 4.6.2)
    "define_material": "H-G1",
    "define_frame_section": "H-G1",
    "define_area_section": "H-G1",
    "slab_thickness": "H-G1",
    "frame_point_load": "H-G2",
    "change_load_pattern": "OQ-G8",
    "delete_load_pattern": "OQ-G8",
    "seismic_parameters": "OQ-G8",
}
_DIRECTION_GAP = "H-G2"  # a load direction other than gravity
_TYPE_GAP = "H-G3"  # a pattern type or combination type with no code in the tool's schema
_PATTERN = {  # spec 4.6.2: the values the tool's schema names
    PatternType.DEAD: "Dead",
    PatternType.LIVE: "Live",
    PatternType.SEISMIC: "Quake",
    PatternType.WIND: "Wind",
    PatternType.SNOW: "Snow",
    PatternType.OTHER: "Other",
}
_COMBO = {  # the schema's codes
    CombinationType.LINEAR_ADD: 0,
    CombinationType.ENVELOPE: 1,
    CombinationType.ABSOLUTE_ADD: 2,
    CombinationType.SRSS: 3,
}


class ShellType(StrEnum):
    """The shell types of `csi_define_wall_section` (the schema's values)."""

    THIN = "ShellThin"
    THICK = "ShellThick"
    MEMBRANE = "Membrane"


def refuse(edit: str) -> NoReturn:
    """Raise the gap of an edit kind that is not implemented; `KeyError` for a kind the spec does not list."""
    raise NotImplementedGap(f"the edit kind {edit} is not implemented", evidence=(GAPS[edit],))


def _gravity(direction: LoadDirection) -> str:
    if direction is not LoadDirection.GRAVITY:
        raise NotImplementedGap(f"the load direction {direction.value} is not implemented", evidence=(_DIRECTION_GAP,))
    return direction.value


class AssignFrameSectionArgs(ParamModel):
    """`csi_assign_frame_section`: one frame."""

    model: str
    frame: str
    section: str


class AssignAreaSectionArgs(ParamModel):
    """`csi_assign_area_section`: one area."""

    model: str
    area: str
    section: str


class DefineWallSectionArgs(ParamModel):
    """`csi_define_wall_section`: the thickness is an engineering quantity (a reference)."""

    model: str
    name: str
    material: str
    shell_type: ShellType = ShellType.THIN
    thickness_mm: float = eng_param(unit="mm", ref_capable=True, engineering_quantity=True)


class SetFrameLoadDistributedArgs(ParamModel):
    """`csi_set_frame_load_distributed`: replaces the pattern's load on the frame."""

    model: str
    frame: str
    pattern: str
    direction: LoadDirection = LoadDirection.GRAVITY
    w_kN_m: float = eng_param(unit="kN/m", ref_capable=True, engineering_quantity=True)


class SetAreaLoadUniformArgs(ParamModel):
    """`csi_set_area_load_uniform`."""

    model: str
    area: str
    pattern: str
    direction: LoadDirection = LoadDirection.GRAVITY
    q_kPa: float = eng_param(unit="kPa", ref_capable=True, engineering_quantity=True)


class AddLoadPatternArgs(ParamModel):
    """`csi_add_load_pattern`."""

    model: str
    name: str
    type: PatternType
    self_weight_ratio: float = eng_param(unit="1", ref_capable=True, engineering_quantity=True)


class AddLoadComboArgs(ParamModel):
    """`csi_add_load_combo`: the factors are the contract's `scale_ratio` of each item."""

    model: str
    name: str
    type: CombinationType
    items: list[CombinationItem]


class DeleteLoadComboArgs(ParamModel):
    """`csi_delete_load_combo`."""

    model: str
    name: str


class SetPointRestraintArgs(ParamModel):
    """`csi_set_point_restraint`: the six flags, never the presets."""

    model: str
    joint: str
    ux: bool
    uy: bool
    uz: bool
    rx: bool
    ry: bool
    rz: bool


_Args = dict[str, JsonValue]


def _builder[M: ParamModel](cls: type[M], build: Callable[[M, Binding], _Args]) -> Builder:
    def run(model: ParamModel, descriptor: ToolDescriptor, binding: Binding) -> _Args:
        if not isinstance(model, cls):
            raise TypeError(f"{descriptor.name} builds from {cls.__name__}, not {type(model).__name__}")
        return build(model, binding)

    return run


def _converted(model: ParamModel, binding: Binding, field: str) -> float:
    """`field` of `model` in the units of the call's token (`eng_contract.units`)."""
    return convert_quantities(model, binding.units_system or "")[field]


def _pattern(m: AddLoadPatternArgs, b: Binding) -> _Args:
    if m.type not in _PATTERN:
        raise NotImplementedGap(f"the pattern type {m.type.value} is not implemented", evidence=(_TYPE_GAP,))
    ratio = m.self_weight_ratio
    return {
        "name": m.name,
        "type": _PATTERN[m.type],
        "self_weight": ratio.value if isinstance(ratio, Quantity) else ratio,
    }


def _combo(m: AddLoadComboArgs, b: Binding) -> _Args:
    if m.type not in _COMBO:
        raise NotImplementedGap(f"the combination type {m.type.value} is not implemented", evidence=(_TYPE_GAP,))
    parts: list[JsonValue] = [
        {
            "name": i.case.case,
            "factor": i.scale_ratio,
            "kind": "combo" if i.case.case_type.value == "load_combination" else "case",
        }
        for i in m.items
    ]
    return {"name": m.name, "combo_type": _COMBO[m.type], "components": parts}


def _load(m: SetFrameLoadDistributedArgs | SetAreaLoadUniformArgs, b: Binding, name: str, field: str) -> _Args:
    value = _converted(m, b, field)
    return {"name": name, "load_pattern": m.pattern, "value": value, "direction": _gravity(m.direction)}


EDIT_MODELS: dict[str, type[ParamModel]] = {
    model.__name__: model
    for model in (
        AssignFrameSectionArgs, AssignAreaSectionArgs, DefineWallSectionArgs, SetFrameLoadDistributedArgs,
        SetAreaLoadUniformArgs, AddLoadPatternArgs, AddLoadComboArgs, DeleteLoadComboArgs, SetPointRestraintArgs,
    )
}  # fmt: skip
EDIT_BUILDERS: dict[str, Builder] = {  # keyed by the host tool; the framework adds `target`, `units` and `confirm`
    "csi_assign_frame_section": _builder(AssignFrameSectionArgs, lambda m, b: {"name": m.frame, "section": m.section}),
    "csi_assign_area_section": _builder(AssignAreaSectionArgs, lambda m, b: {"name": m.area, "section": m.section}),
    "csi_define_wall_section": _builder(
        DefineWallSectionArgs,
        lambda m, b: {
            "name": m.name,
            "material": m.material,
            "thickness": _converted(m, b, "thickness_mm"),
            "wall_type": "Specified",
            "shell_type": m.shell_type.value,
        },
    ),
    "csi_set_frame_load_distributed": _builder(
        SetFrameLoadDistributedArgs, lambda m, b: _load(m, b, m.frame, "w_kN_m")
    ),
    "csi_set_area_load_uniform": _builder(SetAreaLoadUniformArgs, lambda m, b: _load(m, b, m.area, "q_kPa")),
    "csi_add_load_pattern": _builder(AddLoadPatternArgs, _pattern),
    "csi_add_load_combo": _builder(AddLoadComboArgs, _combo),
    "csi_delete_load_combo": _builder(DeleteLoadComboArgs, lambda m, b: {"name": m.name}),
    "csi_set_point_restraint": _builder(
        SetPointRestraintArgs, lambda m, b: {"name": m.joint, "values": [m.ux, m.uy, m.uz, m.rx, m.ry, m.rz]}
    ),
}
