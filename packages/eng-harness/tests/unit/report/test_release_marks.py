"""Release marks and lineage closure (spec 0006 section 4.6.3; AC54)."""

from collections.abc import Sequence
from dataclasses import dataclass

import pytest
from eng_contract.envelope import LiteralInput, Provenance, RefInput
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.records import ResultRecord

from eng_harness.report import ReleaseMarks, ReportError, unreleased_dependencies

TOOL_A = "sasaah/tool_a"
TOOL_B = "sasaah/tool_b"
OTHER = "sasaah/other"


def rid(n: int) -> str:
    return f"res_0{n:025d}"


def record(n: int, tool: str, parents: Sequence[int] = (), inputs: Sequence[int] = ()) -> ResultRecord:
    provenance = Provenance(
        tool=tool,
        tool_version="1",
        inputs={f"/in{i}": RefInput(ref=rid(i)) for i in inputs} | {"/lit": LiteralInput(literal=1)},
        started_at="2026-01-01T00:00:00.000Z",
        duration_ms=1,
    )
    return ResultRecord(
        contract="eng-contract/1",
        result_id=rid(n),
        kind="demo.kind/1",
        created_at="2026-01-01T00:00:00.000Z",
        units="canonical/1",
        complete=True,
        producer=provenance,
        parents=[rid(p) for p in parents],
        payload_sha256="0" * 64,
        payload={},
    )


@dataclass(frozen=True)
class FakeStep:
    result_ref: str | None


class FakeReader:
    def __init__(self, refs: Sequence[str | None]) -> None:
        self._steps = [FakeStep(ref) for ref in refs]

    def steps(self) -> Sequence[FakeStep]:
        return self._steps


class FakeStore:
    def __init__(self, records: Sequence[ResultRecord]) -> None:
        self._by_id = {r.result_id: r for r in records}

    def get(self, result_id: str) -> ResultRecord:
        try:
            return self._by_id[result_id]
        except KeyError:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "unknown result", received=result_id) from None


MARKS = ReleaseMarks(records={TOOL_A: "lane/b-900"})


def test_marks_everywhere() -> None:
    store = FakeStore(
        [
            record(1, TOOL_A),
            record(2, OTHER, parents=[1]),
            record(3, OTHER, inputs=[2]),
            record(4, OTHER),
            record(5, OTHER, parents=[4]),
        ]
    )
    reader = FakeReader([rid(i) for i in (1, 2, 3, 4, 5)])
    marked = unreleased_dependencies(reader, store, MARKS)
    assert set(marked) == {rid(1), rid(2), rid(3)}
    for mark in marked.values():
        assert mark.tools == (TOOL_A,)
        assert mark.texts == ("Depends on unreleased tool `sasaah/tool_a` (record `lane/b-900`)",)
        assert not mark.lineage_incomplete


def test_two_tools_listed_sorted() -> None:
    store = FakeStore([record(1, TOOL_B), record(2, TOOL_A), record(3, OTHER, parents=[1, 2])])
    marks = ReleaseMarks(records={TOOL_A: "r-a", TOOL_B: "r-b"})
    marked = unreleased_dependencies(FakeReader([rid(3)]), store, marks)
    assert marked[rid(3)].tools == (TOOL_A, TOOL_B)
    assert len(marked[rid(3)].texts) == 2


def test_ref_with_pointer_and_steps_without_result() -> None:
    store = FakeStore([record(1, TOOL_A)])
    marked = unreleased_dependencies(FakeReader([None, rid(1) + "#/x"]), store, MARKS)
    assert set(marked) == {rid(1)}


def test_no_marks_no_result() -> None:
    store = FakeStore([record(1, TOOL_A)])
    assert unreleased_dependencies(FakeReader([rid(1)]), store, ReleaseMarks(records={})) == {}


def test_depth_limit_marks_and_flags() -> None:
    chain = [record(1, TOOL_A)] + [record(n, OTHER, parents=[n - 1]) for n in range(2, 6)]
    store = FakeStore(chain)
    marks = ReleaseMarks(records={TOOL_A: "r"}, lineage_depth_limit=2)
    marked = unreleased_dependencies(FakeReader([rid(5), rid(3)]), store, marks)
    assert marked[rid(5)].lineage_incomplete
    assert marked[rid(5)].tools == ()
    assert marked[rid(3)].tools == (TOOL_A,)
    assert not marked[rid(3)].lineage_incomplete


def test_cycle_terminates() -> None:
    store = FakeStore([record(1, OTHER, parents=[2]), record(2, OTHER, parents=[1])])
    assert unreleased_dependencies(FakeReader([rid(1)]), store, MARKS) == {}


def test_unreadable_record_is_report_error() -> None:
    with pytest.raises(ReportError):
        unreleased_dependencies(FakeReader([rid(9)]), FakeStore([]), MARKS)


def test_default_depth_limit_is_fifty() -> None:
    assert ReleaseMarks(records={}).lineage_depth_limit == 50
