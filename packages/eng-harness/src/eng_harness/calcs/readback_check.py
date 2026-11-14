"""Calc 3, read-back check `harness.readback_check` v1 (spec 0003 4.8, rules R0 to R4).

Purpose: after a write, check that every expected effect of the change set reads back from the model (R2) and that
the difference report from the state before the write to the state read after it holds no change that no effect
explains (R1, R3), and give `PASS`, `FAIL` or `NEEDS_ENGINEER` (R4). Expected values come only from the effects and
read values only from the after read set (R0, ب5).
Inputs: `effects` (`harness.expected_effects/1`), the flat read sets `before_<section>` (`stale_ok`) and
`after_<section>` and `basis`, exactly as for the difference report (spec 4.7, 4.13), whose calc this one runs.
Units: values are compared in their canonical units, never converted (D6), within the `compare.*` tolerances (4.4)
that the difference report read and echoed.
Errors: `ContractError` `INVALID_ARGUMENT` (with `field`) for circular inputs (R0), effects given without a record,
and every refusal of the difference report.
"""

from collections.abc import Iterator
from fractions import Fraction
from typing import Any, Literal, cast

from eng_contract.canonical import canonical_json
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.params import eng_param
from eng_contract.verdicts import VerdictStatus
from pydantic import BaseModel, ConfigDict

from eng_harness.calc import InputMeta, TraceBuilder, calc
from eng_harness.calcs._compare import ROW_KEYS, Tolerances, compare_property, row_key, walk_leaves
from eng_harness.calcs._state import SECTIONS
from eng_harness.calcs.model_diff import DiffInput, model_diff
from eng_harness.kinds.calcs import DiffBody, Effect, ExpectedEffects, ReadbackItem, Unexpected

__all__ = ["ReadbackBody", "ReadbackInput", "locate", "read_pointer", "readback_check"]

Result = Literal["match", "mismatch", "missing", "not_read"]
RESULTS: tuple[Result, ...] = ("match", "mismatch", "missing", "not_read")


class ReadbackInput(DiffInput):
    """The read sets and basis of the difference report, and the expected effects of the change set."""

    effects: ExpectedEffects = eng_param(
        ref_capable=True, ref_kinds={"harness.expected_effects/1"}, engineering_quantity=True
    )


class ReadbackBody(BaseModel):
    """The `harness.readback_check/1` payload without `calc`, `draft` and `trace` (the framework adds them)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: VerdictStatus
    items: list[ReadbackItem]
    unexpected: list[Unexpected]
    diff: DiffBody
    complete: bool


def locate(kind: str, node: Any, key: tuple[str, ...], path: tuple[str, ...] = ()) -> Iterator[Any]:
    """The objects of a `kind` payload under a reported D2 key: list name, key members, then any nested list."""
    if not key:
        yield node
        return
    name, *rest = key
    for section, list_path, members in ROW_KEYS:
        if section == kind and list_path == (*path, name):
            for row in node[name]:
                found = row_key(members, row)
                if tuple(rest[: len(found)]) == found:
                    yield from locate(kind, row, tuple(rest[len(found) :]), list_path)


def read_pointer(value: Any, pointer: str) -> Any:
    """The value at a JSON pointer; a member or index that is not there reads as null (D5)."""
    _, *tokens = pointer.split("/")
    for token in tokens:
        part = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _agrees(pointer: str, expected: Any, read: Any, tolerances: Tolerances) -> tuple[bool, float | None, str]:
    """D3 and D4 between an expected and a read value: whether they agree, the tolerance applied and the rule."""
    row, near = compare_property(pointer, expected, read, tolerances)
    return near or canonical_json(expected) == canonical_json(read), row.tolerance, row.rule


def _one(values: list[Any]) -> Any:
    """The value read under a key: one object's value, or the list of them when the key occurs more than once."""
    return values[0] if len(values) == 1 else values


def _item(effect: Effect, after: dict[str, dict[str, Any]], tolerances: Tolerances) -> ReadbackItem:
    """R2: the read-back result of one effect against the after read set."""

    def item(result: Result, read: Any = None, tolerance: float | None = None, rule: str = "R2") -> ReadbackItem:
        return ReadbackItem(
            item_id=effect.item_id, result=result, expected=effect.value, read=read, tolerance=tolerance, rule=rule
        )

    if effect.section not in after:
        return item("not_read")
    found = list(locate(effect.section, after[effect.section], tuple(effect.key)))
    if not found:
        return item("match" if effect.op == "remove" else "missing")
    if effect.op == "remove":
        return item("mismatch", _one(found))
    pointer = effect.pointer or ""  # an `add` is a `set` of the whole object
    reads = [read_pointer(obj, pointer) for obj in found]
    leaves = [leaf for read in reads for leaf in walk_leaves(effect.value, read, pointer)]
    agreed = all(_agrees(*leaf, tolerances)[0] for leaf in leaves)
    _, tolerance, rule = _agrees(pointer, effect.value, reads[0], tolerances)
    if isinstance(effect.value, dict | list):  # compared leaf by leaf (D3 to D5)
        tolerance, rule = None, "R2"
    return item("match" if agreed else "mismatch", _one(reads), tolerance, rule)


def _explained(effects: list[Effect], section: str, key: list[str], pointer: str) -> bool:
    """R3: an effect on the same section and key whose pointer equals or is a prefix of `pointer` (none: the whole)."""
    for effect in effects:
        prefix = effect.pointer or ""
        if (effect.section, effect.key) == (section, key) and (pointer == prefix or pointer.startswith(f"{prefix}/")):
            return True
    return False


def _unexpected(diff: DiffBody, effects: list[Effect]) -> list[Unexpected]:
    """R3: each changed property and each added or removed object that no effect explains (ambiguous keys aside)."""
    rows: list[Unexpected] = []
    for change in diff.changes:
        if change.change == "ambiguous":
            continue
        pointers = [row.pointer for row in change.properties] if change.change == "changed" else [None]
        rows += [
            Unexpected(section=change.section, key=change.key, pointer=pointer)
            for pointer in pointers
            if not _explained(effects, change.section, change.key, pointer or "")
        ]
    return rows


def _side_ids(inp: ReadbackInput, meta: InputMeta, side: str) -> set[str]:
    return {meta.refs[f"{side}_{name}"].result_id for name, _ in SECTIONS if getattr(inp, f"{side}_{name}") is not None}


def _circular(field: str, message: str) -> ContractError:
    hint = "read the after state from the model after the write, and the effects from the change set only"
    return ContractError(ErrorCode.INVALID_ARGUMENT, message, field=field, hint=hint)


def _independent(inp: ReadbackInput, meta: InputMeta, diff: DiffBody) -> None:
    """R0 (ب5): a later revision of the same model after, no record on both sides, effects not derived from after."""
    if diff.after.model_id != diff.before.model_id or diff.after.model_revision <= diff.before.model_revision:
        raise _circular("after", "the after records must be a later revision of the before records' model")
    after = _side_ids(inp, meta, "after")
    if after & _side_ids(inp, meta, "before"):
        raise _circular("after", "an after record is also a before record")
    if (effects := meta.refs.get("effects")) is None:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "the effects must be a record reference", field="effects")
    if after & set(effects.parents):
        raise _circular("effects", "the expected effects have an after record among their parents")


@calc(
    id="harness.readback_check",
    version=1,
    output_kind="harness.readback_check/1",
    title="Read-back check of a write against its expected effects",
    method_source="eng-harness spec 0003 §4.8 (R0 to R4); 18 §4 step 9",
    verification="draft",
)
def readback_check(inp: ReadbackInput, meta: InputMeta, trace: TraceBuilder) -> ReadbackBody:
    """Run the difference report (R1), check independence (R0), each effect (R2), the changes (R3), the status (R4)."""
    diff = cast(DiffBody, model_diff(inp, meta, trace))
    _independent(inp, meta, diff)
    tolerances = {kind: Fraction(tolerance.value) for kind, tolerance in diff.tolerances.items()}
    after = {
        kind: payload.model_dump(mode="json", by_alias=True, exclude_none=False)
        for name, kind in SECTIONS
        if (payload := getattr(inp, f"after_{name}")) is not None
    }
    effects = inp.effects.effects
    items = [_item(effect, after, tolerances) for effect in effects]
    unexpected = _unexpected(diff, effects)
    results = [item.result for item in items]
    counted: list[str] = []
    for result in RESULTS:
        name = f"{result}_items"
        trace.step(name, results.count(result), formula=f"effects read back as {result}", source="§4.8 R2")
        counted.append(name)
    trace.step(
        "unexpected_changes",
        len(unexpected),
        formula="changes of the difference report that no effect explains",
        source="§4.8 R3",
        uses=["identical"],
    )
    if "mismatch" in results or "missing" in results or unexpected:
        status = VerdictStatus.FAIL
    elif "not_read" in results or not diff.complete:
        status = VerdictStatus.NEEDS_ENGINEER
    else:
        status = VerdictStatus.PASS
    trace.step(
        "status",
        status.value,
        formula="FAIL: mismatch, missing or unexpected; else NEEDS_ENGINEER: not read or incomplete; else PASS",
        source="§4.8 R4",
        uses=[*counted, "unexpected_changes", "identical"],
    )
    trace.output("status")
    return ReadbackBody(status=status, items=items, unexpected=unexpected, diff=diff, complete=diff.complete)
