"""Approvals of the engine: request, binding, single use, re-check before the write, items and expiry (spec 0001 4.9).

Purpose: `ctx.approve` stores the preview, binds the request to the state of every model in it, presents it and waits
for the answer. An answer is accepted once, for the request and the preview it quotes. A write passed `under=` the
approval is refused unless the approval was approved, has not expired and covers the item and the model, and a model
that changed since the approval was shown voids it before the write. An approval expires at the first check of a model
it is bound to and at the return of the scope that asked for it. Units: none. Errors: `AwaitingApproval` (no answer, or
a refused one), `ApprovalVoid`, `BlockRuleViolation`, `ReplayDivergence` (the journal shows the request with another
preview), `ContractError` `PRECONDITION_FAILED` (a bound model is not open).
"""

import hashlib
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import cast

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Provenance
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.store import ResultStore
from pydantic import JsonValue

from eng_harness import errors
from eng_harness.ctx import Approval, ApprovalKind, Preview
from eng_harness.engine._invariants import Guard, _Ctx, _Phase
from eng_harness.journal import Event, EventType, JournalWriter
from eng_harness.journal import _events as ev
from eng_harness.ports import ApprovalAnswer, ApprovalPort, ApprovalRequest, HostModelState, HostPort, ModelBinding

_LOG = logging.getLogger(__name__)
_Obj = dict[str, JsonValue]


class AwaitingApproval(errors.Pause):
    """The run waits for the engineer's answer to an approval request: `run_paused` with `awaiting_approval`."""


def request_id(run_id: str, path: str) -> str:
    """`apr_` and the first 32 hex digits of sha256 of `<run_id>\\n<path>`: stable across replay (spec 4.9)."""
    return "apr_" + hashlib.sha256(f"{run_id}\n{path}".encode()).hexdigest()[:32]


@dataclass
class _Grant:
    """What an answered approval authorizes; `next` is, per model, the state the next step must find."""

    path: str
    approved: bool
    items: frozenset[str]
    rejected: frozenset[str]
    binding: dict[str, ModelBinding]
    next: dict[str, tuple[int | None, str | None, str | None]] = field(default_factory=dict)
    """Revision, fingerprint, file hash. No entry: no write yet. Revision `None`: unknown; others: not compared."""
    expired: bool = False


class Approvals:
    """The approvals of one run: requests, answers and what each answered approval still authorizes."""

    def __init__(
        self, port: ApprovalPort, host: HostPort, store: ResultStore, writer: JournalWriter,
        producer: Callable[[], Provenance], run_id: str, events: Sequence[Event],
    ) -> None:  # fmt: skip
        """Serve one run; `events` are the journal replayed: its requests, answers and sign-offs are not made again."""
        self._port, self._host, self._store, self._writer = port, host, store, writer
        self._producer, self._run_id = producer, run_id
        payloads = [e.payload for e in events]
        self._asked = {p.request_id: p for p in payloads if isinstance(p, ev.ApprovalRequested)}
        self._answers = {p.request_id: p for p in payloads if isinstance(p, ev.ApprovalResolved)}
        self._signed = {p.approval_request_id for p in payloads if isinstance(p, ev.SignedOff)}
        self._grants: dict[str, _Grant] = {}

    async def settle(
        self, path: str, title: str, preview: Preview, kind: ApprovalKind, args: _Obj
    ) -> tuple[Approval, str]:
        """The approval requested at `path` and the stored preview's reference; the journal's answer when it has one.

        A request not yet asked is bound to the models' state, journaled and presented; one the journal holds is
        presented again with its recorded binding. `args` is the preview as JSON.

        Raises:
            AwaitingApproval: no answer, or an answer that was refused (the request is presented again).
        """
        request = await self._request(request_id(self._run_id, path), title, preview, kind, args)
        answer = self._answers.get(request.request_id)
        if answer is None:
            await self._port.present(request)
            answer = await self._answer(request)
        return self._grant(path, request, answer, preview), request.preview_ref

    async def _request(self, rid: str, title: str, preview: Preview, kind: ApprovalKind, args: _Obj) -> ApprovalRequest:
        sha, held = payload_sha256(args), self._asked.get(rid)
        if held is None:
            bound = {m.model_key: await self._bind(m.model_key) for m in preview.models}
            stored = self._store.put("harness.approval_preview/1", args, self._producer())
            body: _Obj = {
                "request_id": rid, "kind": kind.value, "title": title, "preview_ref": stored.result_id,
                "shown_sha256": sha, "items": [item.id for item in preview.items],
                "binding": {k: b.model_dump(mode="json", exclude={"model_key"}) for k, b in bound.items()},
            }  # fmt: skip
            self._writer.append(EventType.APPROVAL_REQUESTED, body)
            held = self._asked[rid] = ev.ApprovalRequested.model_validate(body)
        elif held.shown_sha256 != sha:
            raise errors.ReplayDivergence(f"approval request {rid} was shown with another preview than the journal's")
        binding = tuple(ModelBinding.model_validate({"model_key": k, **cast(_Obj, v)}) for k, v in held.binding.items())
        return ApprovalRequest(
            request_id=rid, run_id=self._run_id, kind=held.kind, title=held.title, preview_ref=held.preview_ref,
            shown_sha256=sha, binding=binding, items=tuple(held.items),
        )  # fmt: skip

    async def _state(self, key: str) -> HostModelState | None:
        """The state of the model in the instance that holds it, or `None` when no instance has it open."""
        instance = await self._host.locate(key)
        state = None if instance is None else await self._host.model_state(key, instance.instance_id)
        return state if state is not None and state.loaded else None

    async def _bind(self, key: str) -> ModelBinding:
        if (state := await self._state(key)) is None:
            message = f"the model {key} is not open in any host instance"
            raise ContractError(ErrorCode.PRECONDITION_FAILED, message, precondition=Precondition.model_open)
        return ModelBinding.model_validate({"model_key": key, **state.model_dump(exclude={"loaded"})})

    async def _answer(self, request: ApprovalRequest) -> ev.ApprovalResolved:
        """The engineer's answer, journaled as `approval_resolved`; none, or a refused one, pauses the run."""
        rid = request.request_id
        given = await self._port.answer(rid, wait=False)
        why = None if given is None else self._refusal(request, given)
        if given is None or why is not None:
            if why is not None:  # the request stays open and is presented again
                _LOG.warning("the answer to %s is refused and the request stays open: %s", rid, why)
                await self._port.present(request)
            raise AwaitingApproval(f"approval request {rid} awaits the engineer", evidence=[rid])
        resolved = ev.ApprovalResolved(
            request_id=rid, shown_sha256=given.shown_sha256, decision=given.decision,
            rejected_items=list(given.rejected_items), item_reasons=dict(given.item_reasons),
            acknowledged_unreleased=given.acknowledged_unreleased, reason=given.reason,
            by="engineer:" + given.by.removeprefix("engineer:"),
        )  # fmt: skip
        self._writer.append(EventType.APPROVAL_RESOLVED, resolved)
        self._answers[rid] = resolved
        return resolved

    @staticmethod
    def _refusal(request: ApprovalRequest, given: ApprovalAnswer) -> str | None:
        """Why `given` is refused (AC54), or `None`; a rejected item has a reason, which `ApprovalAnswer` checks."""
        if given.request_id != request.request_id:
            return "it names another request"
        if given.shown_sha256 != request.shown_sha256:
            return "it quotes another preview than the one shown"
        if stray := sorted(set(given.item_reasons) - set(request.items)):
            return f"{', '.join(stray)} are no items of the request"
        return None

    def _grant(self, path: str, request: ApprovalRequest, answer: ev.ApprovalResolved, preview: Preview) -> Approval:
        """Register what the answered approval authorizes; an approved sign-off also journals `signed_off`."""
        rid, approved = request.request_id, answer.decision == "approve"
        rejected = frozenset(answer.rejected_items)
        self._grants[rid] = _Grant(
            path, approved, frozenset(request.items), rejected, {b.model_key: b for b in request.binding}
        )
        if approved and request.kind == ApprovalKind.SIGN_OFF and rid not in self._signed:
            signed = [ref.ref for item in preview.items if item.id not in rejected for ref in item.refs]
            body = {"outputs": list(dict.fromkeys(signed)), "approval_request_id": rid, "by": answer.by}
            self._writer.append(EventType.SIGNED_OFF, body)
        return Approval(
            request_id=rid, approved=approved, rejected_items=tuple(answer.rejected_items),
            item_reasons=dict(answer.item_reasons), reason=answer.reason,
        )  # fmt: skip

    def engineer_approved(self, under: Approval, item: str | None) -> bool:
        """True when `under` was resolved by an engineer, is approved and accepts `item`: an always-ask step is then
        covered; a mode never covers one (spec 4.7, EC3)."""
        answer = self._answers.get(under.request_id)
        return answer is not None and answer.by.startswith("engineer:") and (item is None or under.accepts(item))

    async def authorize(self, under: Approval | None, item: str | None, key: str | None, *, write: bool) -> None:
        """Before a tool step passed `under=` and `item=`: refuse it unless the approval covers it (AC55, AC56).

        Raises:
            BlockRuleViolation: not a write, `item=` with no approval, an approval that is unknown, rejected or
                expired, an item that is unknown or rejected, or a model the approval is not bound to.
            ApprovalVoid: the model is not as the approval bound it, or as the step under it before this one left it.
        """
        if under is None and item is None:
            return
        if not write:
            raise errors.BlockRuleViolation("under= and item= apply to writes only")
        if under is None:
            raise errors.BlockRuleViolation("item= needs under=, the approval that accepted the item")
        rid, grant = under.request_id, self._grants.get(under.request_id)
        if grant is None or not grant.approved:
            raise errors.BlockRuleViolation(f"approval {rid} is not an approved request of this run")
        if grant.expired:
            raise errors.BlockRuleViolation(
                f"approval {rid} expired at a check of its models or the return of its scope"
            )
        if item is not None and item not in grant.items:
            raise errors.BlockRuleViolation(f"item {item} is no item of approval {rid}")
        if item in grant.rejected:
            raise errors.BlockRuleViolation(f"item {item} was rejected in approval {rid}")
        if key not in grant.binding:
            raise errors.BlockRuleViolation(f"approval {rid} is not bound to model {key}")
        await self._recheck(rid, grant, key)

    async def _recheck(self, rid: str, grant: _Grant, key: str) -> None:
        """The model is as bound (identity, revision, fingerprint, file) before the first write, and at the revision the
        step before left for the next."""
        bound, state = grant.binding[key], await self._state(key)
        if key in grant.next:
            revision, fingerprint, file = grant.next[key]
            same = state is not None and state.revision == revision
            same = (
                same
                and fingerprint in (None, state and state.fingerprint)
                and file in (None, state and state.file_sha256)
            )
        else:
            same = state is not None and (state.revision, state.fingerprint, state.file_sha256) == (
                bound.revision, bound.fingerprint, bound.file_sha256
            )  # fmt: skip
        if not same or state is None or state.model_id != bound.model_id:
            raise errors.ApprovalVoid(f"model {key} changed since approval {rid} was shown", evidence=[rid])

    def stepped(self, under: str | None, key: str | None, ref: str, saved: ev.ModelSaved | None = None) -> None:
        """A write under `under` produced the stored result `ref`: the next step must find its revision or, after a tool
        save, the revision, fingerprint and file hash of its `model_saved` (spec 4.9, EC5)."""
        if under is None or key is None or (grant := self._grants.get(under)) is None:
            return
        try:
            host = self._store.get(ref).producer.host
        except ContractError as exc:
            if exc.detail.code is not ErrorCode.REF_NOT_FOUND:
                raise
            host = None
        grant.next[key] = (None if host is None else host.model_revision, None, None)
        if saved is not None:
            grant.next[key] = (saved.revision, saved.fingerprint, saved.file_sha256)

    def expire(self, model: str) -> None:
        """The first check of `model` ends every approval bound to it."""
        for grant in self._grants.values():
            grant.expired = grant.expired or model in grant.binding

    def leave(self, path: str) -> None:
        """The return of the scope at `path` ends every approval requested inside it."""
        for grant in self._grants.values():
            grant.expired = grant.expired or grant.path.startswith(path + "/")


class ApprovalGuard(Guard):
    """The invariant guard of a run whose approvals expire at the first check of a model they are bound to."""

    def __init__(
        self, approvals: Approvals, host: HostPort, store: ResultStore, writer: JournalWriter,
        producer: Callable[[], Provenance],
    ) -> None:  # fmt: skip
        """Guard the run's models and expire `approvals` as they are checked."""
        super().__init__(host, store, writer, producer)
        self._approvals = approvals

    async def check(self, ctx: _Ctx, base: str, phase: _Phase, model: str, *, live: bool = True) -> None:
        """As `Guard.check`; the approvals bound to `model` expire once it has been checked (spec 4.9)."""
        await super().check(ctx, base, phase, model, live=live)
        self._approvals.expire(model)
