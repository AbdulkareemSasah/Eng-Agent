"""Cascade core: call validation, tier 1, the engineer tier, pending requests and the record.

Plan 0005 T7; spec 0005 AC5, AC14, AC15, AC17 to AC19, AC31 and AC34. No provider is configured (the phase 1
deployment); the rules run under a recording guard, and the monotonic clock steps a quarter of a second per reading.
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
from pydantic import BaseModel, ConfigDict

from eng_harness.ctx import BasisView
from eng_harness.decisions import Cascade, LabelStore, StoreWriteError
from eng_harness.decisions._points import DecisionPoint, Label, PointRegistry, Refs, decision_point
from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings
from eng_harness.decisions._record import DecisionScreen, ScreenField, ScreenItem, SuggestionCode
from eng_harness.decisions.interfaces import (
    DecisionAnswer,
    DecisionCall,
    EngineerChoice,
    PendingAnswer,
    ProviderOption,
    Suggestion,
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
def _reset() -> None:
    CALLED.clear()
    RATIOS.clear()
    GUARDED.clear()
    GUARD.entries = 0
    GUARD.active = False


def _view() -> BasisView:
    field = BasisField(
        value=0.5, unit="1", source="engineer:eng@2026-01-01T00:00:00.000Z", confirmed=True, citation=None
    )
    return BasisView(RES, DesignBasis(template=None, fields={"limits.bearing_ratio": field}), ("limits.bearing_ratio",))


def _setup(
    tmp_path: Path, *, settings: DecisionSettings | None = None, points: tuple[DecisionPoint, ...] | None = None
) -> tuple[Cascade, LabelStore]:
    settings = settings or DecisionSettings()
    clock = FixedClock(START_MS, 1)
    labels = LabelStore(tmp_path, settings, clock, SeededIdSource(b"labels", clock))
    cascade = Cascade(
        PointRegistry(points or (ACTION, MEMBER, NOTED, WIDE)),
        settings,
        labels,
        clock=FixedClock(START_MS + 60_000, 1),
        monotonic=Ticks(),
        rule_guard=GUARD,
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
        policy=DecisionPolicy(),
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
