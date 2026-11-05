"""Calc 1, model fingerprint `harness.model_fingerprint` v1 (spec 0003 4.6, rules F1 to F6).

Purpose: detect any change in the model state read, deep enough to see a moved column, for the host-state check and
approval bindings. Each section hash is SHA-256 of the canonical JSON of the record's normalized payload in F2 order,
with no rounding; the fingerprint hashes the section hashes by kind. Units: none; values are hashed as read.
Errors: `ContractError` `INVALID_ARGUMENT` (with `field`) for records of different models or revisions, a record
without a host model, or a section given without a record; a `ValidationError` when no section is set.
"""

from enum import StrEnum
from typing import Literal, Protocol, Self

from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.kinds.model import (
    AreaPlacements,
    FramePlacements,
    GridSystem,
    JointRestraints,
    LoadSet,
    Materials,
    Sections,
    Stories,
)
from eng_contract.params import eng_param  # B-146: not in the spec 4.3 list; see the pull request
from pydantic import BaseModel, ConfigDict, model_validator

from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
from eng_harness.calcs._state import SECTIONS, canonical_state, item_count
from eng_harness.kinds.calcs import FpSection

__all__ = ["FingerprintBody", "FingerprintInput", "StateMatch", "model_fingerprint", "same_state"]

METHOD: Literal["harness.fp/1"] = "harness.fp/1"


class FingerprintInput(CalcInput):
    """One optional reference per neutral model kind (records only, never literals); at least one is set."""

    stories: Stories | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.stories/1"}, engineering_quantity=True
    )
    grids: GridSystem | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.grid_system/1"}, engineering_quantity=True
    )
    frames: FramePlacements | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.frame_placements/1"}, engineering_quantity=True
    )
    areas: AreaPlacements | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.area_placements/1"}, engineering_quantity=True
    )
    sections: Sections | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.sections/1"}, engineering_quantity=True
    )
    materials: Materials | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.materials/1"}, engineering_quantity=True
    )
    loads: LoadSet | None = eng_param(None, ref_capable=True, ref_kinds={"model.load_set/1"}, engineering_quantity=True)
    restraints: JointRestraints | None = eng_param(
        None, ref_capable=True, ref_kinds={"model.joint_restraints/1"}, engineering_quantity=True
    )

    @model_validator(mode="after")
    def _one_set(self) -> Self:
        if all(getattr(self, name) is None for name, _ in SECTIONS):
            raise ValueError("at least one section must be set")
        return self


class FingerprintBody(BaseModel):
    """The `harness.model_fingerprint/1` payload without `calc`, `draft` and `trace` (the framework adds them)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: Literal["harness.fp/1"]
    model_id: str
    model_revision: int
    sections: list[FpSection]
    covered: list[str]
    complete: bool
    fingerprint: str


class StateMatch(StrEnum):
    """Outcome of `same_state` (F6)."""

    SAME = "same"
    DIFFERENT = "different"
    UNKNOWN = "unknown"


class Fingerprinted(Protocol):
    """What `same_state` reads: a fingerprint body or a stored `ModelFingerprint`."""

    @property
    def complete(self) -> bool: ...

    @property
    def covered(self) -> list[str]: ...

    @property
    def fingerprint(self) -> str: ...


def same_state(a: Fingerprinted, b: Fingerprinted) -> StateMatch:
    """F6: `unknown` if either is incomplete or their covered kinds differ, `same` if equal, else `different`."""
    if not (a.complete and b.complete) or list(a.covered) != list(b.covered):
        return StateMatch.UNKNOWN
    return StateMatch.SAME if a.fingerprint == b.fingerprint else StateMatch.DIFFERENT


@calc(
    id="harness.model_fingerprint",
    version=1,
    output_kind="harness.model_fingerprint/1",
    title="Fingerprint of a model state read",
    method_source="eng-harness spec 0003 §4.6 (F1 to F6); RFC 8785",
    verification="draft",
)
def model_fingerprint(inp: FingerprintInput, meta: InputMeta, trace: TraceBuilder) -> FingerprintBody:
    """Hash each given section (F1 to F3), check one model and revision (F5) and build the fingerprint (F4)."""
    given = sorted(
        ((kind, name, payload) for name, kind in SECTIONS if (payload := getattr(inp, name)) is not None),
    )
    identity: tuple[str, int] | None = None
    sections: list[FpSection] = []
    for kind, name, payload in given:
        ref = meta.refs.get(name)
        if ref is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "a section must be a record reference", field=name)
        if ref.model_id is None or ref.model_revision is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "the record names no host model", field=name)
        identity = identity or (ref.model_id, ref.model_revision)
        if (ref.model_id, ref.model_revision) != identity:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, "the records belong to different models or revisions (F5)", field=name
            )
        normalized = payload.model_dump(mode="json", by_alias=True, exclude_none=False)  # F1
        digest, items = payload_sha256(canonical_state(kind, normalized)), item_count(normalized)  # F2, F3
        trace.input(name, payload_sha256(normalized), ref=ref.result_id)
        trace.step(
            f"{name}_sha256",
            digest,
            formula=f"SHA-256 of the canonical JSON of {kind} in F2 order ({items} items)",
            source="§4.6 F2, F3",
            uses=[name],
        )
        sections.append(
            FpSection(kind=kind, result_id=ref.result_id, items=items, sha256=digest, complete=ref.complete)
        )
    if identity is None:  # the input model requires one section; kept for the type checker
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "at least one section must be set")
    fingerprint = "fp1:" + payload_sha256({"method": METHOD, "sections": {s.kind: s.sha256 for s in sections}})
    trace.step(
        "fingerprint",
        fingerprint,
        formula="fp1: + payload_sha256({method, sections: {kind: sha256}})",
        source="§4.6 F4",
        uses=[f"{name}_sha256" for _, name, _ in given],
    )
    trace.output("fingerprint")
    return FingerprintBody(
        method=METHOD,
        model_id=identity[0],
        model_revision=identity[1],
        sections=sections,
        covered=[s.kind for s in sections],
        complete=all(s.complete for s in sections),
        fingerprint=fingerprint,
    )
