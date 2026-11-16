"""The decision cascade: validation, tier 1 (rules), tiers 2 and 3 (providers), the engineer tier and the record.

Purpose (spec 0005 sections 4.5 and 4.6): ``Cascade.decide`` answers one call from the first matching rule, else from
a provider whose answer is accepted (never while the point is in shadow mode), else it stores a pending request for the
engineer, with the providers' suggestions on its screen, and when the engineer's choice comes back appends the label and
answers. A state that fails the redaction check, or a provider that is not local under ``local_only``, is never sent.
Units: ``latency_ms`` in milliseconds; the monotonic clock reads seconds; a confidence is a ratio in [0, 1];
``DecisionPolicy`` timeouts are milliseconds. Errors: ``BlockRuleViolation`` for a call that does not fit its point,
``DecisionInvalid`` for a rule that returns an invalid result or raises, ``StoreWriteError`` from the label store (the
pending request stays presented). A provider that fails, times out or answers badly is a recorded suggestion, never an
error; the engine's stops and cancellation pass through.
"""

import asyncio
import hashlib
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from functools import partial
from typing import Any, Literal, NamedTuple

from eng_contract.canonical import payload_sha256
from eng_contract.ids import Clock, Timestamp
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref
from pydantic import BaseModel, TypeAdapter, ValidationError

from eng_harness.decisions._batch import batch_id, bounded, refusal, restored, stored
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
from eng_harness.decisions._redaction import RedactionFinding, check_state, outgoing_state
from eng_harness.decisions._rules import Rationale, Rule, RuleBasis
from eng_harness.decisions.interfaces import (
    DecisionProvider,
    LLMProvider,
    ProviderError,
    ProviderErrorCode,
    ProviderFailure,
    ProviderInfo,
    ProviderRequest,
)
from eng_harness.decisions.types import Pick
from eng_harness.errors import BlockRuleViolation, DecisionInvalid

__all__ = ["Cascade"]

_MILLISECOND = timedelta(milliseconds=1)
_JSON: TypeAdapter[Any] = TypeAdapter(Any)
_RATIONALE: TypeAdapter[str] = TypeAdapter(Rationale)
_Outcome = Literal[
    "accepted",
    "below_threshold",
    "shadow",
    "invalid",
    "error",
    "timeout",
    "skipped_local_only",
    "skipped_redaction",
]
_Ask = Callable[[ProviderRequest], Awaitable[tuple[str, float | str]]]


class _Tier(NamedTuple):
    """A provider tier that the policy allows: 2 (the model) or 3 (the language model), how to ask it, its timeout."""

    number: Literal[2, 3]
    info: ProviderInfo
    ask: _Ask
    timeout_ms: int


class _Outgoing(NamedTuple):
    """What may leave the machine: the state without its ``Ref`` fields and the redaction findings over it."""

    state: dict[str, Any]
    findings: tuple[RedactionFinding, ...]


async def _choose(
    model: DecisionProvider, yes_no: tuple[str, str] | None, request: ProviderRequest
) -> tuple[str, float | str]:
    """Ask tier 2: the choice and its confidence; a yes/no point is asked with ``yes_no`` and answers its yes or no."""
    if yes_no is None:
        picked = await model.choose(request)
        return picked.choice, picked.confidence
    said = await model.yes_no(request)
    return (yes_no[0] if said.answer else yes_no[1]), said.confidence


async def _reason(llm: LLMProvider, request: ProviderRequest) -> tuple[str, float | str]:
    """Ask tier 3: the choice and its rationale."""
    said = await llm.decide(request)
    return said.choice, said.rationale


def _suggestion(
    tier: Literal[2, 3],
    info: ProviderInfo,
    outcome: _Outcome,
    shadow: bool,
    **fields: Any,
) -> Suggestion:
    """The entry of a provider tier (spec 0005 section 4.9); ``by`` names the tier kind and the provider."""
    kind = "model" if tier == 2 else "llm"
    by = f"{kind}:{info.provider}/{info.model}@{info.version}"
    return Suggestion.model_validate(
        {"tier": tier, "by": by, "outcome": outcome, "shadow": shadow, "choice": None, "latency_ms": 0} | fields
    )


def _failure(error: Exception) -> tuple[Literal["timeout", "error"], str]:
    """The outcome and the recorded error of a failed call: class name and code, never the message (AC22)."""
    if isinstance(error, ProviderError):
        return (
            "timeout" if error.code is ProviderErrorCode.TIMEOUT else "error"
        ), f"{type(error).__name__}:{error.code.value}"
    return ("timeout" if isinstance(error, TimeoutError) else "error"), type(error).__name__


def _failed(tier: Literal[2, 3], info: ProviderInfo, error: Exception, shadow: bool, latency: int) -> Suggestion:
    """The entry of a provider call that failed (AC22)."""
    outcome, name = _failure(error)
    return _suggestion(tier, info, outcome, shadow, error=name, latency_ms=latency)


def _reasoning(raw: object) -> str | None:
    """The rationale when it is a ``Rationale`` (no digit), else ``None``."""
    try:
        return _RATIONALE.validate_python(raw)
    except ValidationError:
        return None


def _model_entry(
    info: ProviderInfo,
    choice: str,
    confidence: object,
    values: tuple[str, ...],
    shadow: bool,
    minimum: float,
    latency: int,
) -> Suggestion:
    """Judge a tier 2 answer: an option and a finite confidence in [0, 1] (AC22); then the threshold decides (AC21)."""
    if choice not in values or not (
        isinstance(confidence, float) and math.isfinite(confidence) and 0.0 <= confidence <= 1.0
    ):
        return _suggestion(2, info, "invalid", shadow, latency_ms=latency)
    outcome: _Outcome = "shadow" if shadow else ("accepted" if confidence >= minimum else "below_threshold")
    return _suggestion(2, info, outcome, shadow, choice=choice, confidence=confidence, latency_ms=latency)


def _llm_entry(
    info: ProviderInfo, choice: str, rationale: object, values: tuple[str, ...], shadow: bool, latency: int
) -> Suggestion:
    """Judge a tier 3 answer: an option and a ``Rationale`` (AC23)."""
    reasoning = _reasoning(rationale)
    if choice not in values or reasoning is None:
        return _suggestion(3, info, "invalid", shadow, latency_ms=latency)
    return _suggestion(
        3, info, "shadow" if shadow else "accepted", shadow, choice=choice, rationale=reasoning, latency_ms=latency
    )


def _sha(call: DecisionCall) -> str:
    """The hash of the call's state, as recorded in the answer and the label."""
    return payload_sha256(call.state.model_dump(mode="json"))


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
    """The decision cascade of one run (spec 0005 section 4.5): rules, the providers, then the engineer."""

    def __init__(
        self,
        points: PointRegistry,
        settings: DecisionSettings,
        labels: LabelStore,
        *,
        clock: Clock,
        monotonic: Callable[[], float],
        rule_guard: Callable[[], AbstractContextManager[object]],
        model: DecisionProvider | None = None,
        llm: LLMProvider | None = None,
        max_concurrent_decisions: int = 4,
    ) -> None:
        """Build the cascade.

        ``monotonic`` reads seconds; ``rule_guard`` is the factory of the context manager that rules run in (the
        engine supplies its audit-hook guard, unit tests a no-op); ``clock`` stamps the closing of a request;
        ``model`` (tier 2) and ``llm`` (tier 3) are the providers, both ``None`` in phase 1;
        ``max_concurrent_decisions`` bounds the single provider calls of ``decide_many`` (the engine's setting).
        """
        self._points, self._settings, self._labels = points, settings, labels
        self._clock, self._monotonic, self._guard = clock, monotonic, rule_guard
        self._model, self._llm, self._limit = model, llm, max_concurrent_decisions

    async def decide(self, call: DecisionCall) -> DecisionAnswer | PendingAnswer:
        """Decide one call: the first matching rule, else an accepted provider answer, else the engineer.

        A call with an ``engineer_choice`` answers with it and consults no provider.

        Raises:
            BlockRuleViolation: the call does not fit its point (AC5); a rule read an undeclared basis path.
            DecisionInvalid: a rule returned an invalid result or raised (AC15).
            StoreWriteError: the label or pending write failed.
        """
        started = self._monotonic()
        self._validate(call)
        values = _values(call)
        sha = _sha(call)
        pending = self._labels.get_pending(call.request_id)
        if pending is not None and pending.closed_at is not None and (given := self._recorded(call, pending)):
            return given
        if pending is None and (by_rule := self._rules(call, values, sha, started)) is not None:
            return by_rule
        sent = self._outgoing(call)
        tried: tuple[Suggestion, ...] = ()
        if pending is None and call.engineer_choice is None and not call.policy.require_engineer:
            tried = await self._providers(call, values, sent)
            if (by_provider := self._by_provider(tried, values, sha, started)) is not None:
                return by_provider
        return self._engineer(call, values, sha, pending, started, tried, sent)

    def _outgoing(self, call: DecisionCall) -> _Outgoing:
        """The state that may leave the machine and the redaction findings over the settings' and the call's values."""
        state = outgoing_state(call.state)
        return _Outgoing(state, check_state(state, (*self._settings.sensitive_values, *call.sensitive_values)))

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

    @staticmethod
    def _options(call: DecisionCall, values: tuple[str, ...]) -> tuple[ProviderOption, ...]:
        """The options with their labels: the values themselves, or the state's labels for references."""
        point = call.point
        if isinstance(point.options, Refs):
            names = getattr(call.state, point.options.labels_field)
            return tuple(ProviderOption(value=value, label=names[int(value)]) for value in values)
        return tuple(ProviderOption(value=value, label=value) for value in values)

    def _screen(
        self, call: DecisionCall, values: tuple[str, ...], suggestions: tuple[Suggestion, ...]
    ) -> DecisionScreen:
        """The engineer's screen: title, options with labels, the state as labeled fields, the providers' entries."""
        item = ScreenItem(
            request_id=call.request_id,
            title=call.point.title,
            options=self._options(call, values),
            fields=tuple(_fields(call.state)),
            suggestions=suggestions,
        )
        return DecisionScreen(items=(item,))

    def _shadowed(self, call: DecisionCall) -> bool:
        """Effective shadow (spec 4.3): ``policy.shadow``, or no release for this point name and version (AC8)."""
        release = self._settings.shadow_released.get(call.point.name)
        return call.policy.shadow or release is None or release.point_version != call.point.version

    def _tiers(self, call: DecisionCall) -> list[_Tier]:
        """The provider tiers present and allowed by the policy, tier 2 first (AC25)."""
        policy, tiers = call.policy, []
        if (model := self._model) is not None and policy.model:
            tiers.append(_Tier(2, model.info, partial(_choose, model, call.point.yes_no), policy.timeout_ms_model))
        if (llm := self._llm) is not None and policy.llm:
            tiers.append(_Tier(3, llm.info, partial(_reason, llm), policy.timeout_ms_llm))
        return tiers

    def _request(self, call: DecisionCall, values: tuple[str, ...], sent: _Outgoing) -> ProviderRequest:
        """The only data a provider receives for ``call``."""
        return ProviderRequest(
            request_id=call.request_id,
            point=call.point.name,
            point_version=call.point.version,
            options=self._options(call, values),
            state=sent.state,
        )

    async def _providers(self, call: DecisionCall, values: tuple[str, ...], sent: _Outgoing) -> tuple[Suggestion, ...]:
        """Tiers 2 and 3 (spec 4.5 step 5): the entries in tier order, the last one accepted when a provider decided.

        In shadow mode the allowed tiers run at the same time and nothing is accepted; otherwise tier 2 runs first and
        tier 3 only when tier 2 is not accepted.
        """
        shadow = self._shadowed(call)
        request = self._request(call, values, sent)

        def ask(tier: _Tier) -> Awaitable[Suggestion]:
            return self._tier(tier, request, values, sent, shadow, call.policy.min_confidence)

        if shadow:
            return tuple(await asyncio.gather(*(ask(tier) for tier in self._tiers(call))))
        entries: list[Suggestion] = []
        for tier in self._tiers(call):
            entries.append(await ask(tier))
            if entries[-1].outcome == "accepted":
                break
        return tuple(entries)

    def _skipped(self, tier: _Tier, sent: _Outgoing, shadow: bool) -> Suggestion | None:
        """The entry of a provider that is not called: not local under ``local_only``, or a failing state."""
        if self._settings.local_only and not tier.info.is_local:
            return _suggestion(tier.number, tier.info, "skipped_local_only", shadow)
        if sent.findings:
            return _suggestion(tier.number, tier.info, "skipped_redaction", shadow)
        return None

    async def _tier(
        self,
        tier: _Tier,
        request: ProviderRequest,
        values: tuple[str, ...],
        sent: _Outgoing,
        shadow: bool,
        minimum: float,
    ) -> Suggestion:
        """One provider call as an entry: a skip (AC26, AC33), a failure (AC22) or a judged answer."""
        if (skipped := self._skipped(tier, sent, shadow)) is not None:
            return skipped
        began = self._monotonic()
        try:
            async with asyncio.timeout(tier.timeout_ms / 1000):
                choice, extra = await tier.ask(request)
        except Exception as error:
            return _failed(tier.number, tier.info, error, shadow, self._elapsed_ms(began))
        latency = self._elapsed_ms(began)
        if tier.number == 2:
            return _model_entry(tier.info, choice, extra, values, shadow, minimum, latency)
        return _llm_entry(tier.info, choice, extra, values, shadow, latency)

    def _by_provider(
        self, tried: tuple[Suggestion, ...], values: tuple[str, ...], sha: str, started: float
    ) -> DecisionAnswer | None:
        """The answer of the provider tier that was accepted (the last entry), else ``None``."""
        last = tried[-1] if tried else None
        if last is None or last.outcome != "accepted" or last.choice is None:
            return None
        return DecisionAnswer(
            choice=last.choice, decided_by=last.by, confidence=last.confidence, latency_ms=self._elapsed_ms(started),
            options=values, state_sha256=sha, suggestions=tried,
        )  # fmt: skip

    def _engineer(
        self,
        call: DecisionCall,
        values: tuple[str, ...],
        sha: str,
        pending: PendingRecord | None,
        started: float,
        tried: tuple[Suggestion, ...],
        sent: _Outgoing,
    ) -> DecisionAnswer | PendingAnswer:
        """Tier 4: present the request (with the entries of ``tried``), or validate the choice, label and answer."""
        screen = pending.screen if pending is not None else self._screen(call, values, tried)
        batch = pending.batch_id if pending is not None else None
        given = call.engineer_choice
        if given is None:
            if pending is None:
                self._labels.open_pending(call.request_id, batch, screen, {})
            return PendingAnswer(request_id=call.request_id, batch_id=batch, screen=screen)
        if given.choice not in values:
            return PendingAnswer(request_id=call.request_id, batch_id=batch, screen=screen, rejected="not_an_option")
        suggestions = tuple(s for item in screen.items if item.request_id == call.request_id for s in item.suggestions)
        label = LabeledExample(
            label_id="lbl_" + hashlib.sha256(call.request_id.encode()).hexdigest()[:32], request_id=call.request_id,
            point=call.point.name, point_version=call.point.version, run_id=call.run_id, step_path=call.step_path,
            options=values, state=sent.state, state_sha256=sha, label=given.choice, engineer=given.by,
            suggestions=suggestions, source="engineer_decision", created_at=given.answered_at,
        )  # fmt: skip
        self._labels.append(label, sent.findings)
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

    async def decide_many(self, calls: Sequence[DecisionCall]) -> list[DecisionAnswer | PendingAnswer]:
        """Decide the calls of one step (spec 4.8): rules for each call, then the providers, then one screen.

        The unresolved calls share one batch id and one screen, which each stored request keeps with the outcomes of
        the resolved calls, so a repeated call returns them and asks no provider again (AC29). The engineer's choices
        are taken for all open requests of the batch or for none (AC28). The result has one entry per call, in order.

        Raises:
            BlockRuleViolation: a call does not fit its point (AC5); nothing has been evaluated or stored.
            DecisionInvalid: a rule returned an invalid result or raised (AC15).
            StoreWriteError: the label or pending write failed.
        """
        for call in calls:
            self._validate(call)
        rows = {c.request_id: row for c in calls if (row := self._labels.get_pending(c.request_id)) is not None}
        if rows or any(c.engineer_choice is not None for c in calls):
            return await self._again(calls, rows)
        return await self._fresh(calls)

    async def _fresh(self, calls: Sequence[DecisionCall]) -> list[DecisionAnswer | PendingAnswer]:
        """The first run of a batch: tier 1 for each call, tiers 2 and 3 for the rest, then one screen (AC27, AC28)."""
        started, answers = self._monotonic(), {}
        for call in calls:
            if (by_rule := self._rules(call, _values(call), _sha(call), started)) is not None:
                answers[call.request_id] = by_rule
        todo = [c for c in calls if c.request_id not in answers]
        sents = {c.request_id: self._outgoing(c) for c in todo}
        tried = await self._providers_many([c for c in todo if not c.policy.require_engineer], sents)
        for call in todo:
            entries = tried.get(call.request_id, ())
            if (by_provider := self._by_provider(entries, _values(call), _sha(call), started)) is not None:
                answers[call.request_id] = by_provider
        open_calls = [c for c in todo if c.request_id not in answers]
        if not open_calls:
            return [answers[c.request_id] for c in calls]
        batch = batch_id(c.request_id for c in open_calls)
        shown = (self._screen(c, _values(c), tried.get(c.request_id, ())).items[0] for c in open_calls)
        screen = DecisionScreen(items=tuple(shown))
        for call in open_calls:
            self._labels.open_pending(call.request_id, batch, screen, stored(answers))
        return [
            answers[c.request_id]
            if c.request_id in answers
            else PendingAnswer(request_id=c.request_id, batch_id=batch, screen=screen)
            for c in calls
        ]

    async def _again(
        self, calls: Sequence[DecisionCall], rows: Mapping[str, PendingRecord]
    ) -> list[DecisionAnswer | PendingAnswer]:
        """A repeated batch or the engineer's choices: stored outcomes come back, the choices count all or none."""
        known = restored(next(iter(rows.values())).outcomes) if rows else {}
        screened = {i.request_id for row in rows.values() if row.closed_at is None for i in row.screen.items}
        expected = {request_id for request_id in screened if self._is_open(request_id)}
        given = {c.request_id: c.engineer_choice.choice for c in calls if c.engineer_choice is not None}
        why = refusal(expected, given, {c.request_id: _values(c) for c in calls})
        answers: list[DecisionAnswer | PendingAnswer] = []
        for call in calls:
            row = rows.get(call.request_id)
            if row is None and call.request_id in known:
                answers.append(known[call.request_id])
            elif why is not None and row is not None and row.closed_at is None:
                answers.append(
                    PendingAnswer(request_id=call.request_id, batch_id=row.batch_id, screen=row.screen, rejected=why)
                )
            else:
                answers.append(await self.decide(call))
        return answers

    def _is_open(self, request_id: str) -> bool:
        """Whether the request is stored and not yet answered."""
        row = self._labels.get_pending(request_id)
        return row is not None and row.closed_at is None

    async def _providers_many(
        self, calls: Sequence[DecisionCall], sents: Mapping[str, _Outgoing]
    ) -> dict[str, tuple[Suggestion, ...]]:
        """Tiers 2 and 3 over many calls: each call gets the entries ``_providers`` would give it alone."""
        shadowed = [c for c in calls if self._shadowed(c)]
        two, three = await asyncio.gather(self._tier_many(2, calls, sents), self._tier_many(3, shadowed, sents))
        later = [
            c
            for c in calls
            if not self._shadowed(c) and (c.request_id not in two or two[c.request_id].outcome != "accepted")
        ]
        three |= await self._tier_many(3, later, sents)
        return {
            c.request_id: tuple(e for e in (two.get(c.request_id), three.get(c.request_id)) if e is not None)
            for c in calls
        }

    async def _tier_many(
        self, number: Literal[2, 3], calls: Sequence[DecisionCall], sents: Mapping[str, _Outgoing]
    ) -> dict[str, Suggestion]:
        """One tier over many calls: the skips, then one ``batch`` request or bounded single calls."""
        found: dict[str, Suggestion] = {}
        batched: list[DecisionCall] = []
        singles: list[DecisionCall] = []
        jobs: list[Callable[[], Awaitable[Suggestion]]] = []
        via: DecisionProvider | None = None
        for call in calls:
            tier = next((t for t in self._tiers(call) if t.number == number), None)
            if tier is None:
                continue
            sent, shadow, values = sents[call.request_id], self._shadowed(call), _values(call)
            if (skipped := self._skipped(tier, sent, shadow)) is not None:
                found[call.request_id] = skipped
            elif number == 2 and (via := self._model) is not None and via.info.supports_batch and not call.point.yes_no:
                batched.append(call)
            else:
                singles.append(call)
                request = self._request(call, values, sent)
                jobs.append(partial(self._tier, tier, request, values, sent, shadow, call.policy.min_confidence))
        if batched and via is not None:
            found |= await self._batched(via, batched, sents)
        for call, entry in zip(singles, await bounded(self._limit, jobs), strict=True):
            found[call.request_id] = entry
        return found

    async def _batched(
        self, model: DecisionProvider, calls: Sequence[DecisionCall], sents: Mapping[str, _Outgoing]
    ) -> dict[str, Suggestion]:
        """Tier 2 for ``calls`` in one ``batch`` request: a failed request is its own entry, a failed batch all."""
        began = self._monotonic()
        requests = [self._request(c, _values(c), sents[c.request_id]) for c in calls]
        try:
            async with asyncio.timeout(max(c.policy.timeout_ms_model for c in calls) / 1000):
                got = await model.batch(requests)
            if len(got) != len(calls):
                raise ProviderError(ProviderErrorCode.BAD_RESPONSE)
        except Exception as error:
            latency = self._elapsed_ms(began)
            return {c.request_id: _failed(2, model.info, error, self._shadowed(c), latency) for c in calls}
        latency, entries = self._elapsed_ms(began), {}
        for call, answer in zip(calls, got, strict=True):
            shadow = self._shadowed(call)
            if isinstance(answer, ProviderFailure):
                entries[call.request_id] = _failed(2, model.info, ProviderError(answer.code), shadow, latency)
            else:
                minimum, values = call.policy.min_confidence, _values(call)
                entries[call.request_id] = _model_entry(
                    model.info, answer.choice, answer.confidence, values, shadow, minimum, latency
                )
        return entries
