"""`ToolPort` over an adapter's allowlist: describe, call, unreleased_tools (plan 0002 T8b; spec 0002 4.5.2, 4.5.3).

Purpose: validate, build host arguments, ledger a write before sending it (4.5.7), answer an envelope. Units: canonical
in and stored, the token's units on the wire. Errors: a tool outside the allowlist raises `INVALID_ARGUMENT`; any other
contract failure is a failure envelope. Host error replies are mapped by the adapter's `HostErrorMapper` and a
timeout or lost session wedges the host until `HostHealth.reconciled` (T9). Not here: preconditions, `reconcile`,
`read_back`.
"""

import logging
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Envelope, HostInfo, make_failure
from eng_contract.errors import ContractError, ErrorCode, ErrorDetail
from eng_contract.ids import Clock, IdSource
from eng_contract.params import ParamModel, ParamSpec
from eng_contract.refs import RefString
from eng_contract.store import ResultStore
from mcp import types
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness.adapters._allowlist import Allowlist
from eng_harness.adapters._args import HostTarget, convert_quantities, host_arguments, validate_call
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._envelope import make_envelope, parse_reply
from eng_harness.adapters._errors import WEDGING_CODES, HostErrorMapper, HostHealth, parse_error_reply
from eng_harness.adapters._ledger import LedgerEntry, WriteLedger
from eng_harness.errors import ToolFailed
from eng_harness.ports import ServerCheck, ToolInfo
from eng_harness.servers import CallEffect, ServersConfig

__all__ = ["AdapterToolPort", "Binding", "Builder", "HostCaller", "ModelBinder", "Reader"]

_LOG = logging.getLogger(__name__)
MODEL_PARAM = "model"  # the canonical argument models name the model key `model`; it never goes to the host
_Obj = Mapping[str, JsonValue]


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

    async def binding(self, host_key: str, model: str | None) -> Binding:
        """The binding of `model`, or of the host's only bound instance when `None`."""

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
    ) -> None:
        """Wire the port; `ValueError` when a tool lacks its argument model, a serving role or a needed reader.

        `errors` maps host error replies (without it an error reply is `HOST_ERROR` with the host's code).
        """
        self._health, self._errors = health or HostHealth(), errors
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
        binding = await self._binder.binding(server.host_key, model)
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
