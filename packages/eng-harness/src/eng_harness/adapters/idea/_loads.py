"""IDEA load map, load plan and structure-preserving loading builder (plan 0014 T7; spec 0014 AC7 to AC10, §4.6, §4.7).

Purpose: keep the shipped load map unconfirmed (IG-2); resolve `$ref` rows of `forces.member_end/1` into the six IDEA
force fields through a confirmed map; preserve every non-force field of the loading read from the host; write a new
file through `idea_native_set_loads` and convert stored read-back to canonical kN / kN.m.
Units: host N and N.m; canonical kN and kN.m via `eng_contract.units.convert` (contract §4.7 exact factors).
Errors: `NotImplementedGap` (IG-2, IG-8); `ContractError` (`INVALID_ARGUMENT`, `REF_*`, `HOST_ERROR`).
"""

from __future__ import annotations

import copy
import tomllib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from eng_contract.envelope import LiteralInput, RefInput
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.issues import ModelIssue
from eng_contract.refs import RecordSource, Ref, RefRule, resolve_ref
from eng_contract.units import convert
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from eng_harness.adapters._errors import parse_error_reply
from eng_harness.adapters.idea import _gaps as gaps
from eng_harness.adapters.idea._errors import IdeaErrorMapper
from eng_harness.adapters.idea._session_ops import new_out_path, require_inside_run
from eng_harness.adapters.idea._tools import build_native_set_loads_args
from eng_harness.kinds.idea import IdeaLoadEffect, IdeaLoads, IdeaLoadSegment
from eng_harness.servers import CallEffect
from eng_harness.servers._session import reply_body

__all__ = [
    "COMPONENT_CSI_FIELDS",
    "FORCE_KEYS",
    "LoadMap",
    "LoadMapComponent",
    "LoadPlan",
    "SetLoadsResult",
    "build_loading",
    "build_loading_from_raw",
    "host_loads_to_canonical",
    "load_map_file",
    "load_shipped_map",
    "require_confirmed_map",
    "set_loads",
]

# Spec 0014 section 4.7: IDEA components and the CSI fields of forces.member_end/1 they take.
COMPONENT_CSI_FIELDS: Mapping[str, str] = {
    "n": "P_kN",
    "qy": "V2_kN",
    "qz": "V3_kN",
    "mx": "T_kNm",
    "my": "M2_kNm",
    "mz": "M3_kNm",
}
FORCE_KEYS: tuple[str, ...] = ("n", "qy", "qz", "mx", "my", "mz")
_FORCE_COMPONENTS = frozenset(FORCE_KEYS)
_MOMENT_KEYS = frozenset({"mx", "my", "mz"})
_MEMBER_END_KIND = "forces.member_end/1"
_MODEL = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class _SegmentKey(BaseModel):
    """One IDEA segment key in the plan's member map (exact match; no tolerance)."""

    model_config = _MODEL

    beam_segment_id: int
    position_host: float


class _LoadEntry(BaseModel):
    """One plan entry: segment key plus a `$ref` to a `forces.member_end/1` row."""

    model_config = _MODEL

    beam_segment_id: int
    position_host: float
    row: Ref


class _LoadEffectPlan(BaseModel):
    """One named effect of the load plan (spec 0014 section 4.7)."""

    model_config = _MODEL

    name: str = Field(min_length=1)
    entries: list[_LoadEntry] = Field(min_length=1)


class LoadPlan(BaseModel):
    """Argument model of the IDEA load step (spec 0014 section 4.7)."""

    model_config = _MODEL

    path: str = Field(min_length=1)
    connection: str = Field(min_length=1)
    member_map: dict[str, list[_SegmentKey]] = Field(min_length=1)
    effects: list[_LoadEffectPlan] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class LoadMapComponent:
    """One IDEA component's CSI field and per-end signs (None = unset)."""

    csi_field: str
    sign_i: int | None
    sign_j: int | None


@dataclass(frozen=True, slots=True)
class LoadMap:
    """Parsed `_load_map.toml` (spec 0014 section 4.7)."""

    status: str
    sign_convention: str
    components: Mapping[str, LoadMapComponent]
    source: str


@dataclass(frozen=True, slots=True)
class SetLoadsResult:
    """Outcome of a successful `set_loads` write (new file path, host reply fields, read-back issues)."""

    out_path: Path
    dropped_zero: tuple[str, ...]
    effects_written: int
    requested: list[dict[str, Any]]
    read_back: list[dict[str, Any]]
    readback_issues: tuple[ModelIssue, ...]


def load_map_file(path: Path) -> LoadMap:
    """Parse a load-map TOML file; `TOMLDecodeError` / `KeyError` / `ValueError` on a bad shape."""
    text = path.read_text(encoding="utf-8")
    return _parse_map(tomllib.loads(text), source=str(path))


def load_shipped_map() -> LoadMap:
    """The packaged `_load_map.toml` (unconfirmed; every sign unset)."""
    resource = files("eng_harness.adapters.idea").joinpath("_load_map.toml")
    return _parse_map(tomllib.loads(resource.read_text(encoding="utf-8")), source="idea/_load_map.toml")


def require_confirmed_map(load_map: LoadMap) -> None:
    """Raise `NotImplementedGap` IG-2 unless `status` is confirmed and every sign is +1 or -1 (AC7)."""
    if load_map.status != "confirmed":
        gaps.raise_gap("IG-2")
    for name, component in load_map.components.items():
        if component.sign_i not in (-1, 1) or component.sign_j not in (-1, 1):
            gaps.raise_gap("IG-2")
        if name not in _FORCE_COMPONENTS:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"unknown load-map component {name}", field="components")


def host_loads_to_canonical(
    *,
    connection: str,
    effects: Sequence[Mapping[str, Any]],
    file_sha256: str,
) -> IdeaLoads:
    """Convert host N / N.m load effects to `harness.idea_loads/1` (canonical kN / kN.m; AC16)."""
    parsed: list[IdeaLoadEffect] = []
    percentage = False
    for effect in effects:
        if effect.get("forcesPercentageOnSegments"):
            percentage = True
        segments = [
            IdeaLoadSegment(
                beam_segment_id=int(seg["beamSegmentId"]),
                position_host=float(seg["position"]),
                N_kN=convert(float(seg.get("n", 0.0)), "N", "kN"),
                Qy_kN=convert(float(seg.get("qy", 0.0)), "N", "kN"),
                Qz_kN=convert(float(seg.get("qz", 0.0)), "N", "kN"),
                Mx_kNm=convert(float(seg.get("mx", 0.0)), "N.m", "kN.m"),
                My_kNm=convert(float(seg.get("my", 0.0)), "N.m", "kN.m"),
                Mz_kNm=convert(float(seg.get("mz", 0.0)), "N.m", "kN.m"),
            )
            for seg in (effect.get("forcesOnSegments") or [])
            if isinstance(seg, Mapping)
        ]
        parsed.append(
            IdeaLoadEffect(
                id=str(effect.get("id") or effect.get("name") or "effect"),
                name=str(effect.get("name") or effect.get("id") or "effect"),
                check_equilibrium=bool(effect.get("checkEquilibrium", effect.get("check_equilibrium", False))),
                segments=segments,
            )
        )
    return IdeaLoads(
        connection=connection,
        effects=parsed,
        percentage_segments_present=percentage,
        file_sha256=file_sha256,
    )


def build_loading_from_raw(
    *,
    current: Sequence[Mapping[str, Any]],
    plan: Mapping[str, Any],
    load_map: LoadMap,
    source: RecordSource,
    current_revision: Callable[[str], int | None],
) -> tuple[list[dict[str, Any]], dict[str, RefInput | LiteralInput]]:
    """Build loading from a raw plan mapping; refuse a literal force row (AC8 `require_refs`)."""
    _refuse_literal_rows(plan)
    try:
        validated = LoadPlan.model_validate(plan)
    except ValidationError as error:
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            "load plan is not valid",
            field="row",
            received=str(error.errors()[:1])[:200],
        ) from error
    return build_loading(
        current=current,
        plan=validated,
        load_map=load_map,
        source=source,
        current_revision=current_revision,
    )


def build_loading(
    *,
    current: Sequence[Mapping[str, Any]],
    plan: LoadPlan,
    load_map: LoadMap,
    source: RecordSource,
    current_revision: Callable[[str], int | None],
) -> tuple[list[dict[str, Any]], dict[str, RefInput | LiteralInput]]:
    """Structure-preserving build (AC9); converts resolved kN / kN.m through the confirmed map to N / N.m."""
    require_confirmed_map(load_map)
    if load_map.sign_convention != "host_local/1":
        raise ContractError(
            ErrorCode.INVALID_ARGUMENT,
            "load map sign_convention must be host_local/1",
            field="sign_convention",
        )
    _refuse_duplicate_effect_names(plan)
    built = [copy.deepcopy(dict(effect)) for effect in current]
    by_name = {str(effect.get("name")): effect for effect in built}
    provenance: dict[str, RefInput | LiteralInput] = {}
    for effect_plan in plan.effects:
        host_effect = by_name.get(effect_plan.name)
        if host_effect is None:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"effect {effect_plan.name!r} is not in the host loading",
                field="name",
                received=effect_plan.name,
            )
        if host_effect.get("forcesPercentageOnSegments"):
            gaps.raise_gap("IG-8")
        segments = host_effect.get("forcesOnSegments")
        if not isinstance(segments, list):
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"effect {effect_plan.name!r} has no forcesOnSegments",
                field="forcesOnSegments",
            )
        for index, entry in enumerate(effect_plan.entries):
            field = f"effects.{effect_plan.name}.entries.{index}.row"
            resolved = resolve_ref(
                entry.row,
                RefRule(kinds=frozenset({_MEMBER_END_KIND}), unit=None, stale_ok=False, field="row"),
                source,
                current_revision,
            )
            provenance[field] = RefInput(ref=resolved.ref)
            row = resolved.value
            if not isinstance(row, Mapping):
                raise ContractError(ErrorCode.INVALID_ARGUMENT, "row reference must point at a row object", field="row")
            member = str(row.get("member") or "")
            allowed = plan.member_map.get(member)
            if allowed is None:
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"member {member!r} is not in the plan member map",
                    field="member_map",
                    received=member,
                )
            key = (entry.beam_segment_id, entry.position_host)
            if not any(item.beam_segment_id == key[0] and item.position_host == key[1] for item in allowed):
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT,
                    f"segment {key} is not mapped for member {member!r}",
                    field="member_map",
                )
            segment = _find_segment(segments, entry.beam_segment_id, entry.position_host)
            end = row.get("end")
            if end not in ("i", "j"):
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT,
                    "member-end row must carry end i or j for the load map sign",
                    field="row",
                )
            _apply_row(segment, row=row, load_map=load_map, end=end)
    return built, provenance


async def set_loads(
    *,
    sessions: Any,
    server: str,
    role: str,
    plan: LoadPlan,
    load_map: LoadMap,
    source: RecordSource,
    current_revision: Callable[[str], int | None],
    run_dir: Path,
    readback_relative_tolerance_ratio: float,
    approved: bool,
    ids: Any | None = None,
) -> SetLoadsResult:
    """Read, build, write a new file, read back (AC10). Raises mapped host errors; never overwrites `path`."""
    from eng_harness.adapters.idea import _checks as checks

    require_confirmed_map(load_map)
    path = require_inside_run(Path(plan.path), run_dir)
    get_result = await sessions.call(
        server,
        role,
        "idea_native_get_loads",
        {"path": str(path), "connection_id": plan.connection},
        CallEffect.READ,
    )
    if get_result.is_error:
        _raise_host(get_result, tool="idea_native_get_loads", effect=CallEffect.READ, ids=ids)
    body = reply_body(get_result)
    if body is None or not isinstance(body.get("loads"), list):
        raise ContractError(
            ErrorCode.HOST_ERROR,
            "idea_native_get_loads returned no loads",
            retryable=False,
            host_code="UNEXPECTED_REPLY",
            host_method="idea_native_get_loads",
        )
    current = body["loads"]
    requested, _provenance = build_loading(
        current=current,
        plan=plan,
        load_map=load_map,
        source=source,
        current_revision=current_revision,
    )
    out_path = new_out_path(path, run_dir)
    args = build_native_set_loads_args(
        path=str(path),
        loads=requested,
        connection_id=plan.connection,
        out_path=str(out_path),
        approved=approved,
    )
    write = await sessions.call(server, role, "idea_native_set_loads", args, CallEffect.WRITE)
    if write.is_error:
        _raise_host(write, tool="idea_native_set_loads", effect=CallEffect.WRITE, ids=ids)
    written = reply_body(write)
    if written is None:
        raise ContractError(
            ErrorCode.HOST_ERROR,
            "idea_native_set_loads returned no body",
            retryable=False,
            host_code="UNEXPECTED_REPLY",
            host_method="idea_native_set_loads",
        )
    if not out_path.exists():
        raise ContractError(
            ErrorCode.HOST_ERROR,
            "idea_native_set_loads did not write out_path",
            retryable=False,
            host_code="idea_error",
            host_method="idea_native_set_loads",
        )
    read = await sessions.call(
        server,
        role,
        "idea_native_get_loads",
        {"path": str(out_path), "connection_id": plan.connection},
        CallEffect.READ,
    )
    if read.is_error:
        _raise_host(read, tool="idea_native_get_loads", effect=CallEffect.READ, ids=ids)
    read_body = reply_body(read)
    if read_body is None or not isinstance(read_body.get("loads"), list):
        raise ContractError(
            ErrorCode.HOST_ERROR,
            "read-back returned no loads",
            retryable=False,
            host_code="UNEXPECTED_REPLY",
            host_method="idea_native_get_loads",
        )
    got = read_body["loads"]
    # Read-back mismatch is an integrity issue for check_model (AC10); the new file is kept.
    readback_issues = checks.compare_loads_readback(
        requested=requested,
        got=got,
        tolerance_ratio=readback_relative_tolerance_ratio,
        connection=plan.connection,
    )
    dropped = tuple(str(name) for name in (written.get("dropped_zero") or []) if name)
    return SetLoadsResult(
        out_path=out_path.resolve(),
        dropped_zero=dropped,
        effects_written=int(written.get("effects_written") or 0),
        requested=requested,
        read_back=got,
        readback_issues=tuple(readback_issues),
    )


def _parse_map(data: Mapping[str, Any], *, source: str) -> LoadMap:
    status = str(data.get("status") or "")
    convention = str(data.get("sign_convention") or "")
    raw_components = data.get("components")
    if not isinstance(raw_components, Mapping):
        raise ValueError(f"{source}: missing components table")
    components: dict[str, LoadMapComponent] = {}
    for name, expected_field in COMPONENT_CSI_FIELDS.items():
        entry = raw_components.get(name)
        if not isinstance(entry, Mapping):
            raise ValueError(f"{source}: missing component {name}")
        field = str(entry.get("csi_field") or "")
        if field != expected_field:
            # Spec 0014 section 4.7 lists the CSI field each component takes; refuse a drifted map.
            raise ValueError(f"{source}: component {name} csi_field must be {expected_field}")
        components[name] = LoadMapComponent(
            csi_field=field,
            sign_i=_optional_sign(entry.get("sign_i")),
            sign_j=_optional_sign(entry.get("sign_j")),
        )
    return LoadMap(status=status, sign_convention=convention, components=components, source=source)


def _optional_sign(value: Any) -> int | None:
    if value is None:
        return None
    sign = int(value)
    if sign not in (-1, 1):
        raise ValueError("load-map sign must be +1, -1 or unset")
    return sign


def _refuse_literal_rows(plan: Mapping[str, Any]) -> None:
    effects = plan.get("effects")
    if not isinstance(effects, list):
        return
    for effect in effects:
        if not isinstance(effect, Mapping):
            continue
        for entry in effect.get("entries") or []:
            if not isinstance(entry, Mapping):
                continue
            row = entry.get("row")
            if isinstance(row, Mapping) and "$ref" not in row:
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT,
                    "row is an engineering quantity and must be given as a reference",
                    field="row",
                    hint="give row as a reference to a forces.member_end/1 row",
                )
            if row is not None and not isinstance(row, Mapping):
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT,
                    "row is an engineering quantity and must be given as a reference",
                    field="row",
                )
            if any(key in entry for key in ("P_kN", "V2_kN", "V3_kN", "T_kNm", "M2_kNm", "M3_kNm")):
                raise ContractError(
                    ErrorCode.INVALID_ARGUMENT,
                    "literal force fields on a load entry are refused",
                    field="row",
                )


def _refuse_duplicate_effect_names(plan: LoadPlan) -> None:
    seen: set[str] = set()
    for effect in plan.effects:
        if effect.name in seen:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"effect name {effect.name!r} appears more than once",
                field="name",
            )
        seen.add(effect.name)


def _find_segment(segments: list[Any], beam_segment_id: int, position_host: float) -> dict[str, Any]:
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        position = segment.get("position")
        if not isinstance(position, (int, float)):
            continue
        if int(segment.get("beamSegmentId", -1)) == beam_segment_id and float(position) == position_host:
            return segment
    raise ContractError(
        ErrorCode.INVALID_ARGUMENT,
        f"segment ({beam_segment_id}, {position_host}) does not exist in the host loading",
        field="beam_segment_id",
        received=f"{beam_segment_id}:{position_host}",
    )


def _apply_row(segment: dict[str, Any], *, row: Mapping[str, Any], load_map: LoadMap, end: str) -> None:
    for component, csi_field in COMPONENT_CSI_FIELDS.items():
        mapped = load_map.components[component]
        raw = row.get(csi_field)
        if not isinstance(raw, (int, float)):
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"row field {csi_field} is missing or not numeric",
                field="row",
            )
        sign = mapped.sign_i if end == "i" else mapped.sign_j
        if sign not in (-1, 1):
            gaps.raise_gap("IG-2")
        src_unit = "kN.m" if component in _MOMENT_KEYS else "kN"
        dst_unit = "N.m" if component in _MOMENT_KEYS else "N"
        segment[component] = float(sign) * convert(float(raw), src_unit, dst_unit)


def _raise_host(result: Any, *, tool: str, effect: CallEffect, ids: Any | None) -> None:
    from eng_contract.ids import FixedClock, SeededIdSource

    dumped = result.model_dump(by_alias=True, mode="json") if hasattr(result, "model_dump") else result
    failure = parse_error_reply(dumped)
    if failure is None:
        raise ContractError(
            ErrorCode.HOST_ERROR,
            f"{tool} failed",
            retryable=False,
            host_code="UNEXPECTED_REPLY",
            host_method=tool,
        )
    mapper_ids = ids if ids is not None else SeededIdSource(b"idea-loads", FixedClock(1_700_000_000_000, 1))
    detail = IdeaErrorMapper(mapper_ids).map(failure, effect=effect, tool=tool, op_id="")
    extra = {
        key: value
        for key in (
            "field",
            "host_code",
            "host_method",
            "op_id",
            "incident_id",
            "hint",
            "precondition",
            "expected",
            "received",
        )
        if (value := getattr(detail, key, None)) is not None
    }
    raise ContractError(detail.code, detail.message, retryable=detail.retryable, **extra)
