"""The block `design_isolated_footing` (spec 0010 section 4.6; plan 0010 T8).

Purpose: size open footings through plan size, layout, the six code-pack checks, status, decide_many,
engineer dimensions and resize, closing footings that need the engineer. Every engineering value is a calc
output or a reference; the `for` over footings builds argument lists only.
Units: millimetres and the units of the referenced reaction and basis fields.
Errors: the step errors of the ctx calls reach the engine unchanged.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from eng_contract.quantity import Quantity
from eng_contract.refs import Ref
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict

from eng_harness.block import block
from eng_harness.ctx import Answered, DecisionRequest
from eng_harness.rules import footing as footing_rules
from eng_harness.workflows.isolated_footing._points import (
    FIX_STRATEGY_POLICY,
    FootingAction,
    FootingFailureState,
)

__all__ = [
    "CHECK_BASE_IDS",
    "Closure",
    "DesignIsolatedFootingInput",
    "DesignIsolatedFootingOutput",
    "FootingDimensions",
    "ResizeKind",
    "design_isolated_footing",
]

_M = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

CHECK_BASE_IDS = (
    "aci318_14.13_3_1_1.bearing_pressure_service",
    "aci318_14.22_5_5_1.one_way_shear",
    "aci318_14.22_6_5_2.punching_shear",
    "aci318_14.13_2_7_1.flexure_at_column_face",
    "aci318_14.8_6_1_1.min_flexural_reinforcement",
    "aci318_14.25_4_2_3.development_length_bottom_bars",
)
"""The six ACI 318-14 footing base ids (spec 0010 4.3); `check_ids` maps each to the pack id of the run."""

_FAMILIES = ("bearing", "one_way_shear", "punching", "flexure", "min_steel", "development")
_FORCE = ("FX_kN", "FY_kN", "FZ_kN", "MX_kNm", "MY_kNm")
_NEEDS = "NEEDS_ENGINEER"
_ATTEMPTS = "ATTEMPTS_EXHAUSTED"
_COMBINE = "COMBINE_REQUESTED"
_LIMIT = "LIMIT_REACHED"
_WIDTH = "WIDTH_TOO_SMALL"


class ResizeKind(StrEnum):
    """Resize actions of `harness.footing_resize` (spec 0010 4.4.4); local copy so block code imports no calc."""

    ENLARGE_PLAN = "enlarge_plan"
    INCREASE_DEPTH = "increase_depth"
    REDUCE_BAR_SPACING = "reduce_bar_spacing"
    ENGINEER_SET = "engineer_set"
    NONE = "none"


class FootingDimensions(BaseModel):
    """Engineer square plan size, depth and spacing (spec 0010 4.6 step 6, Q17); no separate Lx and Ly."""

    model_config = _M

    L: Quantity
    h: Quantity
    s: Quantity


class DesignIsolatedFootingInput(BaseModel):
    """References the block reads (spec 0010 4.6).

    `unused_engineer_dims` is a `basis.engineer_input/1` whose fields `L`, `h` and `s` are Quantity values
    (same shape as `ctx.ask(FootingDimensions)`). `harness.footing_resize` requires the three engineer Quantity
    references on every call (spec 0010 4.4.4); they are used only for `engineer_set`, and otherwise carried as
    unused placeholders from this answer (T9 supplies them from an early ask or defaults).
    """

    model_config = _M

    subjects: Ref
    reactions: Ref
    service_cases: Ref
    factored_cases: Ref
    check_ids: dict[str, str]
    unused_engineer_dims: Ref


class Closure(BaseModel):
    """One footing closed during the block, with the reason of section 4.6."""

    model_config = _M

    id: str
    status: str
    reason: str | None


class DesignIsolatedFootingOutput(BaseModel):
    """The design, status, closures, decisions, verdict sets and round count (spec 0010 4.6)."""

    model_config = _M

    design: Ref
    status: Ref
    closures: tuple[Closure, ...]
    decisions: tuple[str, ...]
    verdict_sets: tuple[Ref, ...]
    rounds: int


def _ref(value: object) -> Ref:
    return Ref.model_validate({"$ref": value})


async def _data(ctx: Any, ref: Ref, pointer: str) -> Any:
    """The decoded value of a stored result at `pointer` (`ReadResult.data`, engine spec 4.3.2)."""
    return (await ctx.read(ref, pointer)).data


def _rid(ref: Ref) -> str:
    """The result id of a top-level or fragment reference (block code may not import `parse_ref`)."""
    base, _sep, _rest = ref.ref.partition("#")
    return base


def _basis_qty(ctx: Any, path: str) -> Ref:
    return _ref(f"{_rid(ctx.basis.record_ref())}#/fields/{path}/value")


def _state_from_row(row: Any) -> FootingFailureState:
    """Map `harness.footing_status` state (`engineer_sized`) to the point state (`hand_sized`, B-398)."""
    state = row["state"]
    return FootingFailureState(
        bearing=VerdictStatus(state["bearing"]),
        one_way_shear=VerdictStatus(state["one_way_shear"]),
        punching=VerdictStatus(state["punching"]),
        flexure=VerdictStatus(state["flexure"]),
        min_steel=VerdictStatus(state["min_steel"]),
        development=VerdictStatus(state["development"]),
        plan_at_max=bool(state["plan_at_max"]),
        depth_at_max=bool(state["depth_at_max"]),
        spacing_at_min=bool(state["spacing_at_min"]),
        hand_sized=bool(state["engineer_sized"]),
    )


def _action_to_resize(choice: FootingAction) -> str:
    """Map a fix-strategy option to a resize action string (no `.value` read; block-module rule)."""
    if choice is FootingAction.ENLARGE_PLAN:
        return "enlarge_plan"
    if choice is FootingAction.INCREASE_DEPTH:
        return "increase_depth"
    if choice is FootingAction.REDUCE_BAR_SPACING:
        return "reduce_bar_spacing"
    return "none"


def _row_index(rows: list[Any], joint: str, case: str) -> int | None:
    for index, row in enumerate(rows):
        case_name = row["case"]["case"] if isinstance(row["case"], dict) else row["case"]
        if row["joint"] == joint and case_name == case:
            return index
    return None


def _list_index(items: list[Any], footing_id: str) -> int | None:
    for index, item in enumerate(items):
        if item["id"] == footing_id:
            return index
    return None


def _force_refs(reactions: Ref, index: int) -> dict[str, Ref]:
    base = _rid(reactions)
    return {name: _ref(f"{base}#/rows/{index}/{name}") for name in _FORCE}


def _design_refs(design: Ref, index: int, names: tuple[str, ...]) -> dict[str, Ref]:
    base = _rid(design)
    return {name: _ref(f"{base}#/footings/{index}/{name}") for name in names}


def _subject_refs(subjects: Ref, index: int) -> dict[str, Ref]:
    base = _rid(subjects)
    return {
        "cx_mm": _ref(f"{base}#/subjects/{index}/cx_mm"),
        "cy_mm": _ref(f"{base}#/subjects/{index}/cy_mm"),
    }


async def _cases_value_ref(ctx: Any, ref: Ref) -> Ref:
    """Fragment that points at the case-name list (plan_size wants an array, not the engineer-input object)."""
    kind = (await ctx.read(ref, "")).kind
    if kind == "basis.engineer_input/1":
        fields = await _data(ctx, ref, "/fields")
        for key in ("service_cases", "factored_cases", "cases"):
            if key in fields:
                return _ref(f"{_rid(ref)}#/fields/{key}/value")
    return ref


async def _cases(ctx: Any, ref: Ref) -> list[str]:
    """Read a list of case names from a stored list or an engineer-input fields payload."""
    kind = (await ctx.read(ref, "")).kind
    if kind == "basis.engineer_input/1":
        fields = await _data(ctx, ref, "/fields")
        for key in ("service_cases", "factored_cases", "cases"):
            if key in fields:
                return [str(item) for item in fields[key]["value"]]
    payload = await _data(ctx, ref, "")
    if isinstance(payload, list):
        return [str(item) for item in payload]
    value = await _data(ctx, ref, "/value")
    return [str(item) for item in value]


async def _close_plan_needs(ctx: Any, dims: Any, open_ids: list[str], closures: list[Closure]) -> list[str]:
    kept: list[str] = []
    footings = await _data(ctx, dims.ref, "/footings")
    for row in footings:
        if row["id"] not in open_ids:
            continue
        if row["status"] == _NEEDS:
            closures.append(Closure(id=row["id"], status=_NEEDS, reason=row["reason"]))
        else:
            kept.append(row["id"])
    return kept


async def _close_width(ctx: Any, design: Any, open_ids: list[str], closures: list[Closure]) -> list[str]:
    kept: list[str] = []
    footings = await _data(ctx, design.ref, "/footings")
    for row in footings:
        if row["id"] not in open_ids:
            continue
        if row["status"] == _NEEDS and row["reason"] == _WIDTH:
            closures.append(Closure(id=row["id"], status=_NEEDS, reason=_WIDTH))
        else:
            kept.append(row["id"])
    return kept


def _bearing_inputs(
    ctx: Any,
    *,
    reactions: Ref,
    design: Ref,
    row_i: int,
    design_i: int,
) -> dict[str, Ref]:
    inputs = _force_refs(reactions, row_i)
    inputs.update(_design_refs(design, design_i, ("Lx_mm", "Ly_mm", "reaction_height_mm", "h_mm")))
    inputs["soil_depth_mm"] = _basis_qty(ctx, "foundation.soil_depth_above_footing_mm")
    inputs["gamma_c_kN_m3"] = _basis_qty(ctx, "materials.concrete_unit_weight_kN_m3")
    inputs["gamma_s_kN_m3"] = _basis_qty(ctx, "foundation.soil_unit_weight_kN_m3")
    inputs["surcharge_kPa"] = _basis_qty(ctx, "foundation.surcharge_kPa")
    inputs["q_allow_kPa"] = _basis_qty(ctx, "foundation.allowable_bearing_pressure_kPa")
    inputs["allowable_kind"] = _basis_qty(ctx, "foundation.allowable_bearing_kind")
    inputs["ratio_limit"] = _basis_qty(ctx, "limits.ratio_limit_ratio")
    return inputs


def _strength_common(
    ctx: Any,
    *,
    reactions: Ref,
    design: Ref,
    subjects: Ref,
    row_i: int,
    design_i: int,
    subject_i: int,
) -> dict[str, Any]:
    """Shared strength-check inputs. `concrete_class` is a literal: the ACI check fields are not ref_capable."""
    inputs: dict[str, Any] = _force_refs(reactions, row_i)
    inputs.update(_design_refs(design, design_i, ("Lx_mm", "Ly_mm", "reaction_height_mm")))
    inputs.update(_subject_refs(subjects, subject_i))
    inputs["ratio_limit"] = _basis_qty(ctx, "limits.ratio_limit_ratio")
    inputs["fc_MPa"] = _basis_qty(ctx, "materials.concrete_fc_MPa")
    return inputs


async def _batch_checks(
    ctx: Any,
    *,
    open_ids: list[str],
    subjects_ref: Ref,
    reactions: Ref,
    design: Ref,
    service_cases: list[str],
    factored_cases: list[str],
    check_ids: dict[str, str],
) -> dict[str, Ref]:
    """Six code-pack batches (spec 0010 4.6 step 2.2); returns family name to verdict-set ref."""
    subjects = list(await _data(ctx, subjects_ref, "/subjects"))
    design_rows = list(await _data(ctx, design, "/footings"))
    rows = list(await _data(ctx, reactions, "/rows"))
    joint_by_id = {s["id"]: s["joint"] for s in subjects if s["id"] in open_ids}
    # Enum basis fields: ACI checks declare ConcreteClass / Coating without ref_capable (pack inputs).
    basis_root = _ref(_rid(ctx.basis.record_ref()))
    concrete_class = await _data(ctx, basis_root, "/fields/materials.concrete_class/value")
    coating = await _data(ctx, basis_root, "/fields/materials.rebar_coating/value")

    bearing_items: list[dict[str, Any]] = []
    one_way_items: list[dict[str, Any]] = []
    punch_items: list[dict[str, Any]] = []
    flexure_items: list[dict[str, Any]] = []
    min_steel_items: list[dict[str, Any]] = []
    development_items: list[dict[str, Any]] = []

    for footing_id in open_ids:
        subject_i = _list_index(subjects, footing_id)
        design_i = _list_index(design_rows, footing_id)
        if subject_i is None or design_i is None:
            continue
        joint = joint_by_id[footing_id]
        subject = {"kind": "footing", "id": footing_id}

        for case in service_cases:
            row_i = _row_index(rows, joint, case)
            if row_i is None:
                continue
            bearing_items.append(
                {
                    "subject": subject,
                    "inputs": _bearing_inputs(ctx, reactions=reactions, design=design, row_i=row_i, design_i=design_i),
                }
            )

        for case in factored_cases:
            row_i = _row_index(rows, joint, case)
            if row_i is None:
                continue
            common = _strength_common(
                ctx,
                reactions=reactions,
                design=design,
                subjects=subjects_ref,
                row_i=row_i,
                design_i=design_i,
                subject_i=subject_i,
            )
            one_way = dict(common)
            one_way.update(_design_refs(design, design_i, ("d_x_mm", "d_y_mm")))
            one_way["concrete_class"] = concrete_class
            one_way_items.append({"subject": subject, "inputs": one_way})

            punch = dict(common)
            punch.update(_design_refs(design, design_i, ("d_mm",)))
            punch["concrete_class"] = concrete_class
            punch_items.append({"subject": subject, "inputs": punch})

            flex = dict(common)
            flex.update(_design_refs(design, design_i, ("d_x_mm", "d_y_mm", "As_x_mm2", "As_y_mm2")))
            flex["fy_MPa"] = _basis_qty(ctx, "materials.rebar_fy_MPa")
            flexure_items.append({"subject": subject, "inputs": flex})

        min_inputs: dict[str, Any] = _design_refs(design, design_i, ("Lx_mm", "Ly_mm", "h_mm", "As_x_mm2", "As_y_mm2"))
        min_inputs["fy_MPa"] = _basis_qty(ctx, "materials.rebar_fy_MPa")
        min_inputs["ratio_limit"] = _basis_qty(ctx, "limits.ratio_limit_ratio")
        min_steel_items.append({"subject": subject, "inputs": min_inputs})

        dev: dict[str, Any] = _subject_refs(subjects_ref, subject_i)
        dev.update(_design_refs(design, design_i, ("Lx_mm", "Ly_mm", "s_x_mm", "s_y_mm", "end_cover_mm")))
        design_base = _rid(design)
        # One bar diameter and cover each way (layout L4).
        dev["db_x_mm"] = _ref(f"{design_base}#/footings/{design_i}/db_mm")
        dev["db_y_mm"] = _ref(f"{design_base}#/footings/{design_i}/db_mm")
        dev["cover_x_mm"] = _ref(f"{design_base}#/footings/{design_i}/cover_mm")
        dev["cover_y_mm"] = _ref(f"{design_base}#/footings/{design_i}/cover_mm")
        dev["fc_MPa"] = _basis_qty(ctx, "materials.concrete_fc_MPa")
        dev["fy_MPa"] = _basis_qty(ctx, "materials.rebar_fy_MPa")
        dev["concrete_class"] = concrete_class
        dev["coating"] = coating
        dev["ratio_limit"] = _basis_qty(ctx, "limits.ratio_limit_ratio")
        development_items.append({"subject": subject, "inputs": dev})

    mapping = {
        "bearing": (CHECK_BASE_IDS[0], bearing_items),
        "one_way_shear": (CHECK_BASE_IDS[1], one_way_items),
        "punching": (CHECK_BASE_IDS[2], punch_items),
        "flexure": (CHECK_BASE_IDS[3], flexure_items),
        "min_steel": (CHECK_BASE_IDS[4], min_steel_items),
        "development": (CHECK_BASE_IDS[5], development_items),
    }
    out: dict[str, Ref] = {}
    for family, (base_id, items) in mapping.items():
        result = await ctx.calc(check_ids[base_id], {"items": items})
        out[family] = result.ref
    return out


async def _resize(
    ctx: Any,
    dims: Any,
    actions: dict[str, str],
    plan: Ref,
    depth: Ref,
    spacing: Ref,
    *,
    keep: list[str] | None = None,
) -> Any:
    """Resize with an action for every footing still in `dims` (spec 0010 §4.4.4); closed ids get `none`.

    When `keep` is set, only those footing ids are retained in the next dims (closed rows dropped for
    open-only layout/status rounds, spec 0010 §4.6 steps 1-2.3).
    """
    covered = dict(actions)
    for row in await _data(ctx, dims.ref, "/footings"):
        if keep is not None and row["id"] not in keep:
            continue
        if row["id"] not in covered:
            covered[row["id"]] = "none"
    args: dict[str, Any] = {
        "dims": dims.ref,
        "actions": covered,
        "engineer_plan": plan,
        "engineer_depth": depth,
        "engineer_spacing": spacing,
        "basis": ctx.basis.record_ref(),
    }
    if keep is not None:
        args["keep"] = list(keep)
    return await ctx.calc("harness.footing_resize", args)


async def _keep_open_dims(ctx: Any, dims: Any, open_ids: list[str], plan: Ref, depth: Ref, spacing: Ref) -> Any:
    """Drop closed footings from trial dims so the next layout/status see only open ids."""
    present = [row["id"] for row in await _data(ctx, dims.ref, "/footings")]
    if len(present) == len(open_ids) and all(item in open_ids for item in present):
        return dims
    return await _resize(ctx, dims, {}, plan, depth, spacing, keep=list(open_ids))


async def _gap_reason(ctx: Any, bearing: Ref, footing_id: str) -> str | None:
    """Copy the NEEDS_ENGINEER gap/precondition id from the bearing verdict set (AC19 / Q18; BP FULL_CONTACT, G-1)."""
    payload = await _data(ctx, bearing, "")
    verdicts = list(payload.get("verdicts") or [])
    traces = list(payload.get("traces") or [])
    for verdict in verdicts:
        subject = verdict.get("subject") or {}
        if subject.get("id") != footing_id:
            continue
        if verdict.get("status") != _NEEDS:
            continue
        messages: list[str] = []
        ref = verdict.get("trace_ref")
        if isinstance(ref, str) and ref.startswith("#/traces/"):
            index = int(ref.rsplit("/", 1)[1])
            if index < len(traces):
                messages = list(traces[index].get("messages") or [])
        for message in messages:
            if message.startswith("FULL_CONTACT"):
                return "FULL_CONTACT"
            if message.startswith("G-1"):
                return "G-1"
            if "G-1" in message:
                return "G-1"
            if "FULL_CONTACT" in message:
                return "FULL_CONTACT"
    return None


async def _apply_limit_closures(ctx: Any, dims: Any, open_ids: list[str], closures: list[Closure]) -> list[str]:
    resized = list(await _data(ctx, dims.ref, "/footings"))
    kept: list[str] = []
    for row in resized:
        if row["id"] not in open_ids:
            continue
        if row["status"] == _LIMIT:
            closures.append(Closure(id=row["id"], status=_NEEDS, reason=_LIMIT))
        else:
            kept.append(row["id"])
    return kept


@block(name="design_isolated_footing", version=1)
async def design_isolated_footing(ctx: Any, inp: DesignIsolatedFootingInput) -> DesignIsolatedFootingOutput:
    """Rounds of layout, batched checks, decisions and resize (spec 0010 4.6)."""
    closures: list[Closure] = []
    decisions: list[str] = []
    verdict_sets: list[Ref] = []
    # 1-based round count without arithmetic in block source (block-module rule forbids `+`).
    round_marks: list[None] = []

    service_cases_ref = await _cases_value_ref(ctx, inp.service_cases)
    dims = await ctx.calc(
        "harness.footing_plan_size",
        {
            "subjects": inp.subjects,
            "reactions": inp.reactions,
            "service_cases": service_cases_ref,
            "basis": ctx.basis.record_ref(),
        },
    )
    open_ids = [row["id"] for row in await _data(ctx, dims.ref, "/footings")]
    open_ids = await _close_plan_needs(ctx, dims, open_ids, closures)

    design: Any = dims
    status: Any = dims
    last_design = dims.ref
    last_status = dims.ref

    async for attempt in ctx.attempts(ctx.basis.count("attempts.footing_rounds")):
        if not open_ids:
            break
        round_marks.append(None)
        design = await ctx.calc(
            "harness.footing_layout",
            {"dims": dims.ref, "subjects": inp.subjects, "basis": ctx.basis.record_ref()},
        )
        last_design = design.ref
        open_ids = await _close_width(ctx, design, open_ids, closures)
        if not open_ids:
            break

        # Spec 0010 §4.6 steps 1-2.3: layout/status see only open footings; closed sizes stay in closures.
        unused = (
            _ref(f"{_rid(inp.unused_engineer_dims)}#/fields/L/value"),
            _ref(f"{_rid(inp.unused_engineer_dims)}#/fields/h/value"),
            _ref(f"{_rid(inp.unused_engineer_dims)}#/fields/s/value"),
        )
        dims = await _keep_open_dims(ctx, dims, open_ids, *unused)
        design = await ctx.calc(
            "harness.footing_layout",
            {"dims": dims.ref, "subjects": inp.subjects, "basis": ctx.basis.record_ref()},
        )
        last_design = design.ref

        service = await _cases(ctx, inp.service_cases)
        factored = await _cases(ctx, inp.factored_cases)
        families = await _batch_checks(
            ctx,
            open_ids=open_ids,
            subjects_ref=inp.subjects,
            reactions=inp.reactions,
            design=design.ref,
            service_cases=service,
            factored_cases=factored,
            check_ids=inp.check_ids,
        )
        for family in _FAMILIES:
            verdict_sets.append(families[family])

        status = await ctx.calc(
            "harness.footing_status",
            {
                "subjects": inp.subjects,
                "design": design.ref,
                "bearing": families["bearing"],
                "one_way_shear": families["one_way_shear"],
                "punching": families["punching"],
                "flexure": families["flexure"],
                "min_steel": families["min_steel"],
                "development": families["development"],
            },
        )
        last_status = status.ref
        status_rows = list(await _data(ctx, status.ref, "/footings"))

        failing: list[Any] = []
        still: list[str] = []
        for row in status_rows:
            if row["id"] not in open_ids:
                continue
            if row["closure"] == "passed":
                closures.append(Closure(id=row["id"], status="PASSED", reason=None))
            elif row["closure"] == "needs_engineer":
                reason = await _gap_reason(ctx, families["bearing"], row["id"])
                closures.append(Closure(id=row["id"], status=_NEEDS, reason=reason))
            else:
                failing.append(row)
                still.append(row["id"])
        open_ids = still
        if not failing:
            break
        if attempt.is_last:
            for row in failing:
                closures.append(Closure(id=row["id"], status=_NEEDS, reason=_ATTEMPTS))
            open_ids = []
            break

        requests = [
            DecisionRequest(
                question="footing_fix_strategy",
                options=FootingAction,
                state=_state_from_row(row),
                rules=footing_rules.FOOTING_RULES,
                policy=FIX_STRATEGY_POLICY,
            )
            for row in failing
        ]
        decided = await ctx.decide_many(requests)
        choices = {row["id"]: decision.choice for row, decision in zip(failing, decided, strict=True)}
        for row, decision in zip(failing, decided, strict=True):
            decisions.append(f"{row['id']}:{decision.choice}:{decision.decided_by}")

        auto_actions: dict[str, str] = {}
        ask_ids: list[str] = []
        for footing_id, choice in choices.items():
            if choice is FootingAction.COMBINE_WITH_NEIGHBOR:
                closures.append(Closure(id=footing_id, status=_NEEDS, reason=_COMBINE))
                open_ids = [item for item in open_ids if item != footing_id]
            elif choice is FootingAction.ASK_ENGINEER:
                ask_ids.append(footing_id)
            else:
                auto_actions[footing_id] = _action_to_resize(choice)

        for footing_id in open_ids:
            if footing_id not in auto_actions and footing_id not in ask_ids:
                auto_actions[footing_id] = "none"

        if auto_actions:
            dims = await _resize(ctx, dims, auto_actions, *unused)
            open_ids = await _apply_limit_closures(ctx, dims, open_ids, closures)

        for footing_id in ask_ids:
            if footing_id not in open_ids:
                continue
            asked: Answered[FootingDimensions] = await ctx.ask(
                FootingDimensions, title=f"Dimensions for footing {footing_id}"
            )
            actions = {footing_id: "engineer_set"}
            dims = await _resize(
                ctx,
                dims,
                actions,
                asked.field_ref("L"),
                asked.field_ref("h"),
                asked.field_ref("s"),
            )
            open_ids = await _apply_limit_closures(ctx, dims, open_ids, closures)

        dims = await _keep_open_dims(ctx, dims, open_ids, *unused)

    return DesignIsolatedFootingOutput(
        design=last_design,
        status=last_status,
        closures=tuple(closures),
        decisions=tuple(decisions),
        verdict_sets=tuple(verdict_sets),
        rounds=len(round_marks),
    )
