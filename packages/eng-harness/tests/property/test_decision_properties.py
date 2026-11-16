"""Sensitive text never reaches a decision provider (spec 0005 AC33, section 4.10), whoever supplied it.

The text is a sensitive value given through the settings, through the call only (`DecisionCall.sensitive_values`) or
through both, and it is inside one or both labeled fields of the state. A state that passes the check does reach the
providers in the same run, so the absence of a request is not an artefact of a cascade that sends nothing.
"""

import asyncio
import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from enum import StrEnum
from pathlib import Path

from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.kinds.basis import DesignBasis
from fakes.decision_providers import FakeDecisionProvider, FakeLLMProvider
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ConfigDict

from eng_harness.ctx import BasisView
from eng_harness.decisions import Cascade, LabelStore
from eng_harness.decisions._points import Label, PointRegistry, decision_point
from eng_harness.decisions._policy import DecisionPolicy, DecisionSettings
from eng_harness.decisions.interfaces import ChoiceAnswer, DecisionCall, LLMAnswer, PendingAnswer

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
CLEAN = "plain note"


class Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class Notes(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    first: Label
    second: Label


POINT = decision_point(name="pick_notes", version=1, title="Pick with notes", options=Action, state=Notes)(object)

# A label has no control character and none of / \ @ : (spec 0005 AC2); the surrogates are not text.
_TEXT = st.text(
    alphabet=st.characters(codec="utf-8", exclude_categories=("Cc", "Cs"), exclude_characters="/\\@:"),
    min_size=3,
    max_size=12,
)


class _Counter:
    """A monotonic clock that steps a millisecond per reading."""

    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        self._now += 0.001
        return self._now


@contextmanager
def _cascade(
    folder: str, sensitive: tuple[str, ...], model: FakeDecisionProvider, llm: FakeLLMProvider
) -> Iterator[Cascade]:
    clock = FixedClock(START_MS, 1)
    config = DecisionSettings(sensitive_values=sensitive)
    labels = LabelStore(Path(folder), config, clock, SeededIdSource(b"labels", clock))
    try:
        yield Cascade(
            PointRegistry((POINT,)),
            config,
            labels,
            clock=clock,
            monotonic=_Counter(),
            rule_guard=nullcontext,
            model=model,
            llm=llm,
        )
    finally:
        labels.close()


def _call(request_id: str, state: Notes, sensitive: tuple[str, ...]) -> DecisionCall:
    return DecisionCall(
        request_id=request_id,
        run_id="run_x",
        step_path="0",
        point=POINT,
        options=Action,
        state=state,
        rules=(),
        policy=DecisionPolicy(llm=True),
        basis=BasisView("res_01ARZ3NDEKTSV4RRFFQ69G5FAV", DesignBasis(template=None, fields={}), ()),
        sensitive_values=sensitive,
    )


@settings(derandomize=True, max_examples=100, deadline=None)
@given(
    text=_TEXT,
    source=st.sampled_from(["settings", "call", "both"]),
    place=st.sampled_from(["first", "second", "both"]),
)
def test_sensitive_text_never_reaches_a_provider(text: str, source: str, place: str) -> None:
    assume(text.casefold() not in CLEAN.casefold())  # the state that passes must really pass
    from_settings = (text,) if source in ("settings", "both") else ()
    from_call = (text,) if source in ("call", "both") else ()
    leaky = f"a {text} b"
    state = Notes(first=leaky if place in ("first", "both") else CLEAN, second=leaky if place != "first" else CLEAN)
    model = FakeDecisionProvider(choices=[ChoiceAnswer(choice="enlarge", confidence=0.99)])
    llm = FakeLLMProvider(answers=[LLMAnswer(choice="rebar", rationale="Rebar is the usual fix.")])
    with tempfile.TemporaryDirectory() as folder, _cascade(folder, from_settings, model, llm) as cascade:
        skipped = asyncio.run(cascade.decide(_call("dec_" + "1" * 32, state, from_call)))
        assert isinstance(skipped, PendingAnswer)
        assert [x.outcome for x in skipped.screen.items[0].suggestions] == ["skipped_redaction"] * 2
        assert (model.requests, llm.requests) == ([], [])
        # a state that passes the check does reach both providers, and nothing of the text is in what they receive
        passed = asyncio.run(cascade.decide(_call("dec_" + "2" * 32, Notes(first=CLEAN, second=CLEAN), from_call)))
        assert isinstance(passed, PendingAnswer)
        assert [x.outcome for x in passed.screen.items[0].suggestions] == ["shadow"] * 2
        assert (len(model.requests), len(llm.requests)) == (1, 1)
        states = [json.dumps(r.state, ensure_ascii=False).casefold() for r in (*model.requests, *llm.requests)]
        assert all(text.casefold() not in state for state in states)
