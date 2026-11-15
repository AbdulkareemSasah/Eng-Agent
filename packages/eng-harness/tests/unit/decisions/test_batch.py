"""`decide_many`: batching per provider, one screen for the unresolved calls, stored outcomes (plan 0005 T9).

Spec 0005 AC27 to AC29 and section 4.8. The providers are the fakes of `tests/fakes/decision_providers.py`; the
monotonic clock steps a quarter of a second per reading; the rule guard is a no-op.
"""

import asyncio
from collections.abc import Iterator, Sequence
from contextlib import nullcontext
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.basis import BasisField, DesignBasis
from fakes.decision_providers import FakeDecisionProvider, FakeLLMProvider
from pydantic import BaseModel, ConfigDict

from eng_harness.ctx import BasisView
from eng_harness.decisions import Cascade, LabelStore
from eng_harness.decisions._points import PointRegistry, decision_point
from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings, ShadowRelease
from eng_harness.decisions.interfaces import (
    ChoiceAnswer,
    DecisionAnswer,
    DecisionCall,
    DecisionProvider,
    EngineerChoice,
    LLMAnswer,
    LLMProvider,
    PendingAnswer,
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    ProviderInfo,
    ProviderRequest,
    Suggestion,
)
from eng_harness.decisions.types import Pick, RuleBasis, rule
from eng_harness.errors import BlockRuleViolation

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
RES = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
ANSWERED_AT = "2026-01-01T00:00:02.500Z"
MODEL_BY = "model:fake/fake-model@0"
LLM_BY = "llm:fake/fake-model@0"
RULE_BY = "rule:batch_pick.low"
SINGLE = ProviderInfo(provider="fake", model="fake-model", version="0", is_local=True, supports_batch=False)


class Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class State(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int


POINT = decision_point(name="batch_pick", version=1, title="Pick an action", options=Action, state=State)(object)
RELEASED = DecisionSettings(shadow_released={"batch_pick": ShadowRelease(point_version=1, basis="owner", record="r1")})
LIVE = DecisionPolicy(shadow=False)
BOTH_LIVE = DecisionPolicy(shadow=False, llm=True)
STORES: list[LabelStore] = []
RAN: list[int] = []


class Ticks:
    """A monotonic clock in seconds: the first reading is 100.0 and each reading adds a quarter of a second."""

    def __init__(self) -> None:
        self._n = -1

    def __call__(self) -> float:
        self._n += 1
        return 100.0 + self._n * 0.25


@rule(id="batch_pick.low", version=1, point="batch_pick", rationale="Enlarge when the number is below ten.")
def low(state: State, basis: RuleBasis) -> Pick[Action] | None:
    RAN.append(state.n)
    return Pick(Action.ENLARGE) if state.n < 10 else None


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    RAN.clear()
    yield
    while STORES:
        STORES.pop().close()


class Gauge:
    """How many calls are inside a provider at the same time, and the most there ever were."""

    def __init__(self) -> None:
        self.now = 0
        self.most = 0

    async def pass_through(self) -> None:
        self.now += 1
        self.most = max(self.most, self.now)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.now -= 1


class CountingModel(FakeDecisionProvider):
    """Records the size of every `batch` request and every single `choose`."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.sizes: list[int] = []
        self.singles = 0

    async def choose(self, request: ProviderRequest) -> ChoiceAnswer:
        self.singles += 1
        return await super().choose(request)

    async def batch(self, requests: Sequence[ProviderRequest]) -> Sequence[ChoiceAnswer | ProviderFailure]:
        self.sizes.append(len(requests))
        return await super().batch(requests)


class GaugedModel(FakeDecisionProvider):
    def __init__(self, gauge: Gauge, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._gauge = gauge

    async def choose(self, request: ProviderRequest) -> ChoiceAnswer:
        await self._gauge.pass_through()
        return await super().choose(request)


class GaugedLLM(FakeLLMProvider):
    def __init__(self, gauge: Gauge, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._gauge = gauge

    async def decide(self, request: ProviderRequest) -> LLMAnswer:
        await self._gauge.pass_through()
        return await super().decide(request)


class BrokenBatch(FakeDecisionProvider):
    """A batch provider whose `batch` raises, or answers with the wrong number of entries."""

    def __init__(self, error: Exception | None = None) -> None:
        super().__init__()
        self._error = error

    async def batch(self, requests: Sequence[ProviderRequest]) -> Sequence[ChoiceAnswer | ProviderFailure]:
        if self._error is not None:
            raise self._error
        return [ChoiceAnswer(choice="enlarge", confidence=0.95)]


def _view() -> BasisView:
    field = BasisField(
        value=0.5, unit="1", source="engineer:eng@2026-01-01T00:00:00.000Z", confirmed=True, citation=None
    )
    return BasisView(RES, DesignBasis(template=None, fields={"limits.bearing_ratio": field}), ("limits.bearing_ratio",))


def _build(
    labels: LabelStore,
    settings: DecisionSettings,
    *,
    model: DecisionProvider | None = None,
    llm: LLMProvider | None = None,
    limit: int | None = None,
) -> Cascade:
    extra: dict[str, Any] = {}  # a keyword is given only when a test has it
    if model is not None:
        extra["model"] = model
    if llm is not None:
        extra["llm"] = llm
    if limit is not None:
        extra["max_concurrent_decisions"] = limit
    return Cascade(
        PointRegistry((POINT,)),
        settings,
        labels,
        clock=FixedClock(START_MS + 60_000, 1),
        monotonic=Ticks(),
        rule_guard=nullcontext,
        **extra,
    )


def _store(tmp_path: Path, settings: DecisionSettings) -> LabelStore:
    clock = FixedClock(START_MS, 1)
    labels = LabelStore(tmp_path, settings, clock, SeededIdSource(b"labels", clock))
    STORES.append(labels)
    return labels


def _setup(
    tmp_path: Path,
    *,
    settings: DecisionSettings = RELEASED,
    model: DecisionProvider | None = None,
    llm: LLMProvider | None = None,
    limit: int | None = None,
) -> tuple[Cascade, LabelStore]:
    labels = _store(tmp_path, settings)
    return _build(labels, settings, model=model, llm=llm, limit=limit), labels


def _rid(n: int) -> str:
    return f"dec_{n:032x}"


def _call(n: int, *, policy: DecisionPolicy = LIVE, choice: str | None = None) -> DecisionCall:
    given = EngineerChoice(choice=choice, by="Engineer One", answered_at=ANSWERED_AT) if choice is not None else None
    return DecisionCall(
        request_id=_rid(n),
        run_id="run_x",
        step_path="0",
        point=POINT,
        options=Action,
        state=State(n=n),
        rules=(low,),
        policy=policy,
        basis=_view(),
        engineer_choice=given,
    )


def _many(cascade: Cascade, calls: Sequence[DecisionCall]) -> list[DecisionAnswer | PendingAnswer]:
    return asyncio.run(cascade.decide_many(calls))


def _decided(result: DecisionAnswer | PendingAnswer) -> DecisionAnswer:
    assert isinstance(result, DecisionAnswer)
    return result


def _pending(result: DecisionAnswer | PendingAnswer) -> PendingAnswer:
    assert isinstance(result, PendingAnswer)
    return result


def _core(entry: Suggestion) -> tuple[object, ...]:
    """An entry without its timing."""
    return (entry.tier, entry.by, entry.outcome, entry.choice, entry.confidence, entry.shadow, entry.error)


def test_batching_and_order(tmp_path: Path) -> None:
    """AC27: rules run per call; the unresolved calls go to a batching provider in one request; answers keep order."""
    model = CountingModel(
        choices=[ChoiceAnswer(choice="rebar", confidence=0.95), ChoiceAnswer(choice="enlarge", confidence=0.9)]
    )
    cascade, labels = _setup(tmp_path, model=model)
    calls = [_call(1), _call(20), _call(30), _call(5)]
    answers = [_decided(x) for x in _many(cascade, calls)]
    assert RAN == [1, 20, 30, 5]  # tier 1 runs for every call, in call order
    assert model.sizes == [2]  # one batch request, for the two calls no rule answered
    assert model.singles == 0
    assert [r.request_id for r in model.requests] == [_rid(20), _rid(30)]
    assert [r.state for r in model.requests] == [{"n": 20}, {"n": 30}]
    assert [(a.choice, a.decided_by) for a in answers] == [
        ("enlarge", RULE_BY),
        ("rebar", MODEL_BY),
        ("enlarge", MODEL_BY),
        ("enlarge", RULE_BY),
    ]
    assert [a.confidence for a in answers] == [None, 0.95, 0.9, None]
    assert [[_core(s) for s in a.suggestions] for a in answers[1:3]] == [
        [(2, MODEL_BY, "accepted", "rebar", 0.95, False, None)],
        [(2, MODEL_BY, "accepted", "enlarge", 0.9, False, None)],
    ]
    assert all(a.options == ("enlarge", "rebar") for a in answers)
    assert labels.get_pending(_rid(20)) is None  # a provider answer is no pending request


def test_concurrent_calls_are_bounded(tmp_path: Path) -> None:
    """AC27: a provider without `supports_batch` gets concurrent single calls, at most `max_concurrent_decisions`."""
    answers = [ChoiceAnswer(choice="rebar", confidence=0.95)] * 5
    calls = [_call(n) for n in range(20, 25)]
    for limit, most in ((None, 4), (2, 2), (1, 1), (9, 5)):
        gauge = Gauge()
        model = GaugedModel(gauge, choices=answers, info=SINGLE)
        cascade, _ = _setup(tmp_path / f"model{limit}", model=model, limit=limit)
        result = _many(cascade, calls)
        assert gauge.most == most, limit
        assert [_decided(a).decided_by for a in result] == [MODEL_BY] * 5
        assert sorted(r.request_id for r in model.requests) == [_rid(n) for n in range(20, 25)]
    gauge = Gauge()
    llm = GaugedLLM(gauge, answers=[LLMAnswer(choice="rebar", rationale="Rebar is the usual fix.")] * 5)
    cascade, _ = _setup(tmp_path / "llm", llm=llm, limit=3)
    result = _many(
        cascade, [_call(n, policy=DecisionPolicy(model=False, llm=True, shadow=False)) for n in range(20, 25)]
    )
    assert gauge.most == 3
    assert [_decided(a).decided_by for a in result] == [LLM_BY] * 5
    # a batching provider is asked once, whatever the limit
    model = CountingModel(choices=answers, info=SINGLE.model_copy(update={"supports_batch": True}))
    cascade, _ = _setup(tmp_path / "batch", model=model, limit=1)
    assert [_decided(a).choice for a in _many(cascade, calls)] == ["rebar"] * 5
    assert (model.sizes, model.singles) == ([5], 0)


def test_tiers_per_call(tmp_path: Path) -> None:
    """Shadow calls record both tiers; a live call whose tier 2 is below the bar goes on to tier 3."""
    model = CountingModel(
        choices=[ChoiceAnswer(choice="rebar", confidence=0.5), ChoiceAnswer(choice="rebar", confidence=0.95)]
    )
    llm = FakeLLMProvider(answers=[LLMAnswer(choice="enlarge", rationale="Enlarging is the usual fix.")] * 2)
    cascade, _ = _setup(tmp_path / "live", model=model, llm=llm)
    result = _many(cascade, [_call(20, policy=BOTH_LIVE), _call(30, policy=BOTH_LIVE)])
    assert model.sizes == [2]
    first, second = _decided(result[0]), _decided(result[1])
    assert (first.choice, first.decided_by) == ("enlarge", LLM_BY)  # tier 2 below the bar, tier 3 accepted
    assert [_core(s)[:3] for s in first.suggestions] == [(2, MODEL_BY, "below_threshold"), (3, LLM_BY, "accepted")]
    assert (second.choice, second.decided_by) == ("rebar", MODEL_BY)
    assert [r.request_id for r in llm.requests] == [_rid(20)]  # tier 3 only for the call tier 2 did not settle
    model = CountingModel(choices=[ChoiceAnswer(choice="rebar", confidence=0.95)] * 2)
    llm = FakeLLMProvider(answers=[LLMAnswer(choice="enlarge", rationale="Enlarging is the usual fix.")] * 2)
    cascade, _ = _setup(tmp_path / "shadow", settings=DecisionSettings(), model=model, llm=llm)
    result = _many(cascade, [_call(20, policy=DecisionPolicy(llm=True)), _call(30, policy=DecisionPolicy(llm=True))])
    screen = _pending(result[0]).screen
    assert [[_core(s) for s in item.suggestions] for item in screen.items] == [
        [(2, MODEL_BY, "shadow", "rebar", 0.95, True, None), (3, LLM_BY, "shadow", "enlarge", None, True, None)]
    ] * 2
    assert (model.sizes, len(llm.requests)) == ([2], 2)


def test_batch_failures_fall_through(tmp_path: Path) -> None:
    """A failed entry, a failed batch, a slow batch and a batch of the wrong size are recorded; the engineer decides."""
    entries = [ChoiceAnswer(choice="rebar", confidence=0.95), ProviderError(ProviderErrorCode.NETWORK)]
    cascade, _ = _setup(
        tmp_path / "entry", model=CountingModel(choices=[*entries, ProviderError(ProviderErrorCode.TIMEOUT)])
    )
    result = _many(cascade, [_call(20), _call(30), _call(40)])
    assert _decided(result[0]).decided_by == MODEL_BY
    [item, other] = _pending(result[1]).screen.items
    assert [_core(s) for s in item.suggestions] == [(2, MODEL_BY, "error", None, None, False, "ProviderError:network")]
    assert [_core(s) for s in other.suggestions] == [
        (2, MODEL_BY, "timeout", None, None, False, "ProviderError:timeout")
    ]
    cases = {
        "raises": (BrokenBatch(ProviderError(ProviderErrorCode.AUTH)), "error", "ProviderError:auth"),
        "short": (BrokenBatch(), "error", "ProviderError:bad_response"),
        "slow": (
            FakeDecisionProvider(choices=[ChoiceAnswer(choice="rebar", confidence=0.95)] * 2, delay_s=0.05),
            "timeout",
            "TimeoutError",
        ),
    }
    for name, (model, outcome, error) in cases.items():
        policy = DecisionPolicy(shadow=False, timeout_ms_model=1) if name == "slow" else LIVE
        cascade, _ = _setup(tmp_path / name, model=model)
        [one, two] = [_pending(x) for x in _many(cascade, [_call(20, policy=policy), _call(30, policy=policy)])]
        assert one.batch_id == two.batch_id, name
        got = [[_core(s) for s in i.suggestions] for i in one.screen.items]
        assert got == [[(2, MODEL_BY, outcome, None, None, False, error)]] * 2, name


def test_one_screen_all_or_nothing(tmp_path: Path) -> None:
    """AC28: the unresolved calls share one batch id and one screen, and the engineer answers all of them or none."""
    cascade, labels = _setup(tmp_path)
    calls = [_call(1), _call(20), _call(30)]
    first, second, third = _many(cascade, calls)
    rule_answer = _decided(first)
    one, two = _pending(second), _pending(third)
    assert one.batch_id == two.batch_id
    assert one.batch_id is not None
    assert one.batch_id.startswith("batch_")
    assert len(one.batch_id) == 6 + 16
    assert (one.request_id, two.request_id) == (_rid(20), _rid(30))
    assert one.screen == two.screen
    assert [i.request_id for i in one.screen.items] == [_rid(20), _rid(30)]  # one item per unresolved call, in order
    assert labels.get_pending(_rid(1)) is None  # a call a rule answered is no pending request
    for n in (20, 30):
        row = labels.get_pending(_rid(n))
        assert row is not None
        assert (row.batch_id, row.screen, row.closed_at) == (one.batch_id, one.screen, None)
        assert row.outcomes == {_rid(1): rule_answer.model_dump(mode="json", by_alias=True)}
    # a set of answers that misses a call is refused as a whole, and nothing is labeled
    short = _many(cascade, [_call(20, choice="rebar")])
    assert [(_pending(x).rejected, _pending(x).batch_id, _pending(x).screen) for x in short] == [
        ("incomplete", one.batch_id, one.screen)
    ]
    missing = _many(cascade, [_call(20, choice="rebar"), _call(30)])
    assert [_pending(x).rejected for x in missing] == ["incomplete", "incomplete"]
    # so is a set with an invalid answer, even for the valid ones
    invalid = _many(cascade, [_call(20, choice="rebar"), _call(30, choice="nope")])
    assert [(_pending(x).rejected, _pending(x).screen) for x in invalid] == [("not_an_option", one.screen)] * 2
    assert labels.read("batch_pick") == ()
    assert all((r := labels.get_pending(_rid(n))) is not None and r.closed_at is None for n in (20, 30))
    ran = list(RAN)
    done = _many(cascade, [_call(1), _call(20, choice="rebar"), _call(30, choice="enlarge")])
    assert _decided(done[0]) == rule_answer  # returned from the stored outcomes, the rule is not run again
    assert ran == RAN
    assert [(_decided(x).choice, _decided(x).decided_by) for x in done[1:]] == [
        ("rebar", "engineer:Engineer One"),
        ("enlarge", "engineer:Engineer One"),
    ]
    assert sorted(x.label for x in labels.read("batch_pick")) == ["enlarge", "rebar"]
    assert all((r := labels.get_pending(_rid(n))) is not None and r.closed_at is not None for n in (20, 30))
    # an answer set for one call with nothing pending in the batch left is just that call's answer (the engine's picks)
    again = _many(cascade, [_call(20, choice="rebar"), _call(30, choice="enlarge")])
    assert [_decided(x).choice for x in again] == ["rebar", "enlarge"]


def test_engineer_answers_only(tmp_path: Path) -> None:
    """The engine's second call holds only the asked calls: the batch is answered from the stored screen."""
    cascade, labels = _setup(tmp_path)
    first = _many(cascade, [_call(1), _call(20), _call(30)])
    ran = list(RAN)
    answers = _many(cascade, [_call(20, choice="rebar"), _call(30, choice="rebar")])
    assert [_decided(x).decided_by for x in answers] == ["engineer:Engineer One"] * 2
    assert ran == RAN
    assert [label.request_id for label in labels.read("batch_pick")] == [_rid(20), _rid(30)]
    assert _decided(first[0]).decided_by == RULE_BY


def test_resume_does_not_requery(tmp_path: Path) -> None:
    """AC29: a repeated call returns the resolved members from the stored outcomes; no provider is asked again."""
    model = CountingModel(
        choices=[ChoiceAnswer(choice="rebar", confidence=0.95), ChoiceAnswer(choice="rebar", confidence=0.5)]
    )
    cascade, labels = _setup(tmp_path, model=model)
    calls = [_call(1), _call(20), _call(30)]
    first = _many(cascade, calls)
    assert [type(x) for x in first] == [DecisionAnswer, DecisionAnswer, PendingAnswer]
    assert _decided(first[1]).decided_by == MODEL_BY
    ran, asked = list(RAN), len(model.requests)
    assert (model.sizes, asked) == ([2], 2)
    # the same call again, in the same run and in a new cascade over the same store (a resume, with a silent provider)
    quiet = CountingModel()
    for who, model_again in (("same", model), ("new", quiet)):
        again = _build(labels, RELEASED, model=model_again) if who == "new" else cascade
        repeated = _many(again, calls)
        assert repeated == first, who
        assert (model.sizes, len(model.requests), quiet.sizes, quiet.requests, quiet.singles) == ([2], 2, [], [], 0), (
            who
        )
    assert ran == RAN  # not even a rule runs again for the stored members
    # the engineer answers the one pending call; the resolved members still come from the store
    done = _many(_build(labels, RELEASED, model=quiet), [*calls[:2], _call(30, choice="enlarge")])
    assert _decided(done[0]) == first[0]
    assert _decided(done[1]) == first[1]
    assert (_decided(done[2]).choice, _decided(done[2]).decided_by) == ("enlarge", "engineer:Engineer One")
    # and after the request is closed the whole batch is still returned as recorded
    closed = _many(_build(labels, RELEASED, model=quiet), calls)
    assert [_decided(x).choice for x in closed] == ["enlarge", "rebar", "enlarge"]
    assert [x.decided_by for x in map(_decided, closed)] == [RULE_BY, MODEL_BY, "engineer:Engineer One"]
    assert (quiet.requests, quiet.sizes, len(model.requests)) == ([], [], 2)


def test_validation_comes_first(tmp_path: Path) -> None:
    """Every call is validated before a rule runs, a provider is asked or a request is stored."""
    model = CountingModel(choices=[ChoiceAnswer(choice="rebar", confidence=0.95)] * 2)
    cascade, labels = _setup(tmp_path, model=model)
    bad = _call(30).model_copy(update={"state": State(n=30), "options": ("a", "b")})
    with pytest.raises(BlockRuleViolation):
        _many(cascade, [_call(1), _call(20), bad])
    assert (RAN, model.requests, model.sizes) == ([], [], [])
    assert labels.get_pending(_rid(20)) is None
    assert _many(cascade, []) == []


def test_batch_helpers() -> None:
    """The pure helpers: the batch id, the all-or-nothing check, the bounded gather and the stored outcomes."""
    from eng_harness.decisions._batch import batch_id, bounded, refusal, restored, stored

    assert batch_id(["b", "a"]) == batch_id(["a", "b"])
    assert batch_id(["a"]) != batch_id(["b"])
    assert batch_id(["a", "b"]).startswith("batch_")
    assert len(batch_id(["a", "b"])) == 22
    values = {"a": ("x", "y"), "b": ("x", "y")}
    assert refusal({"a", "b"}, {}, values) is None  # nothing answered yet
    assert refusal({"a", "b"}, {"a": "x", "b": "y"}, values) is None
    assert refusal({"a", "b"}, {"a": "x"}, values) == "incomplete"
    assert refusal({"a", "b"}, {"a": "z"}, values) == "incomplete"  # a missing answer is named before a bad one
    assert refusal({"a"}, {"a": "z"}, values) == "not_an_option"
    assert refusal(set(), {"a": "x"}, values) is None
    answer = DecisionAnswer(
        choice="x", decided_by="rule:r", latency_ms=1, options=("x",), state_sha256="s",
        suggestions=(Suggestion(tier=2, by="b", outcome="accepted", choice="x", rationale="No digit here.",
            latency_ms=1, shadow=False),),
    )  # fmt: skip
    assert restored(stored({"a": answer})) == {"a": answer}

    async def job(n: int, gauge: Gauge) -> int:
        await gauge.pass_through()
        return n

    for limit in (1, 2, 5):
        gauge = Gauge()
        done = asyncio.run(bounded(limit, [partial(job, n, gauge) for n in range(5)]))
        assert (done, gauge.most) == ([0, 1, 2, 3, 4], limit)
