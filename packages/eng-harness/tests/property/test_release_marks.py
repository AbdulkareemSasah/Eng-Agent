"""The marked set equals reachability to a marked producer (spec 0006 AC54)."""

from eng_contract.envelope import Provenance, RefInput
from eng_contract.records import ResultRecord
from hypothesis import given, settings
from hypothesis import strategies as st

from eng_harness.report import ReleaseMarks, unreleased_dependencies

MARKED = "sasaah/tool_a"
OTHER = "sasaah/other"


def rid(n: int) -> str:
    return f"res_0{n:025d}"


@st.composite
def graphs(draw: st.DrawFn) -> tuple[list[bool], dict[int, set[int]]]:
    size = draw(st.integers(min_value=1, max_value=12))
    is_marked = [draw(st.booleans()) for _ in range(size)]
    edges = {
        n: set(draw(st.lists(st.integers(min_value=0, max_value=size - 1), max_size=3))) - {n} for n in range(size)
    }
    return is_marked, edges


class _Store:
    def __init__(self, records: dict[str, ResultRecord]) -> None:
        self._records = records

    def get(self, result_id: str) -> ResultRecord:
        return self._records[result_id]


class _Step:
    def __init__(self, ref: str) -> None:
        self.result_ref: str | None = ref


class _Reader:
    def __init__(self, count: int) -> None:
        self._steps = [_Step(rid(n)) for n in range(count)]

    def steps(self) -> list[_Step]:
        return self._steps


def _record(n: int, tool: str, parents: list[int], inputs: list[int]) -> ResultRecord:
    prov = Provenance(
        tool=tool,
        tool_version="1",
        inputs={f"/i{i}": RefInput(ref=rid(i)) for i in inputs},
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
        producer=prov,
        parents=[rid(p) for p in parents],
        payload_sha256="0" * 64,
        payload={},
    )


def _oracle(is_marked: list[bool], edges: dict[int, set[int]]) -> set[int]:
    """Independent reachability: a node is marked when a marked node is reachable along the edges."""
    result: set[int] = set()
    for start in range(len(is_marked)):
        seen: set[int] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(edges[node])
        if any(is_marked[n] for n in seen):
            result.add(start)
    return result


@settings(derandomize=True, max_examples=200)
@given(graphs(), st.booleans())
def test_marked_set_is_closure(graph: tuple[list[bool], dict[int, set[int]]], via_inputs: bool) -> None:
    is_marked, edges = graph
    records = {
        rid(n): _record(
            n,
            MARKED if is_marked[n] else OTHER,
            [] if via_inputs else sorted(edges[n]),
            sorted(edges[n]) if via_inputs else [],
        )
        for n in range(len(is_marked))
    }
    marks = ReleaseMarks(records={MARKED: "lane/b-900"})
    found = unreleased_dependencies(_Reader(len(is_marked)), _Store(records), marks)
    assert set(found) == {rid(n) for n in _oracle(is_marked, edges)}
