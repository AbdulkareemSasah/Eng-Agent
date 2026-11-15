"""Cascade: call validation, tier 1, tiers 2 and 3, shadow mode, the engineer tier, pending requests and the record.

Plan 0005 T7 and T8; spec 0005 AC5, AC8, AC14, AC15, AC17 to AC19, AC21 to AC26, AC31, AC33 and AC34. The rules run
under a recording guard, and the monotonic clock steps a quarter of a second per reading. Tiers 2 and 3 are the fake
providers of `tests/fakes/decision_providers.py`; none of them has a network or a clock.
"""

import asyncio
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

import pytest
from eng_contract.canonical import canonical_json, payload_sha256
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.basis import BasisField, DesignBasis
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref
from fakes.decision_providers import FakeDecisionProvider, FakeLLMProvider
from pydantic import BaseModel, ConfigDict

from eng_harness.ctx import BasisView
from eng_harness.decisions import Cascade, LabelStore, StoreWriteError
from eng_harness.decisions._points import DecisionPoint, Label, PointRegistry, Refs, decision_point
from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings, ShadowRelease
from eng_harness.decisions._record import DecisionScreen, ScreenField, ScreenItem, SuggestionCode
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
    ProviderInfo,
    ProviderOption,
    ProviderRequest,
    Suggestion,
    YesNoAnswer,
)
from eng_harness.decisions.types import Pick, RuleBasis, rule
from eng_harness.errors import BlockRuleViolation, DecisionInvalid, Pause

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
RES = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
REQUEST = "dec_" + "a" * 32
OTHER_REQUEST = "dec_" + "b" * 32
ANSWERED_AT = "2026-01-01T00:00:02.500Z"


class Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class Other(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class Verdict(StrEnum):
    YES = "yes"
    NO = "no"


class State(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    failing: bool
    cover_mm: int
    result: Ref


class Members(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    members: tuple[Label, ...]
    result: Ref


class Stranger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    failing: bool


class Noted(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    note: Label
    cover_mm: int


class Inner(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    n: int
    ref: Ref


class Wide(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cover: Quantity
    inner: Inner
    links: tuple[Ref, ...]
    sizes: tuple[Quantity, ...]
    tags: tuple[Label, ...]
    extras: tuple[Label, ...]


ACTION = decision_point(name="pick_action", version=1, title="Pick an action", options=Action, state=State)(object)
ACTION_V2 = decision_point(name="pick_action", version=2, title="Pick an action", options=Action, state=State)(object)
MEMBER = decision_point(name="pick_member", version=1, title="Pick a member", options=Refs("members"), state=Members)(
    object
)
STRANGER = decision_point(name="pick_stranger", version=1, title="Pick a stranger", options=Action, state=Stranger)(
    object
)
FLAG = decision_point(
    name="pick_flag", version=1, title="Pick a verdict", options=Verdict, state=State, yes_no=("yes", "no")
)(object)
NOTED = decision_point(name="pick_noted", version=1, title="Pick with a note", options=Action, state=Noted)(object)
WIDE = decision_point(name="pick_wide", version=1, title="Pick with a wide state", options=Action, state=Wide)(object)
REF = Ref.model_validate({"$ref": RES})
STATE = State(failing=True, cover_mm=50, result=REF)
CALM = State(failing=False, cover_mm=50, result=REF)
MEMBERS = Members(members=("Column C1", "Column C2"), result=REF)
REF_OPTIONS = (f"{RES}#/fields/a/value", f"{RES}#/fields/b/value")

CALLED: list[str] = []
RATIOS: list[float] = []
GUARDED: list[bool] = []
STORES: list[LabelStore] = []


class Guard:
    """The rule guard of the tests: records how often it was entered and whether it is active."""

    def __init__(self) -> None:
        self.entries = 0
        self.active = False

    @contextmanager
    def __call__(self) -> Iterator[None]:
        self.entries += 1
        self.active = True
        try:
            yield
        finally:
            self.active = False


GUARD = Guard()


class Ticks:
    """A monotonic clock in seconds: the first reading is 100.0 and each reading adds a quarter of a second."""

    def __init__(self) -> None:
        self._n = -1

    def __call__(self) -> float:
        self._n += 1
        return 100.0 + self._n * 0.25


@rule(id="pick_action.never", version=1, point="pick_action", rationale="This rule never matches.")
def never(state: State, basis: RuleBasis) -> Pick[Action] | None:
    CALLED.append("never")
    return None


@rule(
    id="pick_action.first",
    version=1,
    point="pick_action",
    rationale="Enlarge when the check fails.",
    thresholds=("limits.bearing_ratio",),
)
def first(state: State, basis: RuleBasis) -> Pick[Action] | None:
    CALLED.append("first")
    GUARDED.append(GUARD.active)
    RATIOS.append(basis.quantity("limits.bearing_ratio").value)
    return Pick(Action.ENLARGE) if state.failing else None


@rule(id="pick_action.second", version=3, point="pick_action", rationale="Rebar is the fallback.")
def second(state: State, basis: RuleBasis) -> Pick[Action] | None:
    CALLED.append("second")
    return Pick(Action.REBAR)


@rule(id="pick_action.bad_enum", version=1, point="pick_action", rationale="Returns another enum.")
def bad_enum(state: State, basis: RuleBasis) -> Pick[Other] | None:
    return Pick(Other.ENLARGE)


@rule(id="pick_action.bad_index", version=1, point="pick_action", rationale="Returns an index for an enum.")
def bad_index(state: State, basis: RuleBasis) -> Pick[int] | None:
    return Pick(0)


@rule(id="pick_action.bad_text", version=1, point="pick_action", rationale="Returns a plain string.")
def bad_text(state: State, basis: RuleBasis) -> Pick[Any] | None:
    return Pick(cast("Any", "enlarge"))


@rule(id="pick_action.bad_result", version=1, point="pick_action", rationale="Returns no Pick.")
def bad_result(state: State, basis: RuleBasis) -> Any:
    return Action.ENLARGE


@rule(id="pick_action.raises", version=1, point="pick_action", rationale="Raises an error.")
def raises(state: State, basis: RuleBasis) -> Pick[Action] | None:
    raise ValueError("a message that holds project data")


@rule(
    id="pick_action.undeclared",
    version=1,
    point="pick_action",
    rationale="Reads a path it did not declare.",
    thresholds=("limits.bearing_ratio",),
)
def undeclared(state: State, basis: RuleBasis) -> Pick[Action] | None:
    basis.quantity("limits.other_ratio")
    return None


@rule(id="pick_action.stops", version=1, point="pick_action", rationale="Raises an engine stop.")
def stops(state: State, basis: RuleBasis) -> Pick[Action] | None:
    raise Pause("the run waits")


@rule(id="pick_member.high", version=1, point="pick_member", rationale="Out of range index.")
def high(state: Members, basis: RuleBasis) -> Pick[int] | None:
    return Pick(2)


@rule(id="pick_member.negative", version=1, point="pick_member", rationale="Negative index.")
def negative(state: Members, basis: RuleBasis) -> Pick[int] | None:
    return Pick(-1)


@rule(id="pick_member.flag", version=1, point="pick_member", rationale="A boolean is no index.")
def flag(state: Members, basis: RuleBasis) -> Pick[bool] | None:
    return Pick(cast("Any", True))


@rule(id="pick_member.member", version=1, point="pick_member", rationale="An enum member is no index.")
def member(state: Members, basis: RuleBasis) -> Pick[Action] | None:
    return Pick(Action.ENLARGE)


@rule(id="pick_member.last", version=1, point="pick_member", rationale="Picks the last member.")
def last(state: Members, basis: RuleBasis) -> Pick[int] | None:
    return Pick(1)


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    CALLED.clear()
    RATIOS.clear()
    GUARDED.clear()
    GUARD.entries = 0
    GUARD.active = False
    yield
    while STORES:
        STORES.pop().close()


def _view() -> BasisView:
    field = BasisField(
        value=0.5, unit="1", source="engineer:eng@2026-01-01T00:00:00.000Z", confirmed=True, citation=None
    )
    return BasisView(RES, DesignBasis(template=None, fields={"limits.bearing_ratio": field}), ("limits.bearing_ratio",))


def _setup(
    tmp_path: Path,
    *,
    settings: DecisionSettings | None = None,
    points: tuple[DecisionPoint, ...] | None = None,
    model: DecisionProvider | None = None,
    llm: LLMProvider | None = None,
) -> tuple[Cascade, LabelStore]:
    settings = settings or DecisionSettings()
    providers: dict[str, Any] = {}  # the two keywords are given only when a test has the provider
    if model is not None:
        providers["model"] = model
    if llm is not None:
        providers["llm"] = llm
    clock = FixedClock(START_MS, 1)
    labels = LabelStore(tmp_path, settings, clock, SeededIdSource(b"labels", clock))
    STORES.append(labels)
    cascade = Cascade(
        PointRegistry(points or (ACTION, MEMBER, NOTED, WIDE, FLAG)),
        settings,
        labels,
        clock=FixedClock(START_MS + 60_000, 1),
        monotonic=Ticks(),
        rule_guard=GUARD,
        **providers,
    )
    return cascade, labels


def _call(
    *,
    point: DecisionPoint = ACTION,
    state: BaseModel | None = None,
    options: type[StrEnum] | tuple[str, ...] | None = None,
    rules: tuple[Any, ...] = (),
    choice: EngineerChoice | None = None,
    request_id: str = REQUEST,
    sensitive: tuple[str, ...] = (),
    policy: DecisionPolicy | None = None,
) -> DecisionCall:
    refs = isinstance(point.options, Refs)
    return DecisionCall(
        request_id=request_id,
        run_id="run_x",
        step_path="0",
        point=point,
        options=options if options is not None else (REF_OPTIONS if refs else cast("type[StrEnum]", point.options)),
        state=state if state is not None else (MEMBERS if refs else STATE),
        rules=rules,
        policy=policy or DecisionPolicy(),
        basis=_view(),
        engineer_choice=choice,
        sensitive_values=sensitive,
    )


def _decide(cascade: Cascade, call: DecisionCall) -> DecisionAnswer | PendingAnswer:
    return asyncio.run(cascade.decide(call))


def _answer(choice: str, by: str = "Engineer One") -> EngineerChoice:
    return EngineerChoice(choice=choice, by=by, answered_at=ANSWERED_AT)


def _decided(result: DecisionAnswer | PendingAnswer) -> DecisionAnswer:
    assert isinstance(result, DecisionAnswer)
    return result


def _pending(result: DecisionAnswer | PendingAnswer) -> PendingAnswer:
    assert isinstance(result, PendingAnswer)
    return result


def test_call_validation(tmp_path: Path) -> None:
    """AC5: a call that does not fit its point is refused before anything is evaluated or sent."""
    size = len(canonical_json(STATE.model_dump(mode="json")))
    three = Members(members=("Column C1", "Column C2", "Column C3"), result=REF)
    refs_message = "the options of 'pick_member' must be 1 to {} references, one for each label"
    cases: dict[str, tuple[Callable[[], DecisionCall], DecisionSettings, str]] = {
        "unregistered": (
            lambda: _call(point=STRANGER, state=Stranger(failing=True), rules=(first,)),
            DecisionSettings(),
            "'pick_stranger' is not a registered decision point",
        ),
        "changed_definition": (
            lambda: _call(point=ACTION_V2, rules=(first,)),
            DecisionSettings(),
            "'pick_action' is not a registered decision point",
        ),
        "other_options": (
            lambda: _call(options=Other, rules=(first,)),
            DecisionSettings(),
            "the options of 'pick_action' differ from the point's",
        ),
        "wrong_state": (
            lambda: _call(state=Stranger(failing=True), rules=(first,)),
            DecisionSettings(),
            "the state of 'pick_action' is not a State",
        ),
        "refs_none": (
            lambda: _call(point=MEMBER, state=Members(members=(), result=REF), options=(), rules=(last,)),
            DecisionSettings(),
            refs_message.format(32),
        ),
        "refs_above_max": (
            lambda: _call(point=MEMBER, state=three, options=(*REF_OPTIONS, f"{RES}#/fields/c/value"), rules=(last,)),
            DecisionSettings(max_options=2),
            refs_message.format(2),
        ),
        "refs_not_one_label_each": (
            lambda: _call(point=MEMBER, state=three, rules=(last,)),
            DecisionSettings(),
            refs_message.format(32),
        ),
        "refs_as_enum": (
            lambda: _call(point=MEMBER, options=Action, rules=(last,)),
            DecisionSettings(),
            refs_message.format(32),
        ),
        "oversize": (
            lambda: _call(rules=(first,)),
            DecisionSettings(max_state_bytes=size - 1),
            f"pick_action: state is {size} bytes, above max_state_bytes {size - 1}",
        ),
    }
    for name, (make, settings, message) in cases.items():
        cascade, labels = _setup(tmp_path / name, settings=settings)
        with pytest.raises(BlockRuleViolation) as info:
            _decide(cascade, make())
        assert info.value.message == message, name
        assert CALLED == [], name  # nothing is evaluated
        assert GUARD.entries == 0, name
        assert labels.get_pending(REQUEST) is None, name  # nothing is stored
        assert labels.read("pick_action") == (), name
    # the same calls at the limits of those rules are accepted
    cascade, _ = _setup(tmp_path / "exact_size", settings=DecisionSettings(max_state_bytes=size))
    assert _decided(_decide(cascade, _call(rules=(first,)))).choice == "enlarge"
    cascade, _ = _setup(tmp_path / "exact_count", settings=DecisionSettings(max_options=2))
    assert _decided(_decide(cascade, _call(point=MEMBER, rules=(last,)))).choice == "1"


def test_first_matching_rule_wins(tmp_path: Path) -> None:
    """AC14: the first matching rule answers; later rules, providers and the engineer are not asked."""
    cascade, labels = _setup(tmp_path)
    answer = _decided(_decide(cascade, _call(rules=(never, first, second))))
    assert (answer.choice, answer.decided_by, answer.confidence) == ("enlarge", "rule:pick_action.first", None)
    assert answer.options == ("enlarge", "rebar")
    assert answer.state_sha256 == payload_sha256(STATE.model_dump(mode="json"))
    assert answer.latency_ms == 250  # two readings of the monotonic clock
    assert CALLED == ["never", "first"]  # the second rule is not called
    assert RATIOS == [0.5]  # the rule read its declared basis path
    assert GUARDED == [True]  # and ran inside the guard
    assert GUARD.entries == 2
    assert labels.get_pending(REQUEST) is None  # no engineer screen
    assert labels.read("pick_action") == ()  # and no label
    # a rule that does not match lets the next one decide
    CALLED.clear()
    later = _decided(_decide(cascade, _call(state=CALM, rules=(first, second), request_id=OTHER_REQUEST)))
    assert (later.choice, later.decided_by) == ("rebar", "rule:pick_action.second")
    assert CALLED == ["first", "second"]
    # reference options answer with an index
    by_index = _decided(_decide(cascade, _call(point=MEMBER, rules=(last,))))
    assert (by_index.choice, by_index.options, by_index.decided_by) == ("1", ("0", "1"), "rule:pick_member.last")


def test_bad_rule_fails_the_step(tmp_path: Path) -> None:
    """AC15: an invalid result or an error of a rule fails the step; later rules are not tried."""
    cascade, labels = _setup(tmp_path)
    invalid = "rule {} returned something that is not one of the options"
    cases = [
        (ACTION, bad_enum, invalid.format("pick_action.bad_enum")),
        (ACTION, bad_index, invalid.format("pick_action.bad_index")),
        (ACTION, bad_text, invalid.format("pick_action.bad_text")),
        (ACTION, bad_result, invalid.format("pick_action.bad_result")),
        (ACTION, raises, "rule pick_action.raises raised ValueError"),
        (MEMBER, high, invalid.format("pick_member.high")),
        (MEMBER, negative, invalid.format("pick_member.negative")),
        (MEMBER, flag, invalid.format("pick_member.flag")),
        (MEMBER, member, invalid.format("pick_member.member")),
    ]
    for point, bad, message in cases:
        CALLED.clear()
        call = _call(point=point, rules=(bad, second, last))
        with pytest.raises(DecisionInvalid) as info:
            _decide(cascade, call)
        assert info.value.message == message, bad.id
        assert info.value.evidence == (bad.id,), bad.id
        assert CALLED == [], bad.id  # the later rules were not tried
        assert labels.get_pending(REQUEST) is None, bad.id  # nothing fell through to the engineer
    assert _decided(_decide(cascade, _call(rules=(second,)))).decided_by == "rule:pick_action.second"


def test_phase1_rules_then_engineer(tmp_path: Path) -> None:
    """AC17 and AC34: no rule matches and no provider exists, so the engineer is asked, then answers."""
    cascade, labels = _setup(tmp_path)
    call = _call(state=CALM, rules=(first,))
    pending = _pending(_decide(cascade, call))
    assert (pending.request_id, pending.batch_id, pending.rejected) == (REQUEST, None, None)
    [item] = pending.screen.items
    assert (item.request_id, item.title, item.suggestions) == (REQUEST, "Pick an action", ())
    assert item.options == (
        ProviderOption(value="enlarge", label="enlarge"),
        ProviderOption(value="rebar", label="rebar"),
    )
    assert item.fields == (
        ScreenField(label="failing", value=False),
        ScreenField(label="cover_mm", value=50),
        ScreenField(label="result", ref=RES),  # a Ref field is shown as a reference (AC34)
    )
    stored = labels.get_pending(REQUEST)
    assert stored is not None
    assert (stored.screen, stored.batch_id, stored.outcomes, stored.closed_at) == (pending.screen, None, {}, None)
    assert labels.read("pick_action") == ()  # no label before the answer
    # the engineer answers
    answer = _decided(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("rebar")})))
    assert (answer.choice, answer.decided_by, answer.confidence) == ("rebar", "engineer:Engineer One", None)
    assert answer.latency_ms == 2500  # the answer time minus the creation of the pending request
    assert answer.options == ("enlarge", "rebar")
    assert answer.state_sha256 == payload_sha256(CALM.model_dump(mode="json"))
    assert answer.suggestions == ()
    [label] = labels.read("pick_action", 1)
    assert (label.request_id, label.run_id, label.step_path) == (REQUEST, "run_x", "0")
    assert (label.label, label.engineer, label.source) == ("rebar", "Engineer One", "engineer_decision")
    assert label.options == ("enlarge", "rebar")
    assert label.state == {"failing": False, "cover_mm": 50}  # the Ref field is not in the label
    assert label.state_sha256 == answer.state_sha256
    closed = labels.get_pending(REQUEST)
    assert closed is not None
    assert closed.closed_at is not None
    assert CALLED == ["first"]  # the answering call did not evaluate the rules again
    # reference options: the screen is labelled by the state's labels field
    refs = _call(point=MEMBER, request_id=OTHER_REQUEST)
    shown = _pending(_decide(cascade, refs))
    [member_item] = shown.screen.items
    assert member_item.options == (
        ProviderOption(value="0", label="Column C1"),
        ProviderOption(value="1", label="Column C2"),
    )
    assert member_item.fields == (
        ScreenField(label="members", value=["Column C1", "Column C2"]),
        ScreenField(label="result", ref=RES),
    )
    picked = _decided(_decide(cascade, refs.model_copy(update={"engineer_choice": _answer("1")})))
    assert (picked.choice, picked.decided_by, picked.options) == ("1", "engineer:Engineer One", ("0", "1"))


def test_invalid_engineer_choice(tmp_path: Path) -> None:
    """AC18: a choice that is no option returns the same pending request, rejected, and stores nothing."""
    cascade, labels = _setup(tmp_path)
    call = _call(state=CALM)
    first_screen = _pending(_decide(cascade, call))
    for bad in ("bogus", "ENLARGE", "enlarge ", "0", ""):
        refused = _pending(_decide(cascade, call.model_copy(update={"engineer_choice": _answer(bad)})))
        assert (refused.request_id, refused.rejected) == (REQUEST, "not_an_option"), bad
        assert refused.screen == first_screen.screen, bad
        assert refused.batch_id is None
    assert labels.read("pick_action") == ()  # nothing is stored
    stored = labels.get_pending(REQUEST)
    assert stored is not None
    assert stored.closed_at is None  # and the request stays open
    # reference options: only the indexes are options
    refs = _call(point=MEMBER, request_id=OTHER_REQUEST)
    _pending(_decide(cascade, refs))
    for bad in ("2", "-1", "01", "enlarge"):
        refused = _pending(_decide(cascade, refs.model_copy(update={"engineer_choice": _answer(bad)})))
        assert refused.rejected == "not_an_option", bad
    assert labels.read("pick_member") == ()
    # a refused choice before any request is stored returns the screen and stores nothing
    fresh = _call(state=CALM, request_id="dec_" + "c" * 32)
    early = _pending(_decide(cascade, fresh.model_copy(update={"engineer_choice": _answer("bogus")})))
    assert early.rejected == "not_an_option"
    assert early.screen.items[0].request_id == fresh.request_id
    assert labels.get_pending(fresh.request_id) is None
    # the right choice is then accepted
    assert (
        _decided(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("enlarge")}))).choice == "enlarge"
    )


def test_pending_is_idempotent(tmp_path: Path) -> None:
    """AC19: a stored request is returned as stored; once answered, the same answer comes back with one label."""
    cascade, labels = _setup(tmp_path)
    call = _call(state=CALM, rules=(first,))
    opened = _pending(_decide(cascade, call))
    assert CALLED == ["first"]
    # the stored screen is returned, not built again, and no rule is called again
    moved = _call(state=State(failing=False, cover_mm=60, result=REF), rules=(first,))
    again = _pending(_decide(cascade, moved))
    assert again == opened
    assert CALLED == ["first"]
    assert [f.value for f in again.screen.items[0].fields][:2] == [False, 50]
    # once answered, a further call returns the same answer
    answered = _decided(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("rebar")})))
    repeat = _decided(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("rebar")})))
    assert repeat == answered
    assert len(labels.read("pick_action")) == 1  # no second label
    # without a choice, or with another one, the recorded answer still comes back
    assert _decided(_decide(cascade, call)) == answered
    other = _decided(
        _decide(cascade, call.model_copy(update={"engineer_choice": _answer("enlarge", by="Engineer Two")}))
    )
    assert other == answered
    assert [(x.label, x.engineer) for x in labels.read("pick_action")] == [("rebar", "Engineer One")]
    assert CALLED == ["first"]


def test_rule_entry_has_hash(tmp_path: Path) -> None:
    """AC31: the entry of a rule decision holds the rule's code hash and version."""
    cascade, _ = _setup(tmp_path)
    answer = _decided(_decide(cascade, _call(rules=(first,))))
    assert answer.suggestions == (
        Suggestion(
            tier=1,
            by="rule:pick_action.first",
            outcome="accepted",
            choice="enlarge",
            confidence=None,
            rationale="Enlarge when the check fails.",
            latency_ms=250,
            shadow=False,
            code=SuggestionCode(rule_version=1, rule_sha256=first.code_sha256),
        ),
    )
    assert len(first.code_sha256) == 64
    versioned = _decided(_decide(cascade, _call(state=CALM, rules=(second,), request_id=OTHER_REQUEST)))
    [entry] = versioned.suggestions
    assert entry.code == SuggestionCode(rule_version=3, rule_sha256=second.code_sha256)
    assert entry.by == versioned.decided_by == "rule:pick_action.second"
    dumped = entry.model_dump(mode="json", by_alias=True)
    assert dumped["rationale"] == "Rebar is the fallback."
    assert dumped["code"] == {"rule_version": 3, "rule_sha256": second.code_sha256}


def test_label_state_is_hash_only_when_it_fails_the_check(tmp_path: Path) -> None:
    """AC36 through the cascade: sensitive values of the settings and of the call both make the label hash-only."""
    noted = Noted(note="Zeta Tower east", cover_mm=50)
    stored = {"note": "Zeta Tower east", "cover_mm": 50}
    cases = [
        (DecisionSettings(sensitive_values=("zeta tower",)), (), None),
        (DecisionSettings(), ("zeta tower",), None),
        (DecisionSettings(sensitive_values=("other site",)), ("another",), stored),
    ]
    for n, (settings, sensitive, expected) in enumerate(cases):
        cascade, labels = _setup(tmp_path / str(n), settings=settings)
        call = _call(point=NOTED, state=noted, sensitive=sensitive)
        _pending(_decide(cascade, call))
        answer = _decided(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("rebar")})))
        [label] = labels.read("pick_noted")
        assert label.state == expected, n
        assert label.state_sha256 == answer.state_sha256 == payload_sha256(stored), n


def test_screen_shows_nested_state_as_labeled_fields(tmp_path: Path) -> None:
    """AC34: references anywhere in the state are shown as references; quantities and tuples as values."""
    cascade, _ = _setup(tmp_path)
    other = Ref.model_validate({"$ref": f"{RES}#/fields/a/value"})
    wide = Wide(
        cover=Quantity(40.0, "mm"),
        inner=Inner(n=3, ref=REF),
        links=(REF, other),
        sizes=(Quantity(1.0, "m"),),
        tags=("A", "B"),
        extras=(),
    )
    [item] = _pending(_decide(cascade, _call(point=WIDE, state=wide))).screen.items
    assert item.fields == (
        ScreenField(label="cover", value={"value": 40.0, "unit": "mm"}),
        ScreenField(label="inner.n", value=3),
        ScreenField(label="inner.ref", ref=RES),
        ScreenField(label="links.0", ref=RES),
        ScreenField(label="links.1", ref=f"{RES}#/fields/a/value"),
        ScreenField(label="sizes.0", value={"value": 1.0, "unit": "m"}),
        ScreenField(label="tags", value=["A", "B"]),
        ScreenField(label="extras", value=[]),
    )


def test_engine_stops_and_basis_violations_pass_through(tmp_path: Path) -> None:
    """A rule reading an undeclared basis path is a BlockRuleViolation, and an engine stop is not an invalid rule."""
    cascade, labels = _setup(tmp_path)
    with pytest.raises(BlockRuleViolation) as info:
        _decide(cascade, _call(rules=(undeclared, second)))
    assert info.value.message == "basis path 'limits.other_ratio' is not in the rule's thresholds"
    assert GUARD.active is False  # the guard was left
    with pytest.raises(Pause):
        _decide(cascade, _call(rules=(stops, second)))
    assert GUARD.active is False
    assert CALLED == []
    assert labels.get_pending(REQUEST) is None


def test_choice_without_a_stored_request(tmp_path: Path) -> None:
    """A choice that arrives with no stored request is answered and labelled; latency is the monotonic one."""
    cascade, labels = _setup(tmp_path)
    answer = _decided(_decide(cascade, _call(state=CALM, rules=(first,), choice=_answer("rebar"))))
    assert (answer.choice, answer.decided_by, answer.latency_ms) == ("rebar", "engineer:Engineer One", 250)
    assert CALLED == ["first"]
    assert labels.get_pending(REQUEST) is None
    [label] = labels.read("pick_action")
    assert (label.label, label.created_at) == ("rebar", ANSWERED_AT)


def test_closing_and_label_times(tmp_path: Path) -> None:
    """The label is stamped with the answer time and the request is closed at the cascade clock's time."""
    cascade, labels = _setup(tmp_path)
    call = _call(state=CALM)
    _pending(_decide(cascade, call))
    _decided(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("rebar")})))
    [label] = labels.read("pick_action")
    assert label.created_at == ANSWERED_AT
    assert label.label_id.startswith("lbl_")
    assert len(label.label_id) == 36
    closed = labels.get_pending(REQUEST)
    assert closed is not None
    assert closed.closed_at == "2026-01-01T00:01:00.000Z"
    # an answer that is dated before the request was created has no negative latency
    early = _call(state=CALM, request_id=OTHER_REQUEST)
    _pending(_decide(cascade, early))
    stale = EngineerChoice(choice="rebar", by="Engineer One", answered_at="2025-12-31T23:59:59.000Z")
    assert _decided(_decide(cascade, early.model_copy(update={"engineer_choice": stale}))).latency_ms == 0


def test_label_write_failure_keeps_the_request_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC37: a failed label write fails the step and leaves the request presented."""
    cascade, labels = _setup(tmp_path)
    call = _call(state=CALM)
    _pending(_decide(cascade, call))

    def refuse(label: object, findings: object) -> None:
        raise StoreWriteError("decision store write failed: OperationalError", "inc_1")

    monkeypatch.setattr(labels, "append", refuse)
    with pytest.raises(StoreWriteError):
        _decide(cascade, call.model_copy(update={"engineer_choice": _answer("rebar")}))
    stored = labels.get_pending(REQUEST)
    assert stored is not None
    assert stored.closed_at is None
    monkeypatch.undo()
    assert _decided(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("rebar")}))).choice == "rebar"


def test_closed_request_without_a_label_is_asked_again(tmp_path: Path) -> None:
    """A closed request with no label (it cannot be answered from the store) goes to the engineer again."""
    cascade, labels = _setup(tmp_path)
    call = _call(state=CALM)
    opened = _pending(_decide(cascade, call))
    labels.close_pending(REQUEST, "2026-01-01T00:00:01.000Z")
    assert _pending(_decide(cascade, call)) == opened
    answer = _decided(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("rebar")})))
    assert answer.choice == "rebar"
    assert [x.label for x in labels.read("pick_action")] == ["rebar"]


def test_stored_request_keeps_its_batch_and_suggestions(tmp_path: Path) -> None:
    """A stored request is answered as stored: its batch id is kept, and its own suggestions go to the label."""
    cascade, labels = _setup(tmp_path)
    mine = Suggestion(
        tier=2,
        by="model:fake/fake-model@0",
        outcome="shadow",
        choice="enlarge",
        confidence=0.9,
        latency_ms=5,
        shadow=True,
    )
    theirs = mine.model_copy(update={"choice": "rebar"})
    options = (ProviderOption(value="enlarge", label="enlarge"), ProviderOption(value="rebar", label="rebar"))
    items = (
        ScreenItem(request_id=OTHER_REQUEST, title="Pick an action", options=options, suggestions=(theirs,)),
        ScreenItem(request_id=REQUEST, title="Pick an action", options=options, suggestions=(mine,)),
    )
    labels.open_pending(REQUEST, "batch_x", DecisionScreen(items=items), {})
    call = _call(state=CALM)
    assert _pending(_decide(cascade, call)).batch_id == "batch_x"
    refused = _pending(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("nope")})))
    assert (refused.batch_id, refused.rejected) == ("batch_x", "not_an_option")
    answer = _decided(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("rebar")})))
    assert answer.suggestions == (mine,)
    assert labels.read("pick_action")[0].suggestions == (mine,)


LLM_BY = "llm:fake/fake-model@0"
MODEL_BY = "model:fake/fake-model@0"
REMOTE = ProviderInfo(provider="remote", model="big", version="2", is_local=False, supports_batch=False)
RELEASE = ShadowRelease(point_version=1, basis="owner", record="owner decision 1")
RELEASED = DecisionSettings(shadow_released={"pick_action": RELEASE})
LIVE = DecisionPolicy(shadow=False)
BOTH = DecisionPolicy(llm=True)
BOTH_LIVE = DecisionPolicy(llm=True, shadow=False)
GOOD = LLMAnswer(choice="rebar", rationale="Rebar is the usual fix.")
OPTIONS = (ProviderOption(value="enlarge", label="enlarge"), ProviderOption(value="rebar", label="rebar"))


class Meeting:
    """Both providers must be inside their call at the same time, or neither of them returns."""

    def __init__(self) -> None:
        self.arrived = 0
        self.both = asyncio.Event()

    async def meet(self) -> None:
        self.arrived += 1
        if self.arrived == 2:
            self.both.set()
        await self.both.wait()


class MeetingModel(FakeDecisionProvider):
    def __init__(self, meeting: Meeting, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._meeting = meeting

    async def choose(self, request: ProviderRequest) -> ChoiceAnswer:
        await self._meeting.meet()
        return await super().choose(request)


class MeetingLLM(FakeLLMProvider):
    def __init__(self, meeting: Meeting, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._meeting = meeting

    async def decide(self, request: ProviderRequest) -> LLMAnswer:
        await self._meeting.meet()
        return await super().decide(request)


class StoppingModel(FakeDecisionProvider):
    async def choose(self, request: ProviderRequest) -> ChoiceAnswer:
        raise Pause("the run waits")


def _rid(n: int) -> str:
    return f"dec_{n:032x}"


def _suggestion(tier: int, outcome: str, **fields: Any) -> Suggestion:
    """The entry a fake provider with the default info leaves; ``latency_ms`` is 250 (two readings of the clock)."""
    by = MODEL_BY if tier == 2 else LLM_BY
    given: dict[str, Any] = {"tier": tier, "by": by, "outcome": outcome, "choice": None, "latency_ms": 250}
    given.setdefault("shadow", False)
    return Suggestion.model_validate(given | fields)


def _core(entry: Suggestion) -> tuple[object, ...]:
    """An entry without its timing."""
    return (
        entry.tier,
        entry.by,
        entry.outcome,
        entry.choice,
        entry.confidence,
        entry.reasoning,
        entry.shadow,
        entry.error,
    )


def test_shadow_needs_release(tmp_path: Path) -> None:
    """AC8: `policy.shadow=False` is not enough; without a release of this name and version, tiers 2 and 3 suggest."""
    other_version = RELEASE.model_copy(update={"point_version": 2})
    cases = [
        ({}, False, True),
        ({"pick_action": other_version}, False, True),
        ({"pick_flag": RELEASE}, False, True),
        ({"pick_action": RELEASE}, True, True),
        ({"pick_action": RELEASE}, False, False),
    ]
    for n, (released, shadow, effective) in enumerate(cases):
        model = FakeDecisionProvider(choices=[ChoiceAnswer(choice="enlarge", confidence=0.95)])
        settings = DecisionSettings(shadow_released=released)
        cascade, labels = _setup(tmp_path / str(n), settings=settings, model=model)
        result = _decide(cascade, _call(policy=DecisionPolicy(shadow=shadow)))
        assert len(model.requests) == 1, n  # the provider is consulted either way
        if effective:
            [item] = _pending(result).screen.items
            assert [_core(x) for x in item.suggestions] == [
                (2, MODEL_BY, "shadow", "enlarge", 0.95, None, True, None)
            ], n
            assert labels.get_pending(REQUEST) is not None, n
        else:
            answer = _decided(result)
            assert (answer.choice, answer.decided_by, answer.confidence) == ("enlarge", MODEL_BY, 0.95), n
            assert [x.shadow for x in answer.suggestions] == [False], n
            assert labels.get_pending(REQUEST) is None, n


def test_tier2_threshold(tmp_path: Path) -> None:
    """AC21: a rule decides before tier 2; a confidence at the threshold is taken, one below it is only recorded."""
    choices = [
        ChoiceAnswer(choice="enlarge", confidence=0.85),
        ChoiceAnswer(choice="enlarge", confidence=0.8499),
        ChoiceAnswer(choice="rebar", confidence=0.9),
        ChoiceAnswer(choice="rebar", confidence=0.89),
    ]
    model = FakeDecisionProvider(choices=choices)
    cascade, labels = _setup(tmp_path, settings=RELEASED, model=model)
    ruled = _decided(_decide(cascade, _call(rules=(first,), policy=LIVE)))
    assert ruled.decided_by == "rule:pick_action.first"  # tier 1 first, and only a rule that matches ends the cascade
    assert model.requests == []
    taken = _decided(_decide(cascade, _call(policy=LIVE, request_id=_rid(1))))
    assert (taken.choice, taken.decided_by, taken.confidence, taken.latency_ms) == ("enlarge", MODEL_BY, 0.85, 750)
    assert taken.options == ("enlarge", "rebar")
    assert taken.suggestions == (_suggestion(2, "accepted", choice="enlarge", confidence=0.85),)
    assert model.requests == [  # the state is sent without its Ref field (AC34)
        ProviderRequest(
            request_id=_rid(1),
            point="pick_action",
            point_version=1,
            options=OPTIONS,
            state={"failing": True, "cover_mm": 50},
        )
    ]
    assert labels.get_pending(_rid(1)) is None  # a model answer is no engineer label
    assert labels.read("pick_action") == ()
    below = _pending(_decide(cascade, _call(policy=LIVE, request_id=_rid(2))))
    [item] = below.screen.items
    assert item.suggestions == (_suggestion(2, "below_threshold", choice="enlarge", confidence=0.8499),)
    assert labels.get_pending(_rid(2)) is not None
    raised = DecisionPolicy(shadow=False, min_confidence=0.9)
    assert _decided(_decide(cascade, _call(policy=raised, request_id=_rid(3)))).choice == "rebar"
    [again] = _pending(_decide(cascade, _call(policy=raised, request_id=_rid(4)))).screen.items
    assert [_core(x) for x in again.suggestions] == [(2, MODEL_BY, "below_threshold", "rebar", 0.89, None, False, None)]


def test_yes_no_point_asks_yes_no(tmp_path: Path) -> None:
    """A point with `yes_no` is asked with `yes_no`, and the answer is the point's yes or no value (spec 4.7)."""
    model = FakeDecisionProvider(
        yes_nos=[YesNoAnswer(answer=True, confidence=0.9), YesNoAnswer(answer=False, confidence=0.95)]
    )
    settings = DecisionSettings(shadow_released={"pick_flag": RELEASE})
    cascade, _ = _setup(tmp_path, settings=settings, model=model)
    yes = _decided(_decide(cascade, _call(point=FLAG, request_id=_rid(1), policy=LIVE)))
    no = _decided(_decide(cascade, _call(point=FLAG, request_id=_rid(2), policy=LIVE)))
    assert [(x.choice, x.decided_by, x.confidence) for x in (yes, no)] == [
        ("yes", MODEL_BY, 0.9),
        ("no", MODEL_BY, 0.95),
    ]
    assert yes.options == ("yes", "no")


def test_provider_failures_fall_through(tmp_path: Path) -> None:
    """AC22: a timeout, an error or an invalid answer is a recorded outcome; nothing is raised; no message is kept."""
    nan = ChoiceAnswer.model_construct(choice="enlarge", confidence=float("nan"))
    infinite = ChoiceAnswer.model_construct(choice="enlarge", confidence=float("inf"))
    high = ChoiceAnswer.model_construct(choice="enlarge", confidence=1.5)
    negative = ChoiceAnswer.model_construct(choice="enlarge", confidence=-0.1)
    outside = ChoiceAnswer(choice="elsewhere", confidence=0.99)
    quick = DecisionPolicy(shadow=False, timeout_ms_model=1)
    cases: list[tuple[FakeDecisionProvider, DecisionPolicy, str, str | None]] = [
        (
            FakeDecisionProvider(choices=[ChoiceAnswer(choice="enlarge", confidence=0.99)], delay_s=5.0),
            quick,
            "timeout",
            "TimeoutError",
        ),
        (
            FakeDecisionProvider(choices=[ProviderError(ProviderErrorCode.TIMEOUT)]),
            LIVE,
            "timeout",
            "ProviderError:timeout",
        ),
        (
            FakeDecisionProvider(choices=[ProviderError(ProviderErrorCode.NETWORK)]),
            LIVE,
            "error",
            "ProviderError:network",
        ),
        (FakeDecisionProvider(choices=[RuntimeError("secret project text")]), LIVE, "error", "RuntimeError"),
        (FakeDecisionProvider(choices=[outside]), LIVE, "invalid", None),
        (FakeDecisionProvider(choices=[nan]), LIVE, "invalid", None),
        (FakeDecisionProvider(choices=[infinite]), LIVE, "invalid", None),
        (FakeDecisionProvider(choices=[high]), LIVE, "invalid", None),
        (FakeDecisionProvider(choices=[negative]), LIVE, "invalid", None),
    ]
    for n, (model, policy, outcome, error) in enumerate(cases):
        cascade, labels = _setup(tmp_path / str(n), settings=RELEASED, model=model)
        asked = _pending(_decide(cascade, _call(policy=policy)))  # the engineer is asked
        assert len(model.requests) == 1, n
        [item] = asked.screen.items
        assert item.suggestions == (_suggestion(2, outcome, error=error),), n
        assert "secret project text" not in asked.model_dump_json(), n
        assert labels.get_pending(REQUEST) is not None, n
    # a failed tier 2 does not end the cascade: tier 3 answers next, and both entries are kept in tier order
    model = FakeDecisionProvider(choices=[RuntimeError("secret project text")])
    llm = FakeLLMProvider(answers=[GOOD])
    cascade, _ = _setup(tmp_path / "next", settings=RELEASED, model=model, llm=llm)
    answer = _decided(_decide(cascade, _call(policy=BOTH_LIVE)))
    assert (answer.choice, answer.decided_by, answer.confidence, answer.latency_ms) == ("rebar", LLM_BY, None, 1250)
    assert answer.suggestions == (
        _suggestion(2, "error", error="RuntimeError"),
        _suggestion(3, "accepted", choice="rebar", reasoning="Rebar is the usual fix."),
    )
    # an engine stop is no provider failure and passes through
    cascade, labels = _setup(tmp_path / "stop", settings=RELEASED, model=StoppingModel())
    with pytest.raises(Pause):
        _decide(cascade, _call(policy=LIVE))
    assert labels.get_pending(REQUEST) is None


def test_tier3_rationale_and_option(tmp_path: Path) -> None:
    """AC23: an LLM answer with a valid option and a rationale is taken; a digit or an outside option is invalid."""
    digit = LLMAnswer.model_construct(choice="rebar", rationale="Add 2 bars.")
    outside = LLMAnswer(choice="elsewhere", rationale="No such option.")
    llm = FakeLLMProvider(answers=[GOOD, digit, outside, GOOD])
    cascade, labels = _setup(tmp_path, settings=RELEASED, llm=llm)  # no tier 2 provider: tier 2 is not accepted
    taken = _decided(_decide(cascade, _call(policy=BOTH_LIVE, request_id=_rid(1))))
    assert (taken.choice, taken.decided_by, taken.confidence, taken.latency_ms) == ("rebar", LLM_BY, None, 750)
    assert taken.suggestions == (_suggestion(3, "accepted", choice="rebar", reasoning="Rebar is the usual fix."),)
    assert llm.requests[0].options == OPTIONS
    for n in (2, 3):  # the invalid answers: the engineer is asked, and the entry keeps neither choice nor rationale
        asked = _pending(_decide(cascade, _call(policy=BOTH_LIVE, request_id=_rid(n))))
        [item] = asked.screen.items
        assert item.suggestions == (_suggestion(3, "invalid"),), n
        assert labels.get_pending(_rid(n)) is not None, n
    # tier 2 below its threshold goes on to tier 3
    model = FakeDecisionProvider(choices=[ChoiceAnswer(choice="enlarge", confidence=0.8)])
    cascade, _ = _setup(tmp_path / "both", settings=RELEASED, model=model, llm=FakeLLMProvider(answers=[GOOD]))
    answer = _decided(_decide(cascade, _call(policy=BOTH_LIVE)))
    assert (answer.choice, answer.decided_by) == ("rebar", LLM_BY)
    assert [_core(x) for x in answer.suggestions] == [
        (2, MODEL_BY, "below_threshold", "enlarge", 0.8, None, False, None),
        (3, LLM_BY, "accepted", "rebar", None, "Rebar is the usual fix.", False, None),
    ]


def test_shadow_mode(tmp_path: Path) -> None:
    """AC24: in shadow mode both providers run at the same time, only suggest, and the engineer is asked once."""
    meeting = Meeting()
    model = MeetingModel(meeting, choices=[ChoiceAnswer(choice="enlarge", confidence=1.0)])
    llm = MeetingLLM(meeting, answers=[GOOD])
    cascade, labels = _setup(tmp_path, model=model, llm=llm)
    call = _call(policy=BOTH)
    asked = _pending(_decide(cascade, call))
    [item] = asked.screen.items
    assert [_core(x) for x in item.suggestions] == [  # a confidence of 1.0 decides nothing in shadow mode
        (2, MODEL_BY, "shadow", "enlarge", 1.0, None, True, None),
        (3, LLM_BY, "shadow", "rebar", None, "Rebar is the usual fix.", True, None),
    ]
    assert (len(model.requests), len(llm.requests)) == (1, 1)
    assert labels.get_pending(REQUEST) is not None
    assert _pending(_decide(cascade, call)) == asked  # one prompt: asking again shows it, and asks no provider again
    assert (len(model.requests), len(llm.requests)) == (1, 1)
    answer = _decided(_decide(cascade, call.model_copy(update={"engineer_choice": _answer("enlarge")})))
    assert (answer.choice, answer.decided_by) == ("enlarge", "engineer:Engineer One")
    assert answer.suggestions == item.suggestions
    [label] = labels.read("pick_action")
    assert label.suggestions == item.suggestions


def test_policy_switches(tmp_path: Path) -> None:
    """AC25: `require_engineer` consults no provider and a switched-off tier is not called; each switch is paired."""
    model = FakeDecisionProvider(choices=[ChoiceAnswer(choice="enlarge", confidence=0.9)] * 3)
    llm = FakeLLMProvider(answers=[GOOD] * 3)
    cascade, _ = _setup(tmp_path, model=model, llm=llm)
    asked = _pending(
        _decide(cascade, _call(policy=DecisionPolicy(llm=True, require_engineer=True), request_id=_rid(1)))
    )
    assert (model.requests, llm.requests) == ([], [])
    assert asked.screen.items[0].suggestions == ()
    # the same cascade and the same providers with the switch off consult both of them
    on = _pending(_decide(cascade, _call(policy=BOTH, request_id=_rid(2))))
    assert (len(model.requests), len(llm.requests)) == (1, 1)
    assert [x.tier for x in on.screen.items[0].suggestions] == [2, 3]
    # `model=False`: only the language model is consulted
    only_llm = _pending(_decide(cascade, _call(policy=DecisionPolicy(model=False, llm=True), request_id=_rid(3))))
    assert (len(model.requests), len(llm.requests)) == (1, 2)
    assert [x.tier for x in only_llm.screen.items[0].suggestions] == [3]
    # `llm=False` (the default): only the model is consulted
    only_model = _pending(_decide(cascade, _call(policy=DecisionPolicy(), request_id=_rid(4))))
    assert (len(model.requests), len(llm.requests)) == (2, 2)
    assert [x.tier for x in only_model.screen.items[0].suggestions] == [2]


def test_local_only(tmp_path: Path) -> None:
    """AC26: with `local_only` a provider that is not local is not called and is recorded; a local one is called."""
    remote = FakeDecisionProvider(info=REMOTE, choices=[ChoiceAnswer(choice="enlarge", confidence=0.99)])
    llm = FakeLLMProvider(answers=[GOOD])
    settings = DecisionSettings(local_only=True, shadow_released={"pick_action": RELEASE})
    cascade, _ = _setup(tmp_path / "local", settings=settings, model=remote, llm=llm)
    answer = _decided(_decide(cascade, _call(policy=BOTH_LIVE)))
    assert remote.requests == []
    assert (answer.choice, answer.decided_by, answer.latency_ms) == ("rebar", LLM_BY, 750)
    assert answer.suggestions == (
        _suggestion(2, "skipped_local_only", by="model:remote/big@2", latency_ms=0),
        _suggestion(3, "accepted", choice="rebar", reasoning="Rebar is the usual fix."),
    )
    # in shadow mode the skipped entry is a shadow entry, and the local provider only suggests
    remote = FakeDecisionProvider(info=REMOTE, choices=[ChoiceAnswer(choice="enlarge", confidence=0.99)])
    cascade, _ = _setup(
        tmp_path / "shadow",
        settings=DecisionSettings(local_only=True),
        model=remote,
        llm=FakeLLMProvider(answers=[GOOD]),
    )
    [item] = _pending(_decide(cascade, _call(policy=BOTH))).screen.items
    assert [_core(x) for x in item.suggestions] == [
        (2, "model:remote/big@2", "skipped_local_only", None, None, None, True, None),
        (3, LLM_BY, "shadow", "rebar", None, "Rebar is the usual fix.", True, None),
    ]
    # the same provider is called when `local_only` is off
    remote = FakeDecisionProvider(info=REMOTE, choices=[ChoiceAnswer(choice="enlarge", confidence=0.99)])
    cascade, _ = _setup(tmp_path / "off", settings=RELEASED, model=remote)
    taken = _decided(_decide(cascade, _call(policy=LIVE)))
    assert (taken.choice, taken.decided_by) == ("enlarge", "model:remote/big@2")
    assert len(remote.requests) == 1


def test_redaction_skip(tmp_path: Path) -> None:
    """AC33: a state that fails the redaction check reaches no provider, whoever supplied the sensitive value."""
    noted = Noted(note="Zeta Tower east", cover_mm=50)
    clean = Noted(note="Plain note", cover_mm=50)
    cases = [(DecisionSettings(sensitive_values=("ZETA tower",)), ()), (DecisionSettings(), ("zeta TOWER",))]
    for n, (settings, sensitive) in enumerate(cases):
        model = FakeDecisionProvider(choices=[ChoiceAnswer(choice="enlarge", confidence=0.99)])
        llm = FakeLLMProvider(answers=[GOOD])
        cascade, labels = _setup(tmp_path / str(n), settings=settings, model=model, llm=llm)
        skipped = _pending(_decide(cascade, _call(point=NOTED, state=noted, sensitive=sensitive, policy=BOTH)))
        assert (model.requests, llm.requests) == ([], [])
        [item] = skipped.screen.items  # the engineer is asked, with both skips on the screen
        assert [(x.tier, x.by, x.outcome, x.choice, x.latency_ms, x.shadow, x.error) for x in item.suggestions] == [
            (2, MODEL_BY, "skipped_redaction", None, 0, True, None),
            (3, LLM_BY, "skipped_redaction", None, 0, True, None),
        ]
        assert "zeta" not in " ".join(x.model_dump_json().casefold() for x in item.suggestions)
        assert labels.get_pending(REQUEST) is not None
        # the same cascade sends a state that passes the check
        passed = _call(point=NOTED, state=clean, sensitive=sensitive, policy=BOTH, request_id=OTHER_REQUEST)
        [sent] = _pending(_decide(cascade, passed)).screen.items
        assert [x.outcome for x in sent.suggestions] == ["shadow", "shadow"]
        assert [r.state for r in model.requests] == [{"note": "Plain note", "cover_mm": 50}]
        assert len(llm.requests) == 1
