"""`ToolPort` over an adapter's allowlist: describe, call, unreleased_tools (plan 0002 T8b; spec 0002 4.5.2, 4.5.3).

Purpose: validate, build host arguments, ledger a write before sending it (4.5.7), answer an envelope. Units: canonical
in and stored, the token's units on the wire. Errors: a tool outside the allowlist raises `INVALID_ARGUMENT`; any other
contract failure is a failure envelope. Host error replies are mapped by the adapter's `HostErrorMapper` and a
timeout or lost session wedges the host until `HostHealth.reconciled` (T9).

Reconciliation (T14, spec 4.5.7): with an adapter's `Reconciler`, `supports_reconcile` is true for each write tool,
`reconcile` decides what became of a write from the ledger entry of its `op_id`, the canonical arguments and reads of
the host, stores the evidence as a `harness.run_output/1` result, frees the host (`HostHealth.reconciled`) and answers
a `Reconciliation`; `read_back` shows the state the write left. A host read that times out is `unknown`. The
pre-image is what `Binding.pre_image_ref` pointed to when the write was ledgered: the `observed` value of a
`read_back` taken before it (`None` and no pre-image on record are told apart). Not here: preconditions.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Envelope, HostInfo, LiteralInput, RefInput, SuccessEnvelope, make_failure
from eng_contract.errors import ContractError, ErrorCode, ErrorDetail, Precondition
from eng_contract.ids import Clock, IdSource, Timestamp
from eng_contract.params import ParamModel, ParamSpec
from eng_contract.refs import Ref, RefRule, RefString, resolve_ref
from eng_contract.store import ResultStore
from mcp import types
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness.adapters._allowlist import Allowlist
from eng_harness.adapters._args import HostTarget, convert_quantities, host_arguments, validate_call
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._envelope import make_envelope, parse_reply
from eng_harness.adapters._errors import WEDGING_CODES, HostErrorMapper, HostHealth, parse_error_reply
from eng_harness.adapters._ledger import LedgerEntry, WriteLedger
from eng_harness.ctx import ModelHandle, Preview, PreviewItem
from eng_harness.errors import ToolFailed
from eng_harness.ports import Reconciliation, ServerCheck, ToolInfo
from eng_harness.servers import CallEffect, ServersConfig

__all__ = [
    "AdapterToolPort", "Binding", "Builder", "Decision", "HostCaller", "HostRead", "LostWrite", "ModelBinder",
    "Reader", "Reconciler",
]  # fmt: skip

_LOG = logging.getLogger(__name__)
MODEL_PARAM = "model"  # the canonical argument models name the model key `model`; it never goes to the host
_Obj = Mapping[str, JsonValue]
_TIMEOUTS = frozenset({ErrorCode.TIMEOUT_NO_EFFECT, ErrorCode.TIMEOUT_UNKNOWN_OUTCOME})
HostRead = Callable[
    [str, dict[str, Any], CallEffect], Awaitable[dict[str, Any]]
]  # a host read, `ContractError` on failure


def _untracked(model_id: str) -> int | None:
    """The revision of no model: the references of a lost write are read for their values, not checked for age."""
    return None


class Binding(BaseModel):
    """The model a call acts on: its instance, units token, host (provenance) and last state read (the pre-image)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target: HostTarget
    units_system: str | None = None
    host: HostInfo | None = None
    owned: bool = False  # the role holds launch ownership of the instance (spec 4.4.2)
    pre_image_ref: RefString | None = None


class ModelBinder(Protocol):
    """The `HostPort` side that knows the bound instance of a model key."""

    async def binding(self, host_key: str, model: str | None, descriptor: ToolDescriptor) -> Binding:
        """The binding of `model`, or of the host's only bound instance when `None`, for the tool `descriptor`."""

    def revision(self, model_id: str) -> int | None:
        """The current revision of a model id, `None` when not tracked (staleness of references)."""


class HostCaller(Protocol):
    """The session side; `ServerManager` satisfies it."""

    async def call(
        self, server: str, role: str, tool: str, arguments: Mapping[str, Any], effect: CallEffect
    ) -> types.CallToolResult:
        """Send one tool call and return the raw reply."""


Builder = Callable[[ParamModel, ToolDescriptor, Binding], dict[str, JsonValue]]  # canonical model to host arguments
Reader = Callable[[_Obj, Binding], tuple[dict[str, JsonValue], dict[str, JsonValue]]]  # reply to (payload, summary)


@dataclass(frozen=True)
class LostWrite:
    """A write of unknown outcome: its tool, canonical arguments, binding and the pre-image of its ledger entry.

    `known` tells a pre-image on record (whose value `pre_image` may be `None`: the object was absent) from none.
    """

    descriptor: ToolDescriptor
    model: ParamModel
    binding: Binding
    known: bool
    pre_image: JsonValue


class Decision(BaseModel):
    """What an adapter found: the outcome, the items still missing after a `partial`, and the evidence it read."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Literal["applied", "not_applied", "partial", "unknown"]
    evidence: dict[str, JsonValue]
    missing: tuple[str, ...] = ()


class Reconciler(Protocol):
    """An adapter's rules for the outcome of a lost write (spec 4.5.7), reading the host through `read`."""

    async def decide(self, lost: LostWrite, read: HostRead) -> Decision:
        """The decision for `lost`; `ContractError` when a read fails."""

    async def observe(self, lost: LostWrite, read: HostRead) -> dict[str, JsonValue] | None:
        """The state `lost`'s tool left as a payload, or `None` when the adapter has no read-back for it."""


def _raised(detail: ErrorDetail) -> ContractError:
    names = ("incident_id", "host_code", "host_method", "precondition")
    extra = {name: value for name in names if (value := getattr(detail, name)) is not None}
    return ContractError(detail.code, detail.message, retryable=detail.retryable, **extra)


def _default_builder(model: ParamModel, descriptor: ToolDescriptor, binding: Binding) -> dict[str, JsonValue]:
    """The model's fields without the model key; quantities of a `token` tool converted to the token's units."""
    fields = model.model_dump(mode="json", exclude_none=True, exclude={MODEL_PARAM})
    if descriptor.units == "token" and binding.units_system is not None:
        fields |= convert_quantities(model, binding.units_system)
    return fields


class AdapterToolPort:
    """The `ToolPort` calls of one adapter (the server `server` of `config`) over its allowlist."""

    def __init__(
        self,
        *,
        allowlist: Allowlist,
        config: ServersConfig,
        server: str,
        caller: HostCaller,
        binder: ModelBinder,
        store: ResultStore,
        ledger: WriteLedger,
        clock: Clock,
        ids: IdSource,
        check: ServerCheck,
        arg_models: Mapping[str, type[ParamModel]],
        builders: Mapping[str, Builder] | None = None,
        readers: Mapping[str, Reader] | None = None,
        health: HostHealth | None = None,
        errors: HostErrorMapper | None = None,
        reconciler: Reconciler | None = None,
        record_pre_image: bool = False,
        open_model_bound: Callable[[str | None], bool] | None = None,
    ) -> None:
        """Wire the port; `ValueError` when a tool lacks its argument model, a serving role or a needed reader.

        `errors` maps host error replies (without it an error reply is `HOST_ERROR` with the host's code).
        Without a `reconciler` no tool supports reconciliation and the engine asks the engineer.
        `record_pre_image` opts production wiring into pre-write observation; otherwise the binder's ref is retained.
        `open_model_bound` is a cache-only query for the unbound-open preview exception; without it the binder decides.
        """
        self._record_pre_image, self._open_model_bound = record_pre_image, open_model_bound
        self._health, self._errors, self._reconciler = health or HostHealth(), errors, reconciler
        self._allowlist, self._config, self._server = allowlist, config, server
        self._caller, self._binder, self._store, self._ledger = caller, binder, store, ledger
        self._clock, self._ids, self._check, self._models = clock, ids, check, arg_models
        self._builders, self._readers = builders or {}, readers or {}
        for t in allowlist.tools:
            served = any(t.timeout_class in r.classes for r in config.servers[server].roles.values())
            if t.args_model not in arg_models or not served or (t.result_kind and t.name not in self._readers):
                raise ValueError(f"{t.name}: its argument model, role or reader is not wired")

    def unreleased_tools(self) -> dict[str, str]:
        """`{name: release_record}` of the unreleased allowlist and `[cli_tools.*]` entries (AC38)."""
        return self._allowlist.unreleased_tools() | self._config.unreleased_tools()

    def _find(self, tool: str) -> ToolDescriptor:
        try:
            return self._allowlist.descriptor(tool)
        except KeyError:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{tool} is not on the allowlist", field="tool") from None

    async def describe(self, tool: str) -> ToolInfo:
        """The tool's info; `ContractError` `INVALID_ARGUMENT` for a tool outside the allowlist (AC17)."""
        descriptor = self._find(tool)
        fields = self._models[descriptor.args_model].model_fields
        params = tuple(
            name
            for name, info in fields.items()
            if isinstance(info.json_schema_extra, ParamSpec) and info.json_schema_extra.engineering_quantity
        )
        return ToolInfo(
            name=descriptor.name,
            effect=descriptor.effect,
            action=descriptor.action,
            host_key=self._config.servers[self._server].host_key,
            model_param=MODEL_PARAM if MODEL_PARAM in fields else None,
            engineering_params=params,
        )

    async def call(self, tool: str, args: _Obj, *, op_id: str, model: str | None) -> Envelope:
        """Call `tool`; a write is ledgered first. `confirm` follows the descriptor (the engine's approval came first).

        Raises:
            ContractError: `INVALID_ARGUMENT` for a tool outside the allowlist; nothing is sent.
        """
        descriptor = self._find(tool)
        try:
            return await self._call(descriptor, args, op_id, model)
        except (ContractError, ToolFailed) as error:
            return make_failure(error.detail)

    def _lost(self, detail: ErrorDetail, host_key: str, op_id: str, *, bump_epoch: bool) -> ToolFailed:
        """The failure to return; a timeout or lost session wedges the host and an unknown outcome names `op_id`."""
        if detail.code in WEDGING_CODES:
            self._health.mark_wedged(host_key, op_id, bump_epoch=bump_epoch)
        if detail.code is ErrorCode.TIMEOUT_UNKNOWN_OUTCOME and detail.op_id is None:
            detail = detail.model_copy(update={"op_id": op_id})
        return ToolFailed(detail)

    async def _call(self, descriptor: ToolDescriptor, args: _Obj, op_id: str, model: str | None) -> Envelope:
        server = self._config.servers[self._server]
        self._health.check(server.host_key)  # a wedged host gets nothing until the engine has reconciled
        role = next(name for name, r in server.roles.items() if descriptor.timeout_class in r.classes)
        started, began = self._clock.now(), self._clock.now_ms()
        cls = self._models[descriptor.args_model]
        validated = validate_call(cls, args, source=self._store, current_revision=self._binder.revision)
        binding = await self._binder.binding(server.host_key, model, descriptor)
        build = self._builders.get(descriptor.name, _default_builder)
        sent = host_arguments(
            descriptor,
            build(validated.model, descriptor, binding),
            target=binding.target,
            units_system=binding.units_system,
            approved=True,
            owned=binding.owned,
        )
        effect = CallEffect.WRITE if descriptor.effect == "write" else CallEffect.READ
        if effect is CallEffect.WRITE:
            if self._record_pre_image:
                binding = binding.model_copy(update={"pre_image_ref": await self._pre_image(descriptor.name, args)})
            entry = LedgerEntry(
                op_id=op_id,
                tool=descriptor.name,
                args_sha256=payload_sha256(dict(args)),
                target=binding.target,
                pre_image_ref=binding.pre_image_ref,
                sent_at=self._clock.now(),
            )
            try:
                self._ledger.append(entry)
            except OSError as error:
                incident = self._ids.new_ulid()
                _LOG.error("write ledger failed", extra={"incident_id": incident, "tool": descriptor.name})
                raise ContractError(
                    ErrorCode.INTERNAL, f"{descriptor.name} not sent, ledger: {error}", incident_id=incident
                ) from error
        try:
            result = await self._caller.call(self._server, role, descriptor.name, sent, effect)
        except ToolFailed as error:  # the session lost the host and increased its epoch itself
            raise self._lost(error.detail, server.host_key, op_id, bump_epoch=False) from error
        dumped = result.model_dump(by_alias=True, mode="json")
        if self._errors is not None and (failure := parse_error_reply(dumped)) is not None:
            detail = self._errors.map(failure, effect=effect, tool=descriptor.name, op_id=op_id)
            raise self._lost(detail, server.host_key, op_id, bump_epoch=True)
        reply = parse_reply(dumped)
        binding = await self._settled(descriptor, args, model, binding)
        reader = self._readers.get(descriptor.name)
        payload, summary = reader(reply, binding) if reader else ({"value": reply}, {})
        return make_envelope(
            self._store,
            tool=f"{self._allowlist.adapter}/{descriptor.name}",
            kind=descriptor.result_kind or "harness.run_output/1",
            payload=payload,
            summary=summary,
            reply=reply,
            check=self._check,
            host=binding.host,
            inputs=validated.inputs,
            started_at=started,
            duration_ms=self._clock.now_ms() - began,
        )

    async def _settled(self, descriptor: ToolDescriptor, args: _Obj, model: str | None, binding: Binding) -> Binding:
        """Return the binding whose `host` goes on the stored result after a successful reply (spec 4.5.3, 4.5.9)."""
        return binding

    async def _pre_image(self, tool: str, args: _Obj) -> RefString | None:
        """Store the observed pre-write state, for the ledger and preview (spec 4.5.7); absent for no read-back."""
        if not self.supports_reconcile(tool):
            return None
        before = await self.read_back(tool, args)
        if before is not None and not isinstance(before, SuccessEnvelope):
            raise _raised(before.error)
        return None if before is None else RefString(f"{before.result_id}#/value/observed")

    async def preview(self, tool: str, args: _Obj) -> Preview:
        """Canonical arguments and the observed pre-image, without sending a write (spec 4.5.9, AC45)."""
        descriptor = self._find(tool)
        validated = validate_call(
            self._models[descriptor.args_model], args, source=self._store, current_revision=self._binder.revision
        )
        key = args.get(MODEL_PARAM)
        key = key if isinstance(key, str) else None
        models: tuple[ModelHandle | str, ...] = ()
        binding = None
        unopened = (
            descriptor.action == "open" and self._open_model_bound is not None and not self._open_model_bound(key)
        )
        if not unopened:
            binding = await self._binder.binding(self._config.servers[self._server].host_key, key, descriptor)
            if binding.host is None:
                raise ContractError(ErrorCode.PRECONDITION_FAILED, "not open", precondition=Precondition.model_open)
            models = (
                ModelHandle(model_key=key or "", model_id=binding.host.model_id, revision=binding.host.model_revision),
            )
        started, began = self._clock.now(), self._clock.now_ms()
        canonical = make_envelope(
            self._store,
            tool=f"{self._allowlist.adapter}/{tool}",
            kind="harness.run_output/1",
            payload={"value": validated.model.model_dump(mode="json", exclude_none=True)},
            summary={},
            reply={},
            check=self._check,
            host=None if binding is None else binding.host,
            inputs=validated.inputs,
            started_at=started,
            duration_ms=self._clock.now_ms() - began,
        )
        refs: tuple[Ref, ...] = (Ref.model_validate({"$ref": canonical.result_id}),)
        before = None if binding is None else binding.pre_image_ref
        if not unopened and self._record_pre_image:
            before = await self._pre_image(tool, args)
        if before is not None:
            refs += (Ref.model_validate({"$ref": before}),)
        return Preview(
            items=(PreviewItem(id=tool, label=f"{tool}: {key or 'host'}", refs=refs),), models=models, diff_ref=None
        )

    def supports_reconcile(self, tool: str) -> bool:
        """True for a write tool of the allowlist when the port has a reconciler (spec 4.5.9)."""
        try:
            descriptor = self._allowlist.descriptor(tool)
        except KeyError:
            return False
        return self._reconciler is not None and descriptor.effect == "write"

    async def reconcile(self, tool: str, args: _Obj, op_id: str) -> Reconciliation:
        """Decide whether the call `op_id` of `tool` took effect (spec 4.5.7), and free the host it wedged.

        A host read that times out gives `unknown`. The evidence is stored and referenced from the answer.

        Raises:
            ContractError: `INVALID_ARGUMENT` for a tool outside the allowlist or without a reconciler, the
                validation errors of `args`, and any host failure other than a timeout.
        """
        descriptor, reconciler = self._find(tool), self._reconciler
        if reconciler is None:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, f"{tool} has no reconciler", field="tool")
        started, began = self._clock.now(), self._clock.now_ms()
        validated = validate_call(
            self._models[descriptor.args_model], args, source=self._store, current_revision=_untracked
        )
        lost = await self._lost_write(descriptor, validated.model, args, op_id)
        try:
            decision = await reconciler.decide(lost, self._read)
        except ContractError as error:
            if error.detail.code not in _TIMEOUTS:
                raise
            decision = Decision(outcome="unknown", evidence={"read_failed": error.detail.code.value})
        stored = self._stored(descriptor, lost, validated.inputs, {"value": decision.evidence}, started, began)
        self._health.reconciled(op_id)
        return Reconciliation(
            outcome=decision.outcome,
            missing=decision.missing,
            evidence=(Ref.model_validate({"$ref": stored.result_id}),),
        )

    async def read_back(self, tool: str, args: _Obj) -> Envelope | None:
        """The state a write of `tool` left, as a stored `value.observed`; `None` for a tool with no read-back."""
        descriptor = self._find(tool)
        if self._reconciler is None or not self.supports_reconcile(tool):
            return None
        started, began = self._clock.now(), self._clock.now_ms()
        validated = validate_call(
            self._models[descriptor.args_model], args, source=self._store, current_revision=_untracked
        )
        lost = await self._lost_write(descriptor, validated.model, args, None)
        observed = await self._reconciler.observe(lost, self._read)
        if observed is None:
            return None
        return self._stored(descriptor, lost, validated.inputs, {"value": observed}, started, began)

    def _stored(
        self, descriptor: ToolDescriptor, lost: LostWrite, inputs: Mapping[str, RefInput | LiteralInput],
        payload: dict[str, JsonValue], started: Timestamp, began: int,
    ) -> SuccessEnvelope:  # fmt: skip
        return make_envelope(
            self._store, tool=f"{self._allowlist.adapter}/{descriptor.name}", kind="harness.run_output/1",
            payload=payload, summary={}, reply={}, check=self._check, host=lost.binding.host, inputs=inputs,
            started_at=started, duration_ms=self._clock.now_ms() - began,
        )  # fmt: skip

    async def _lost_write(
        self, descriptor: ToolDescriptor, model: ParamModel, args: _Obj, op_id: str | None
    ) -> LostWrite:
        key = args.get(MODEL_PARAM)
        binding = await self._binder.binding(
            self._config.servers[self._server].host_key, key if isinstance(key, str) else None, descriptor
        )
        entry = None if op_id is None else self._ledger.find(op_id)
        ref = None if entry is None else entry.pre_image_ref
        pre_image = None if ref is None else resolve_ref(ref, RefRule(), self._store, _untracked).value
        return LostWrite(descriptor, model, binding, ref is not None, pre_image)

    async def _read(self, tool: str, arguments: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
        """A read on the role that serves the `call` class; `ContractError` for any failure, the host's mapped."""
        role = next(name for name, r in self._config.servers[self._server].roles.items() if "call" in r.classes)
        try:
            result = await self._caller.call(self._server, role, tool, arguments, effect)
        except ToolFailed as error:
            raise _raised(error.detail) from error
        dumped = result.model_dump(by_alias=True, mode="json")
        if self._errors is not None and (failure := parse_error_reply(dumped)) is not None:
            raise _raised(self._errors.map(failure, effect=effect, tool=tool, op_id=""))
        return parse_reply(dumped)
