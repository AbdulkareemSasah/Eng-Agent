"""The decision cascade, core: validation, tier 1 (rules), the engineer tier and the record (spec 0005 section 4.5).

Purpose: ``Cascade.decide`` answers one call from the first matching rule, or stores a pending request for the engineer
and, when the engineer's choice comes back, appends the label and answers. Provider tiers are absent here (phase 1).
Units: ``latency_ms`` in milliseconds; the monotonic clock reads seconds. Errors: ``BlockRuleViolation`` for a call that
does not fit its point, ``DecisionInvalid`` for a rule that returns an invalid result or raises, ``StoreWriteError``
from the label store (the pending request stays presented).
"""

import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from typing import Any

from eng_contract.canonical import payload_sha256
from eng_contract.ids import Clock, Timestamp
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref
from pydantic import BaseModel, TypeAdapter

from eng_harness.decisions._labels import LabeledExample, LabelStore, PendingRecord
from eng_harness.decisions._points import PointRegistry, Refs, check_state_size
from eng_harness.decisions._policy import DecisionSettings
from eng_harness.decisions._record import (
    DecisionAnswer,
    DecisionCall,
    DecisionScreen,
    PendingAnswer,
    ProviderOption,
    ScreenField,
    ScreenItem,
    Suggestion,
    SuggestionCode,
)
from eng_harness.decisions._redaction import check_state, outgoing_state
from eng_harness.decisions._rules import Rule, RuleBasis
from eng_harness.decisions.types import Pick
from eng_harness.errors import BlockRuleViolation, DecisionInvalid

__all__ = ["Cascade"]

_MILLISECOND = timedelta(milliseconds=1)
_JSON: TypeAdapter[Any] = TypeAdapter(Any)


def _values(call: DecisionCall) -> tuple[str, ...]:
    """The option values: the members' values, or ``"0"`` to ``"n-1"`` for references."""
    if isinstance(call.options, type):
        return tuple(str(member.value) for member in call.options)
    return tuple(str(index) for index in range(len(call.options)))


def _between(first: Timestamp, last: Timestamp) -> int:
    """Milliseconds from ``first`` to ``last``, never below zero."""
    return max(0, (datetime.fromisoformat(last) - datetime.fromisoformat(first)) // _MILLISECOND)


def _fields(model: BaseModel, prefix: str = "") -> list[ScreenField]:
    """The state as labeled fields in model order; a ``Ref`` is a reference, a nested model or tuple is walked."""
    shown: list[ScreenField] = []
    for name in type(model).model_fields:
        shown += _field(prefix + name, getattr(model, name))
    return shown


def _field(label: str, value: object) -> list[ScreenField]:
    if isinstance(value, Ref):
        return [ScreenField(label=label, ref=value.ref)]
    if isinstance(value, BaseModel) and not isinstance(value, Quantity):
        return _fields(value, label + ".")
    if isinstance(value, tuple) and any(isinstance(item, Ref | BaseModel) for item in value):
        return [shown for index, item in enumerate(value) for shown in _field(f"{label}.{index}", item)]
    return [ScreenField(label=label, value=_JSON.dump_python(value, mode="json"))]


class Cascade:
    """The decision cascade of one run (spec 0005 section 4.5): rules, then the engineer."""

    def __init__(
        self,
        points: PointRegistry,
        settings: DecisionSettings,
        labels: LabelStore,
        *,
        clock: Clock,
        monotonic: Callable[[], float],
        rule_guard: Callable[[], AbstractContextManager[object]],
    ) -> None:
        """Build the cascade.

        ``monotonic`` reads seconds; ``rule_guard`` is the factory of the context manager that rules run in (the
        engine supplies its audit-hook guard, unit tests a no-op); ``clock`` stamps the closing of a request.
        """
        self._points, self._settings, self._labels = points, settings, labels
        self._clock, self._monotonic, self._guard = clock, monotonic, rule_guard

    async def decide(self, call: DecisionCall) -> DecisionAnswer | PendingAnswer:
        """Decide one call: the first matching rule, else the engineer (a call with an ``engineer_choice`` answers).

        Raises:
            BlockRuleViolation: the call does not fit its point (AC5); a rule read an undeclared basis path.
            DecisionInvalid: a rule returned an invalid result or raised (AC15).
            StoreWriteError: the label or pending write failed.
        """
        started = self._monotonic()
        self._validate(call)
        values = _values(call)
        sha = payload_sha256(call.state.model_dump(mode="json"))
        pending = self._labels.get_pending(call.request_id)
        if pending is not None and pending.closed_at is not None and (given := self._recorded(call, pending)):
            return given
        if pending is None and (by_rule := self._rules(call, values, sha, started)) is not None:
            return by_rule
        return self._engineer(call, values, sha, pending, started)

    def _validate(self, call: DecisionCall) -> None:
        """AC5: the point is registered as given, options and state fit it and the state is not too large."""
        point = call.point
        if self._points.get(point.name) != point:
            raise BlockRuleViolation(f"{point.name!r} is not a registered decision point")
        if not isinstance(call.state, point.state):
            raise BlockRuleViolation(f"the state of {point.name!r} is not a {point.state.__name__}")
        limit = self._settings.max_options
        if isinstance(point.options, Refs):
            labels = getattr(call.state, point.options.labels_field)
            if (
                isinstance(call.options, type)
                or not 1 <= len(call.options) <= limit
                or len(call.options) != len(labels)
            ):
                raise BlockRuleViolation(
                    f"the options of {point.name!r} must be 1 to {limit} references, one for each label"
                )
        elif call.options is not point.options:
            raise BlockRuleViolation(f"the options of {point.name!r} differ from the point's")
        check_state_size(point.name, call.state, self._settings.max_state_bytes)

    def _elapsed_ms(self, started: float) -> int:
        return max(0, round((self._monotonic() - started) * 1000))

    def _rules(self, call: DecisionCall, values: tuple[str, ...], sha: str, started: float) -> DecisionAnswer | None:
        """Tier 1: the first rule that returns a ``Pick`` answers; a rule that returns ``None`` lets the next run."""
        for rule in call.rules:
            result = self._run(rule, call)
            if result is None:
                continue
            choice = self._chosen(call, result)
            if choice is None:
                raise DecisionInvalid(
                    f"rule {rule.id} returned something that is not one of the options", evidence=[rule.id]
                )
            by, latency = f"rule:{rule.id}", self._elapsed_ms(started)
            entry = Suggestion(
                tier=1, by=by, outcome="accepted", choice=choice, rationale=rule.rationale, latency_ms=latency,
                shadow=False, code=SuggestionCode(rule_version=rule.version, rule_sha256=rule.code_sha256),
            )  # fmt: skip
            return DecisionAnswer(
                choice=choice, decided_by=by, latency_ms=latency, options=values, state_sha256=sha, suggestions=(entry,)
            )
        return None

    def _run(self, rule: Rule, call: DecisionCall) -> object:
        """Run one rule inside the guard; an error of the rule is ``DecisionInvalid`` (the engine's stops pass)."""
        try:
            with self._guard():
                return rule.fn(call.state, RuleBasis(call.basis, rule.thresholds))
        except Exception as error:
            raise DecisionInvalid(f"rule {rule.id} raised {type(error).__name__}", evidence=[rule.id]) from error

    @staticmethod
    def _chosen(call: DecisionCall, result: object) -> str | None:
        """The choice a rule's result names: a member of the options enum, or an index into the references."""
        if not isinstance(result, Pick):
            return None
        option = result.option
        if isinstance(call.options, type):
            return str(option.value) if isinstance(option, call.options) else None
        return str(option) if type(option) is int and 0 <= option < len(call.options) else None

    def _screen(self, call: DecisionCall, values: tuple[str, ...]) -> DecisionScreen:
        """The engineer's screen: title, options with labels, the state as labeled fields (no suggestions yet)."""
        point = call.point
        if isinstance(point.options, Refs):
            names = getattr(call.state, point.options.labels_field)
            shown = tuple(ProviderOption(value=value, label=names[int(value)]) for value in values)
        else:
            shown = tuple(ProviderOption(value=value, label=value) for value in values)
        item = ScreenItem(
            request_id=call.request_id, title=point.title, options=shown, fields=tuple(_fields(call.state))
        )
        return DecisionScreen(items=(item,))

    def _engineer(
        self, call: DecisionCall, values: tuple[str, ...], sha: str, pending: PendingRecord | None, started: float
    ) -> DecisionAnswer | PendingAnswer:
        """Tier 4: present the request, or validate the engineer's choice, append the label and answer."""
        screen = pending.screen if pending is not None else self._screen(call, values)
        batch = pending.batch_id if pending is not None else None
        given = call.engineer_choice
        if given is None:
            if pending is None:
                self._labels.open_pending(call.request_id, batch, screen, {})
            return PendingAnswer(request_id=call.request_id, batch_id=batch, screen=screen)
        if given.choice not in values:
            return PendingAnswer(request_id=call.request_id, batch_id=batch, screen=screen, rejected="not_an_option")
        suggestions = tuple(s for item in screen.items if item.request_id == call.request_id for s in item.suggestions)
        state = outgoing_state(call.state)
        label = LabeledExample(
            label_id="lbl_" + hashlib.sha256(call.request_id.encode()).hexdigest()[:32], request_id=call.request_id,
            point=call.point.name, point_version=call.point.version, run_id=call.run_id, step_path=call.step_path,
            options=values, state=state, state_sha256=sha, label=given.choice, engineer=given.by,
            suggestions=suggestions, source="engineer_decision", created_at=given.answered_at,
        )  # fmt: skip
        findings = check_state(state, (*self._settings.sensitive_values, *call.sensitive_values))
        self._labels.append(label, findings)
        if pending is not None:
            self._labels.close_pending(call.request_id, self._clock.now())
        latency = _between(pending.created_at, given.answered_at) if pending is not None else self._elapsed_ms(started)
        return DecisionAnswer(
            choice=given.choice, decided_by=f"engineer:{given.by}", latency_ms=latency, options=values,
            state_sha256=sha, suggestions=suggestions,
        )  # fmt: skip

    def _recorded(self, call: DecisionCall, pending: PendingRecord) -> DecisionAnswer | None:
        """The answer already recorded for a closed request, from its label; ``None`` when there is no label."""
        point = call.point
        label = next((x for x in self._labels.read(point.name, point.version) if x.request_id == call.request_id), None)
        if label is None:
            return None
        latency = _between(pending.created_at, label.created_at)
        return DecisionAnswer(
            choice=label.label, decided_by=f"engineer:{label.engineer}", latency_ms=latency, options=label.options,
            state_sha256=label.state_sha256, suggestions=label.suggestions,
        )  # fmt: skip
