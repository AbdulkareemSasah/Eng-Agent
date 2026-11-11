"""Step paths, scopes, op_id, overlap and the parallel and attempts drivers (plan 0001 T8; spec 0001 4.3.1, AC5 to AC8).

The tests drive the helpers with a stub step executor (a function that records the path it was given), before the
runner exists.
"""

import asyncio
import hashlib
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Literal

import pytest
from workflows.ctx_flows import flow
from workflows.rig import make_rig, request

from eng_harness.engine import RunStatus
from eng_harness.engine._invariants import path_key
from eng_harness.engine._steps import (
    MAX_PATH_LENGTH,
    Scope,
    attempts,
    block_step,
    inserted_path,
    op_id,
    parallel,
    resume_path,
    root_scope,
    step,
    validate_path,
)
from eng_harness.errors import (
    BlockRuleViolation,
    EngineStop,
    Escalation,
    HarnessCode,
    NeedsReconciliation,
    NotImplementedGap,
    Pause,
    ReplayDivergence,
    StepError,
)
from eng_harness.ports import ToolInfo

RUN_ID = "run_01ARZ3NDEKTSV4RRFFQ69G5FAV"


async def _yield(times: int) -> None:
    """Give the other tasks `times` turns; orders completions without a clock."""
    for _ in range(times):
        await asyncio.sleep(0)


def _leaf(log: list[str], label: str, delay: int = 0) -> Callable[[], Awaitable[str]]:
    """A stub step executor: records the path it runs at and the order of completion."""

    async def run() -> str:
        async def execute(path: str) -> str:
            log.append(f"start {path}")
            await _yield(delay)
            log.append(f"end {path}")
            return f"{label}@{path}"

        return await step(execute)

    return run


def _workflow(delays: Sequence[int]) -> Callable[[], Awaitable[tuple[list[str], list[object]]]]:
    """Sequential steps, a child block, three parallel children and an attempts loop; `delays` orders the children."""

    async def run() -> tuple[list[str], list[object]]:
        log: list[str] = []
        results: list[object] = []
        with root_scope():
            results.append(await _leaf(log, "a")())  # 0

            async def child(path: str) -> str:
                return await _leaf(log, "c1")() + await _leaf(log, "c2")()  # 1/0, 1/1

            results.append(await block_step(child))  # 1

            def branch(i: int) -> Awaitable[str]:
                async def body() -> str:
                    first = await _leaf(log, f"p{i}", delays[i])()  # 2/i/0
                    return first + await _leaf(log, f"q{i}")()  # 2/i/1

                return body()

            results.append(await parallel([branch(0), branch(1), branch(2)]))  # 2
            async for attempt in attempts(3):  # 3, scopes 3/0, 3/1, ...
                results.append(await _leaf(log, f"t{attempt.index}")())
                if attempt.index == 1:
                    break
            results.append(await _leaf(log, "z")())  # 4
        return log, results

    return run


def test_paths_independent_of_completion_order() -> None:
    log_a, results_a = asyncio.run(_workflow((0, 3, 6))())
    log_b, results_b = asyncio.run(_workflow((6, 3, 0))())
    started = [line for line in log_a if line.startswith("start")]
    assert sorted(started) == sorted(
        [
            "start 0",
            "start 1/0",
            "start 1/1",
            "start 2/0/0",
            "start 2/1/0",
            "start 2/2/0",
            "start 2/0/1",
            "start 2/1/1",
            "start 2/2/1",
            "start 3/0/0",
            "start 3/1/0",
            "start 4",
        ]
    )
    assert sorted(line for line in log_b if line.startswith("start")) == sorted(started)
    ends_a = [line for line in log_a if line.startswith("end 2/") and line.endswith("/0")]
    ends_b = [line for line in log_b if line.startswith("end 2/") and line.endswith("/0")]
    assert ends_a == ["end 2/0/0", "end 2/1/0", "end 2/2/0"]
    assert ends_b == ["end 2/2/0", "end 2/1/0", "end 2/0/0"]  # the completion orders really are opposite
    assert sorted(log_a) == sorted(log_b)
    assert results_a == results_b
    assert results_a[2] == ["p0@2/0/0q0@2/0/1", "p1@2/1/0q1@2/1/1", "p2@2/2/0q2@2/2/1"]  # argument order
    assert results_a[1] == "c1@1/0c2@1/1"
    assert results_a[3:] == ["t0@3/0/0", "t1@3/1/0", "z@4"]


def test_inserted_and_housekeeping_paths() -> None:
    assert inserted_path("2/0", "pre", "check_model", "mod_1") == "2/0~pre.check_model.mod_1"
    assert inserted_path("3", "post", "save") == "3~post.save"
    assert inserted_path("", "end", "check_model", "mod_1") == "~end.check_model.mod_1"
    assert inserted_path("4/1", "host", "epoch", "s2") == "4/1~host.epoch.s2"
    assert resume_path(2, "model_state", "mod_1") == "@resume2.model_state.mod_1"
    for good in ("0", "10/2/0", "0/1~end.x", "5~host.epoch.a:b-c_d.e", "@resume0.server_check.csi"):
        assert validate_path(good) == good
    for bad in ("", "01", "1//2", "1/", "a", "1~mid.x", "1~pre", "1~pre.x.", "@resume.x.y", "@resume1.x", "1 ", "-1"):
        with pytest.raises(ValueError, match="step path"):
            validate_path(bad)
    with pytest.raises(ValueError, match="step path"):
        inserted_path("", "pre", "check_model")  # only the root block's end step has an empty base
    with pytest.raises(ValueError, match="step path"):
        inserted_path("1", "post", "check_model", "bad key")
    with pytest.raises(ValueError, match="step path"):
        inserted_path("1", "post", "check_model", "k" * 201)


def test_path_key_hashes_a_model_outside_the_grammar() -> None:
    """A model key that is not a path key becomes `h` and the first 12 hex digits of its SHA-256 (spec 4.3.1)."""
    assert path_key("mod_1") == "mod_1"
    raw = "bad key"
    assert path_key(raw) == "h" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def test_path_length_limit() -> None:
    longest_allowed = Scope("/".join(["0"] * 511))  # 1021 characters; its first step is 1023 characters
    assert len(longest_allowed.begin()) == MAX_PATH_LENGTH - 1
    too_long = Scope("/".join(["0"] * 512))  # 1023 characters; its first step would be 1025
    with pytest.raises(BlockRuleViolation, match="1024"):
        too_long.begin()


def test_op_id() -> None:
    expected = "op_" + hashlib.sha256(f"{RUN_ID}\n2/0\n1".encode()).hexdigest()[:32]
    assert op_id(RUN_ID, "2/0", 1) == expected
    assert len(expected) == 3 + 32
    ids = {op_id(RUN_ID, "2/0", attempt) for attempt in (1, 2, 3)}
    assert len(ids) == 3
    assert op_id(RUN_ID, "2/1", 1) != op_id(RUN_ID, "2/0", 1)
    assert op_id("run_01ARZ3NDEKTSV4RRFFQ69G5FAW", "2/0", 1) != op_id(RUN_ID, "2/0", 1)
    with pytest.raises(ValueError, match="attempt"):
        op_id(RUN_ID, "2/0", 0)
    with pytest.raises(ValueError, match="step path"):
        op_id(RUN_ID, "x", 1)


def test_overlap_outside_parallel() -> None:
    async def scenario() -> tuple[list[object], list[str], str]:
        gate = asyncio.Event()
        called: list[str] = []

        async def first(path: str) -> str:
            called.append(path)
            await gate.wait()
            return "a"

        async def second(path: str) -> str:
            called.append(path)
            return "b"

        async def release() -> None:
            await _yield(2)
            gate.set()

        with root_scope():
            outcomes = await asyncio.gather(step(first), step(second), release(), return_exceptions=True)
            after = await step(second)  # a refused overlap takes no index
        return list(outcomes), called, after

    outcomes, called, after = asyncio.run(scenario())
    assert outcomes[0] == "a"
    violation = outcomes[1]
    assert isinstance(violation, BlockRuleViolation)
    assert violation.code == HarnessCode.BLOCK_RULE_VIOLATION
    assert called == ["0", "1"]  # the refused overlap never reached its port call; the next step took "1"
    assert after == "b"


def test_overlapping_block_steps_are_refused() -> None:
    async def scenario() -> list[object]:
        gate = asyncio.Event()

        async def holding(path: str) -> str:
            await gate.wait()
            return path

        async def noop(path: str) -> str:
            return path

        async def release() -> None:
            await _yield(2)
            gate.set()

        with root_scope():
            return list(await asyncio.gather(block_step(holding), block_step(noop), release(), return_exceptions=True))

    outcomes = asyncio.run(scenario())
    assert outcomes[0] == "0"
    assert isinstance(outcomes[1], BlockRuleViolation)


def test_step_outside_a_run_is_refused() -> None:
    async def execute(path: str) -> str:
        return path

    with pytest.raises(BlockRuleViolation, match="outside"):
        asyncio.run(step(execute))


def _failing(i: int, delay: int, error: BaseException | None, done: list[int]) -> Awaitable[int]:
    async def body() -> int:
        async def execute(path: str) -> int:
            await _yield(delay)
            done.append(i)
            if error is not None:
                raise error
            return i

        return await step(execute)

    return body()


@pytest.mark.parametrize(
    ("errors", "delays", "winner"),
    [
        # class rank: ReplayDivergence > NeedsReconciliation > BlockRuleViolation > Escalation > Pause > StepError
        ({0: NotImplementedGap("s"), 1: Pause("p"), 2: Escalation("e")}, (0, 5, 9), "Escalation"),
        ({0: NotImplementedGap("s"), 1: Pause("p"), 2: Escalation("e")}, (9, 5, 0), "Escalation"),
        (
            {0: Pause("p"), 1: BlockRuleViolation("b"), 2: NeedsReconciliation("n"), 3: ReplayDivergence("r")},
            (0, 1, 2, 3),
            "ReplayDivergence",
        ),
        (
            {0: Pause("p"), 1: BlockRuleViolation("b"), 2: NeedsReconciliation("n"), 3: ReplayDivergence("r")},
            (3, 2, 1, 0),
            "ReplayDivergence",
        ),
        ({0: Pause("p"), 1: BlockRuleViolation("b"), 2: NeedsReconciliation("n")}, (9, 0, 5), "NeedsReconciliation"),
        ({0: Pause("p"), 1: NotImplementedGap("s")}, (5, 0), "Pause"),
    ],
)
def test_parallel_error_choice(errors: dict[int, BaseException], delays: tuple[int, ...], winner: str) -> None:
    done: list[int] = []

    async def scenario() -> None:
        with root_scope():
            children = [_failing(i, delays[i], errors.get(i), done) for i in range(len(delays))]
            await parallel(children)

    with pytest.raises((EngineStop, StepError)) as caught:
        asyncio.run(scenario())
    assert type(caught.value).__name__ == winner
    assert sorted(done) == list(range(len(delays)))  # every child ran to its end, none was cancelled


def test_parallel_error_choice_lowest_index_within_a_class() -> None:
    errors = {0: Pause("zero"), 1: Pause("one"), 2: Pause("two")}
    for delays in ((0, 4, 8), (8, 4, 0), (4, 0, 8)):
        done: list[int] = []

        async def scenario(delays: tuple[int, ...] = delays, done: list[int] = done) -> None:
            with root_scope():
                await parallel([_failing(i, delays[i], errors[i], done) for i in range(3)])

        with pytest.raises(Pause) as caught:
            asyncio.run(scenario())
        assert caught.value.message == "zero"
        assert len(done) == 3


def test_parallel_without_failures_and_when_refused() -> None:
    async def scenario() -> list[object]:
        done: list[int] = []
        gate = asyncio.Event()
        outcomes: list[object] = []

        async def holding(path: str) -> str:
            await gate.wait()
            return path

        with root_scope():
            outcomes.append(await parallel([]))
            outcomes.append(await parallel([_failing(i, 2 - i, None, done) for i in range(3)]))
            blocked = asyncio.ensure_future(step(holding))
            await _yield(1)
            never_started = _failing(0, 0, None, done)
            with pytest.raises(BlockRuleViolation):
                await parallel([never_started])  # the parallel step overlaps the step in progress
            gate.set()
            outcomes.append(await blocked)
            outcomes.append(done)
        return outcomes

    assert asyncio.run(scenario()) == [[], [0, 1, 2], "2", [2, 1, 0]]


def test_attempts_scopes_and_exhaustion() -> None:
    async def scenario() -> tuple[list[str], list[tuple[int, bool]], bool, str]:
        seen: list[str] = []
        flags: list[tuple[int, bool]] = []

        async def execute(path: str) -> str:
            seen.append(path)
            return path

        with root_scope():
            loop = attempts(3)
            async for attempt in loop:
                flags.append((attempt.index, attempt.is_last))
                await step(execute)
                await step(execute)
            after = await step(execute)
        return seen, flags, loop.exhausted, after

    seen, flags, exhausted, after = asyncio.run(scenario())
    assert seen == ["0/0/0", "0/0/1", "0/1/0", "0/1/1", "0/2/0", "0/2/1", "1"]
    assert flags == [(0, False), (1, False), (2, True)]
    assert exhausted is True
    assert after == "1"


def test_attempts_break_ends_the_loop_and_restores_the_scope() -> None:
    async def scenario() -> list[str]:
        seen: list[str] = []

        async def execute(path: str) -> str:
            seen.append(path)
            return path

        with root_scope():
            async for attempt in attempts(2):
                await step(execute)
                if attempt.index == 0:
                    break
            await step(execute)  # the next step of the enclosing scope, right after the break
            async for _ in attempts(1):
                break
            await step(execute)
        return seen

    assert asyncio.run(scenario()) == ["0/0/0", "1", "3"]


def test_attempts_body_error_releases_the_scope() -> None:
    async def scenario() -> str:
        async def execute(path: str) -> str:
            return path

        with root_scope():
            try:
                async for _ in attempts(2):
                    raise NotImplementedGap("body failed")
            except NotImplementedGap:
                pass
            return await step(execute)

    assert asyncio.run(scenario()) == "1"


@pytest.mark.parametrize(
    ("earlier", "later"),
    [("write_m", "read_m"), ("read_m", "write_m"), ("write_m", "write_m")],
)
def test_sibling_model_conflict(tmp_path: Path, earlier: str, later: str) -> None:
    """A sibling that reads or writes a model another child wrote never reaches its port call (AC5)."""
    rig = make_rig(tmp_path)
    specs: tuple[tuple[str, Literal["read", "write"]], ...] = (("write_m", "write"), ("read_m", "read"))
    for name, effect in specs:
        rig.host._tools[name] = ToolInfo(name=name, effect=effect, action="plain", host_key="csi", model_param="model")

    async def body(ctx: Any) -> list[str]:
        gate = asyncio.Event()

        async def lead() -> str:
            found = await ctx.tool(earlier, {"model": "m1"})
            gate.set()
            return str(found.ref.ref)

        async def trail() -> str:
            await gate.wait()
            return str((await ctx.tool(later, {"model": "m1"})).ref.ref)

        await ctx.parallel(lead(), trail())
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.NEEDS_ENGINEER
    assert outcome.escalation is not None
    assert outcome.escalation.reason == "block_rule_violation"
    assert [entry.tool for entry in rig.host.ledger] == [earlier]  # the later sibling made no port call


def test_sibling_reads_share_a_model(tmp_path: Path) -> None:
    """Two children may read the same model; both port calls happen (AC5)."""
    rig = make_rig(tmp_path)
    rig.host._tools["read_m"] = ToolInfo(
        name="read_m", effect="read", action="plain", host_key="csi", model_param="model"
    )

    async def body(ctx: Any) -> list[str]:
        gate = asyncio.Event()

        async def lead() -> str:
            found = await ctx.tool("read_m", {"model": "m1"})
            gate.set()
            return str(found.ref.ref)

        async def trail() -> str:
            await gate.wait()
            return str((await ctx.tool("read_m", {"model": "m1"})).ref.ref)

        await ctx.parallel(lead(), trail())
        return []

    outcome = asyncio.run(rig.engine(flow(body)).start(request()))
    assert outcome.status is RunStatus.COMPLETED
    assert [entry.tool for entry in rig.host.ledger] == ["read_m", "read_m"]


def test_attempts_overlapping_a_step_is_refused() -> None:
    async def scenario() -> None:
        gate = asyncio.Event()

        async def holding(path: str) -> str:
            await gate.wait()
            return path

        with root_scope():
            blocked = asyncio.ensure_future(step(holding))
            await _yield(1)
            with pytest.raises(BlockRuleViolation):
                attempts(2)
            gate.set()
            await blocked

    asyncio.run(scenario())
