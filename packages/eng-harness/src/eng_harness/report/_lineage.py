"""Release marks and lineage closure (spec 0006 section 4.6.3; ADR-0026 section 3).

Purpose: find the results that came from, or depend on, a tool that is still a project-lane branch.
Units: depth in lineage steps. Errors: `ReportError` when a record in the lineage cannot be read.
"""

from collections.abc import Sequence
from typing import Protocol

from eng_contract.envelope import RefInput
from eng_contract.errors import ContractError
from eng_contract.records import ResultRecord
from eng_contract.refs import parse_ref
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_LINEAGE_DEPTH_LIMIT = 50
"""Default `lineage_depth_limit` (spec 0006 section 4.6.3)."""


class ReportError(Exception):
    """The report or its marks could not be built (spec 0006 section 4.6)."""


class ReleaseMarks(BaseModel):
    """Maps unreleased tool names to the record of their project-lane branch."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    records: dict[str, str]
    lineage_depth_limit: int = Field(default=DEFAULT_LINEAGE_DEPTH_LIMIT, ge=0)


class ResultMark(BaseModel):
    """The mark of one result: the unreleased tools found in its lineage and whether the walk was cut short."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result_id: str
    tools: tuple[str, ...]
    texts: tuple[str, ...]
    lineage_incomplete: bool


class StepLike(Protocol):
    """The part of the journal's step view used here."""

    @property
    def result_ref(self) -> str | None:
        """Reference of the step's result, or None."""
        ...


class StepSource(Protocol):
    """The part of `JournalReader` used here."""

    def steps(self) -> Sequence[StepLike]:
        """One view per step."""
        ...


class RecordStore(Protocol):
    """The part of `ResultStore` used here."""

    def get(self, result_id: str) -> ResultRecord:
        """The record, or `ContractError`."""
        ...


def _references(record: ResultRecord) -> list[str]:
    """Parent ids and the result ids of the provenance inputs, in a stable order."""
    ids = list(record.parents)
    for name in sorted(record.producer.inputs):
        item = record.producer.inputs[name]
        if isinstance(item, RefInput):
            ids.append(parse_ref(item.ref)[0])
    return ids


def _mark_one(root: str, store: RecordStore, marks: ReleaseMarks, cache: dict[str, ResultRecord]) -> ResultMark | None:
    tools: set[str] = set()
    incomplete = False
    seen = {root}
    frontier = [root]
    depth = 0
    while frontier:
        following: list[str] = []
        for result_id in frontier:
            record = cache.get(result_id)
            if record is None:
                try:
                    record = store.get(result_id)
                except ContractError as exc:
                    raise ReportError(f"lineage record {result_id} cannot be read: {exc}") from exc
                cache[result_id] = record
            if record.producer.tool in marks.records:
                tools.add(record.producer.tool)
            for ref in _references(record):
                if ref not in seen:
                    seen.add(ref)
                    following.append(ref)
        if following and depth >= marks.lineage_depth_limit:
            incomplete = True
            break
        frontier = following
        depth += 1
    if not tools and not incomplete:
        return None
    ordered = tuple(sorted(tools))
    texts = tuple(f"Depends on unreleased tool `{t}` (record `{marks.records[t]}`)" for t in ordered)
    return ResultMark(result_id=root, tools=ordered, texts=texts, lineage_incomplete=incomplete)


def unreleased_dependencies(reader: StepSource, store: RecordStore, marks: ReleaseMarks) -> dict[str, ResultMark]:
    """Marked results by id: producer in `marks`, or such a result among the ancestors (parents, provenance inputs).

    The walk is breadth-first to `lineage_depth_limit`; a result with unexplored lineage beyond it is marked and
    flagged `lineage_incomplete`. With no marks nothing is read and the result is empty.

    Raises:
        ReportError: a record in a lineage cannot be read.
    """
    if not marks.records:
        return {}
    cache: dict[str, ResultRecord] = {}
    found: dict[str, ResultMark] = {}
    for step in reader.steps():
        if step.result_ref is None:
            continue
        root = parse_ref(step.result_ref)[0]
        if root in found:
            continue
        mark = _mark_one(root, store, marks, cache)
        if mark is not None:
            found[root] = mark
    return found
