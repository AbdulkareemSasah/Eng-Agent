"""Route-scoped IDEA calls, load previews and write settlement (plan 0014 T9a)."""

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Envelope, HostInfo, LiteralInput, RefInput, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.ids import Clock, IdSource, Timestamp
from eng_contract.kinds.basis import DesignBasis
from eng_contract.params import ParamModel
from eng_contract.refs import Ref, RefRule, resolve_ref
from eng_contract.store import ModelStateStore, ResultStore
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from eng_harness.adapters._allowlist import Allowlist
from eng_harness.adapters._args import validate_call
from eng_harness.adapters._descriptors import ToolDescriptor
from eng_harness.adapters._envelope import make_envelope
from eng_harness.adapters._errors import HostHealth, parse_error_reply
from eng_harness.adapters._toolport import AdapterToolPort, Decision, HostCaller, LostWrite, SettlementError
from eng_harness.adapters.idea import _loads, _replies, _tools
from eng_harness.adapters.idea._calculate import (
    CalculateProvenance,
    calculate_native,
    calculate_rest,
    get_check_results,
)
from eng_harness.adapters.idea._errors import IdeaErrorMapper
from eng_harness.adapters.idea._reconcile import IdeaReconciler
from eng_harness.adapters.idea._session_ops import IdeaHostPort, _file_sha256, require_inside_run
from eng_harness.basis import BasisInvalid, StoreBasisPort
from eng_harness.ctx import ModelHandle, Preview, PreviewItem
from eng_harness.errors import JournalIntegrityError, ToolFailed
from eng_harness.journal import JournalReader
from eng_harness.kinds.idea import IdeaLoads
from eng_harness.ports import Reconciliation, ServerCheck, ToolInfo
from eng_harness.servers import CallEffect, ServerManager, ServersConfig

_SET = "idea_native_set_loads"
_LOADS = "idea_native_get_loads"
_NATIVE_CALC = "idea_native_calculate"
_CALC = "idea_calculate"
_RESULTS = "idea_get_check_results"
_OPEN = "idea_open_project"
_CLOSE = "idea_close_project"
_LIST = "idea_list_connections"
_STATUS = "idea_status"
_OUTPUT = "harness.run_output/1"
_CODE = "connection.design_code"
_TOLERANCE = "checks.readback_relative_tolerance_ratio"
_OBSERVED = "#/value/observed"


class _LoadArguments(_loads.LoadPlan, ParamModel):
    model: str


_MODELS: Mapping[str, type[ParamModel]] = {
    "NativeSetLoadsArgs": _LoadArguments,
    **{
        model.__name__: model
        for model in (
            _tools.StatusArgs,
            _tools.OpenProjectArgs,
            _tools.CloseProjectArgs,
            _tools.ListConnectionsArgs,
            _tools.NativeGetLoadsArgs,
            _tools.NativeCalculateArgs,
            _tools.CalculateArgs,
            _tools.GetCheckResultsArgs,
        )
    },
}
_Obj = Mapping[str, JsonValue]
_Inputs = Mapping[str, RefInput | LiteralInput]


class _IdeaTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    route: Literal["native", "rest"]
    file: str
    service_url: str | None = None


class _IdeaLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    op_id: str
    tool: str
    args_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target: _IdeaTarget
    pre_image_ref: str | None
    sent_at: Timestamp


class _IdeaWriteLedger:
    """Append before sending (spec 0014 §4.7, §4.10, Q13). A torn line cannot account for a lost write."""

    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / "adapter" / "ops.jsonl"

    def append(self, entry: _IdeaLedgerEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        created = not self.path.exists()
        with self.path.open("ab") as handle:
            handle.write(entry.model_dump_json().encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        if created and os.name == "posix":
            directory = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    def find(self, op_id: str) -> _IdeaLedgerEntry | None:
        found = None
        with self.path.open("rb") as handle:
            for line in handle:
                try:
                    entry = _IdeaLedgerEntry.model_validate_json(line)
                except ValidationError:
                    continue
                if entry.op_id == op_id:
                    found = entry
        return found


class _IdeaToolInfo(ToolInfo):
    def saves_new_file(self, args: _Obj) -> bool:
        return self.name == _SET

    def opens_model_without_writing(self, args: _Obj) -> bool:
        return self.name == _OPEN


class _CalculationContext(TypedDict):
    sessions: HostCaller
    server: str
    role: str
    design_code: str
    load_map_confirmed: bool
    store: ResultStore
    ids: IdSource
    provenance: CalculateProvenance
    op_id: str


class IdeaRunHostPort(IdeaHostPort):
    """Expose verified file bindings and combine the server and adapter timeout epochs."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.write_health = HostHealth()

    def session_epoch(self, host_key: str) -> int:
        return super().session_epoch(host_key) + self.write_health.epoch_bumps(host_key)

    def model_for_file(self, path: Path) -> str | None:
        return next((key for key in self._bound if self._file(key) == path), None)

    def file_binding(self, model: str) -> tuple[Path, HostInfo]:
        path = require_inside_run(self._file(model), self._run_dir)
        if model not in self._bound or not path.is_file() or _file_sha256(path) != self._hashes[model]:
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED, "IDEA working copy is not bound", precondition=Precondition.model_open
            )
        identity = self.identity_store.resolve(path)
        return path, HostInfo(program="idea", version="", model_id=identity.model_id, model_revision=identity.revision)


@dataclass(frozen=True)
class _PreparedLoading:
    path: Path
    host: HostInfo
    plan: _LoadArguments
    before: IdeaLoads
    requested: list[dict[str, Any]]
    inputs: _Inputs


@dataclass(frozen=True)
class _LostLoading:
    """The descriptor and prepared request consumed by T8's IDEA reconciler."""

    descriptor: ToolDescriptor
    model: ParamModel


class IdeaToolPort(AdapterToolPort):
    """Use the shared call, description and error framework with IDEA-specific dispatch."""

    def __init__(
        self,
        *,
        config: ServersConfig,
        allowlist: Allowlist,
        server: str,
        caller: ServerManager,
        host: IdeaRunHostPort,
        states: ModelStateStore,
        store: ResultStore,
        run_dir: Path,
        clock: Clock,
        ids: IdSource,
        check: ServerCheck,
    ) -> None:
        # The base dispatch initializer requires a PID-based binder and ledger. IDEA uses neither in its dispatch.
        self._config, self._allowlist, self._server, self._caller = config, allowlist, server, caller
        self._store, self._clock, self._ids, self._check, self._models = store, clock, ids, check, _MODELS
        self._health, self._errors = host.write_health, IdeaErrorMapper(ids)
        self._host, self._states, self._run_dir = host, states, run_dir.resolve()
        self._idea_ledger = _IdeaWriteLedger(self._run_dir)
        self._load_map = _loads.load_shipped_map()
        self._rest_model: str | None = None

    async def describe(self, tool: str) -> ToolInfo:
        info = await super().describe(tool)
        return _IdeaToolInfo.model_validate(info.model_dump() | {"model_param": None if tool == _STATUS else "model"})

    def _revision(self, model_id: str) -> int | None:
        state = self._states.get(model_id)
        return None if state is None else state.revision

    def _basis(self) -> DesignBasis | None:
        try:
            reader = JournalReader(self._run_dir)
            try:
                ref = reader.header().basis_ref
            finally:
                reader.close()
            return StoreBasisPort(self._store).load(ref).basis
        except JournalIntegrityError, BasisInvalid:
            return None

    def _basis_value(self, name: str) -> JsonValue:
        basis = self._basis()
        field = None if basis is None else basis.fields.get(name)
        return None if field is None or not field.confirmed else field.value

    def _tolerance(self) -> float | None:
        value = self._basis_value(_TOLERANCE)
        return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None

    def _relative(self, path: Path) -> str:
        return require_inside_run(path, self._run_dir).relative_to(self._run_dir).as_posix()

    def _bound(self, model: str | None) -> tuple[Path, HostInfo]:
        if model is None:
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED, "an IDEA model must be bound", precondition=Precondition.model_open
            )
        return self._host.file_binding(model)

    def _record(self, tool: str, args: _Obj, op_id: str, path: Path, pre_image: str | None = None) -> None:
        url = self._config.servers[self._server].service_url
        route = self._config.servers[self._server].route
        target = _IdeaTarget(route="rest" if route == "rest" else "native", file=self._relative(path), service_url=url)
        entry = _IdeaLedgerEntry(
            op_id=op_id,
            tool=tool,
            args_sha256=payload_sha256(dict(args)),
            target=target,
            pre_image_ref=pre_image,
            sent_at=self._clock.now(),
        )
        try:
            self._idea_ledger.append(entry)
        except OSError as error:
            raise ContractError(
                ErrorCode.INTERNAL, f"{tool}: could not persist the write intent", incident_id=self._ids.new_ulid()
            ) from error

    def _store_result(
        self,
        tool: str,
        kind: str,
        payload: dict[str, JsonValue],
        host: HostInfo | None,
        inputs: _Inputs,
        timing: tuple[Timestamp, int],
        reply: _Obj | None = None,
        summary: dict[str, JsonValue] | None = None,
    ) -> SuccessEnvelope:
        started, began = timing
        return make_envelope(
            self._store,
            tool=f"{self._allowlist.adapter}/{tool}",
            kind=kind,
            payload=payload,
            host=host,
            inputs=inputs,
            started_at=started,
            duration_ms=self._clock.now_ms() - began,
            check=self._check,
            summary=summary or {},
            reply=reply or {},
        )

    def _timing(self) -> tuple[Timestamp, int]:
        return self._clock.now(), self._clock.now_ms()

    async def _send_write(self, tool: str, sent: _Obj, op_id: str) -> dict[str, Any]:
        result = await self._caller.call(self._server, "main", tool, sent, CallEffect.WRITE)
        dumped = result.model_dump(by_alias=True, mode="json")
        if (failure := parse_error_reply(dumped)) is not None:
            raise ToolFailed(IdeaErrorMapper(self._ids).map(failure, effect=CallEffect.WRITE, tool=tool, op_id=op_id))
        return _replies.parse_reply_json(dumped)

    async def _call(self, descriptor: ToolDescriptor, args: _Obj, op_id: str, model: str | None) -> Envelope:
        tool, host_key = descriptor.name, self._config.servers[self._server].host_key
        self._health.check(host_key)
        epoch = self._host.session_epoch(host_key)
        try:
            if tool == _SET:
                return await self._write_loads(args, op_id, model)
            return await self._dispatch(descriptor, args, op_id, model)
        except (ContractError, ToolFailed) as error:
            detail = error.detail
            if detail.code in (ErrorCode.TIMEOUT_NO_EFFECT, ErrorCode.TIMEOUT_UNKNOWN_OUTCOME):
                raise self._lost(
                    detail, host_key, op_id, bump_epoch=self._host.session_epoch(host_key) == epoch
                ) from error
            raise

    async def _dispatch(self, descriptor: ToolDescriptor, args: _Obj, op_id: str, model: str | None) -> Envelope:
        tool, timing = descriptor.name, self._timing()
        call_args = dict(args)
        if tool != _STATUS and "model" in call_args:
            selector = call_args.pop("model")
            if not isinstance(selector, str) or (model is not None and selector != model):
                raise ContractError(ErrorCode.INVALID_ARGUMENT, "invalid IDEA model selector", field="model")
            model = selector
        validated = validate_call(
            self._models[descriptor.args_model], call_args, source=self._store, current_revision=self._revision
        )
        sent = validated.model.model_dump(mode="json", exclude_none=True)
        if tool == _STATUS:
            reply = await self._read(tool, sent, CallEffect.READ)
            status = _replies.parse_status(
                {key: reply[key] for key in ("installed", "service", "read_only", "script_enabled") if key in reply}
            )
            return self._store_result(
                tool, "harness.idea_status/1", status.model_dump(mode="json"), None, validated.inputs, timing
            )

        if "path" in sent:
            given = require_inside_run(Path(str(sent["path"])), self._run_dir)
            model = model or self._host.model_for_file(given)
        model = model or self._rest_model
        path, host = self._bound(model)
        if "path" in sent:
            sent["path"] = str(path)
        if isinstance(validated.model, _tools.NativeGetLoadsArgs):
            raw = await self._read(tool, sent, CallEffect.READ)
            loads = self._canonical(raw, path, validated.model.connection_id)
            return self._store_result(
                tool, "harness.idea_loads/1", loads.model_dump(mode="json"), host, validated.inputs, timing, raw
            )
        if isinstance(validated.model, _tools.NativeCalculateArgs | _tools.CalculateArgs | _tools.GetCheckResultsArgs):
            return await self._calculate(validated.model, args, path, host, op_id, model)
        if tool == _OPEN:
            reply = await self._open_project(path, args, op_id, model)
        else:
            await self._require_project(path, model)
            if tool == _CLOSE:
                self._record(tool, args, op_id, path)
                await self._send_write(tool, sent, op_id)
                self._rest_model = None
                reply = {"backend": None, "service_reachable": True, "live_project": False, "connections": []}
            else:
                reply = await self._read(tool, sent, CallEffect.READ)
        project = _replies.parse_project(
            {key: reply[key] for key in ("backend", "service_reachable", "live_project", "connections") if key in reply}
        )
        return self._store_result(
            tool, "harness.idea_project/1", project.model_dump(mode="json"), host, validated.inputs, timing, reply
        )

    async def _open_project(self, path: Path, args: _Obj, op_id: str, model: str | None) -> dict[str, Any]:
        self._record(_OPEN, args, op_id, path)
        opened = await self._send_write(_OPEN, {"path": str(path)}, op_id)
        if (
            opened.get("backend") != "rest"
            or opened.get("live_project") is not True
            or opened.get("service_reachable") is not True
        ):
            close_op = self._ids.new_ulid()
            self._record(_CLOSE, {}, close_op, path)
            await self._send_write(_CLOSE, {}, close_op)
            self._rest_model = None
            raise ContractError(ErrorCode.HOST_NOT_CONNECTED, "IDEA did not open a live REST project")
        self._rest_model = model
        return opened

    async def _require_project(self, path: Path, model: str | None) -> None:
        if model is not None and await self._host.locate(model) is not None:
            return
        if self._rest_model != model or model is None:
            raise ContractError(
                ErrorCode.PRECONDITION_FAILED, "IDEA project is not open", precondition=Precondition.model_open
            )
        await self._open_project(path, {"path": self._relative(path)}, self._ids.new_ulid(), model)
        if await self._host.locate(model) is None:
            raise ContractError(ErrorCode.HOST_NOT_CONNECTED, "IDEA reopened a different project")

    async def _calculate(
        self,
        request: _tools.NativeCalculateArgs | _tools.CalculateArgs | _tools.GetCheckResultsArgs,
        args: _Obj,
        path: Path,
        host: HostInfo,
        op_id: str,
        model: str | None,
    ) -> Envelope:
        code = _tools.design_code_from_basis({_CODE: self._basis_value(_CODE)})
        provenance = CalculateProvenance(clock=self._clock, host=host, tool_version=self._check.build)
        common: _CalculationContext = {
            "sessions": self._caller,
            "server": self._server,
            "role": "main",
            "design_code": code,
            "load_map_confirmed": self._load_map.status == "confirmed",
            "store": self._store,
            "ids": self._ids,
            "provenance": provenance,
            "op_id": op_id,
        }
        if isinstance(request, _tools.NativeCalculateArgs):
            if model is not None:
                await self._host.ensure_route_ready(model)
            result = await calculate_native(path=path, connection_id=request.connection_id, **common)
        else:
            await self._require_project(path, model)
            if isinstance(request, _tools.CalculateArgs):
                self._record(_CALC, args, op_id, path)
                result = await calculate_rest(connection_ids=request.connection_ids, approved=True, **common)
            else:
                result = await get_check_results(connection_id=request.connection_id, **common)
        return result.verdict_envelope

    def _plan(self, args: _Obj) -> _LoadArguments:
        try:
            return _LoadArguments.model_validate(dict(args))
        except ValidationError as error:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "IDEA load plan is not valid", field="effects") from error

    async def _prepare(self, args: _Obj) -> _PreparedLoading:
        _loads.require_confirmed_map(self._load_map)
        plan = self._plan(args)
        path, host = self._bound(plan.model)
        require_inside_run(Path(plan.path), self._run_dir)
        await self._host.ensure_route_ready(plan.model)
        raw = await self._read(_LOADS, {"path": str(path), "connection_id": plan.connection}, CallEffect.READ)
        before = self._canonical(raw, path, plan.connection)
        requested, _ = _loads.build_loading(
            current=raw["loads"],
            plan=plan,
            load_map=self._load_map,
            source=self._store,
            current_revision=self._revision,
        )
        inputs = {
            f"effects[{effect_index}].entries[{entry_index}].row": RefInput(ref=entry.row.ref)
            for effect_index, effect in enumerate(plan.effects)
            for entry_index, entry in enumerate(effect.entries)
        }
        return _PreparedLoading(path, host, plan, before, requested, inputs)

    def _canonical(self, reply: Mapping[str, Any], path: Path, connection: str | None) -> IdeaLoads:
        try:
            return _loads.host_loads_to_canonical(
                connection=reply.get("connection") or connection or "",
                effects=reply["loads"],
                file_sha256=_file_sha256(path),
            )
        except (KeyError, TypeError, ValueError, OSError) as error:
            raise ContractError(
                ErrorCode.HOST_ERROR,
                "IDEA load reply is invalid",
                retryable=False,
                host_code="UNEXPECTED_REPLY",
                host_method=_LOADS,
            ) from error

    async def _write_loads(self, args: _Obj, op_id: str, model: str | None) -> Envelope:
        timing = self._timing()
        work = await self._prepare(args)
        if model is not None and model != work.plan.model:
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "the model selectors disagree", field="model")
        out = self._run_dir / f"{work.path.stem}.{self._ids.new_ulid()}{work.path.suffix}"
        if out.exists():
            raise ContractError(ErrorCode.CONFLICT, "the IDEA output file already exists")
        sent = _tools.build_native_set_loads_args(
            path=str(work.path),
            loads=work.requested,
            connection_id=work.plan.connection,
            out_path=str(out),
            approved=True,
        )
        record = self._store_result(
            _SET,
            _OUTPUT,
            {
                "value": {
                    "observed": work.before.model_dump(mode="json"),
                    "sent": {**sent, "path": self._relative(work.path), "out_path": self._relative(out)},
                }
            },
            work.host,
            work.inputs,
            timing,
        )
        self._record(_SET, args, op_id, work.path, f"{record.result_id}{_OBSERVED}")
        reply = await self._send_write(_SET, sent, op_id)
        try:
            raw = await self._read(_LOADS, {"path": str(out), "connection_id": work.plan.connection}, CallEffect.READ)
            self._settle_loads(
                work.plan.model, out, work.plan.connection, work.requested, raw, reply.get("dropped_zero") or []
            )
            return self._load_result(_SET, work.plan.model, raw, work.plan.connection, timing, work.inputs)
        except (ContractError, OSError) as error:
            raise SettlementError("IDEA applied the load write but settlement failed") from error

    def _settle_loads(
        self,
        model: str,
        path: Path,
        connection: str,
        requested: list[dict[str, Any]],
        raw: Mapping[str, Any],
        dropped: list[str],
    ) -> None:
        self._canonical(raw, path, connection)
        current, _ = self._bound(model)
        if current != path:
            self._host.rebind_to_out_path(model, path)
        self._host.remember_set_loads(
            model,
            requested=requested,
            got=raw["loads"],
            dropped_zero=dropped,
            tolerance_ratio=self._tolerance(),
            connection=connection,
            load_map_status=self._load_map.status,
        )

    def _load_result(
        self,
        tool: str,
        model: str,
        raw: Mapping[str, Any],
        connection: str,
        timing: tuple[Timestamp, int],
        inputs: _Inputs,
    ) -> SuccessEnvelope:
        path, host = self._bound(model)
        loading = self._canonical(raw, path, connection)
        return self._store_result(
            tool,
            "harness.idea_loads/1",
            loading.model_dump(mode="json"),
            host,
            inputs,
            timing,
            summary={"saved_file": {"name": path.name, "sha256": loading.file_sha256}},
        )

    async def preview(self, tool: str, args: _Obj) -> Preview:
        descriptor = self._find(tool)
        timing = self._timing()
        if tool != _SET:
            call_args = dict(args)
            key = call_args.pop("model", None) if tool != _STATUS else None
            validated = validate_call(
                self._models[descriptor.args_model], call_args, source=self._store, current_revision=self._revision
            )
            payload = validated.model.model_dump(mode="json", exclude_none=True)
            if "path" in payload:
                payload["path"] = self._relative(Path(payload["path"]))
            models: tuple[ModelHandle, ...] = ()
            host = None
            if isinstance(key, str):
                _, host = self._bound(key)
                models = (ModelHandle(model_key=key, model_id=host.model_id, revision=host.model_revision),)
            value = self._store_result(tool, _OUTPUT, {"value": payload}, host, validated.inputs, timing)
            return Preview(
                items=(
                    PreviewItem(id=tool, label=tool, refs=(Ref.model_validate({"$ref": f"{value.result_id}#/value"}),)),
                ),
                models=models,
                diff_ref=None,
            )
        work = await self._prepare(args)
        plan = work.plan.model_dump(mode="json", by_alias=True, exclude={"model"})
        plan["path"] = self._relative(work.path)
        load_map: dict[str, JsonValue] = {
            "status": self._load_map.status,
            "sign_convention": self._load_map.sign_convention,
            "components": {name: asdict(component) for name, component in self._load_map.components.items()},
        }
        proposed = _loads.host_loads_to_canonical(
            connection=work.plan.connection, effects=work.requested, file_sha256=work.before.file_sha256
        )
        records = (plan, load_map, proposed.model_dump(mode="json", exclude={"file_sha256"}))
        stored = (
            self._store_result(tool, _OUTPUT, {"value": value}, work.host, work.inputs, timing) for value in records
        )
        refs = tuple(Ref.model_validate({"$ref": f"{record.result_id}#/value"}) for record in stored)
        handle = ModelHandle(model_key=work.plan.model, model_id=work.host.model_id, revision=work.host.model_revision)
        return Preview(
            items=(PreviewItem(id=tool, label=f"{tool}: {work.plan.model}", refs=refs),),
            models=(handle,),
            diff_ref=None,
        )

    async def read_back(self, tool: str, args: _Obj) -> Envelope | None:
        self._find(tool)
        if tool == _OPEN:
            return await self._dispatch(self._find(_LIST), {}, "", self._rest_model)
        if tool != _SET:
            return None
        timing = self._timing()
        plan = self._plan(args)
        path, _ = self._bound(plan.model)
        raw = await self._read(_LOADS, {"path": str(path), "connection_id": plan.connection}, CallEffect.READ)
        return self._load_result(tool, plan.model, raw, plan.connection, timing, {})

    def supports_reconcile(self, tool: str) -> bool:
        return tool in (_SET, _CALC) and any(entry.name == tool for entry in self._allowlist.tools)

    def _lost_loading(self, tool: str, args: _Obj, op_id: str) -> _tools.NativeSetLoadsArgs | None:
        try:
            entry = self._idea_ledger.find(op_id)
            if (
                entry is None
                or entry.tool != tool
                or entry.target.route != "native"
                or entry.args_sha256 != payload_sha256(dict(args))
                or not entry.pre_image_ref
                or not entry.pre_image_ref.endswith(_OBSERVED)
            ):
                return None
            rule = RefRule(kinds=frozenset({_OUTPUT}), stale_ok=True)
            IdeaLoads.model_validate(resolve_ref(entry.pre_image_ref, rule, self._store, self._revision).value)
            ref = entry.pre_image_ref.removesuffix(_OBSERVED) + "#/value/sent"
            sent = resolve_ref(ref, rule, self._store, self._revision).value
            if not isinstance(sent, dict) or sent.get("confirm") is not True or sent.get("path") != entry.target.file:
                return None
            request = _tools.NativeSetLoadsArgs.model_validate(
                {key: value for key, value in sent.items() if key != "confirm"}
            )
            source, out = (
                require_inside_run(self._run_dir / file, self._run_dir) for file in (request.path, request.out_path)
            )
            if (
                not request.loads
                or source == out
                or any(Path(file).is_absolute() for file in (request.path, request.out_path))
            ):
                return None
            return request.model_copy(update={"path": str(source), "out_path": str(out)})
        except ContractError, OSError, ValidationError:
            return None

    async def reconcile(self, tool: str, args: _Obj, op_id: str) -> Reconciliation:
        descriptor = self._find(tool)
        timing = self._timing()
        result = None
        host = None
        if tool == _CALC:
            # T8's REST rule returns unknown without asking the host for stale or abandoned checks.
            call_args = {key: value for key, value in args.items() if key != "model"}
            try:
                validated = _tools.CalculateArgs.model_validate(call_args)
                lost = cast(LostWrite, _LostLoading(descriptor, validated))
                decision = await IdeaReconciler(tolerance_ratio=None).decide(lost, self._read)
            except ContractError, ValidationError:
                decision = Decision(outcome="unknown", evidence={"reason": "no valid IDEA write evidence"})
        else:
            decision = Decision(outcome="unknown", evidence={"reason": "no valid IDEA write evidence"})
            if tool == _SET and (request := self._lost_loading(tool, args, op_id)) is not None:
                observed: dict[str, Any] = {}

                async def read(name: str, sent: dict[str, Any], effect: CallEffect) -> dict[str, Any]:
                    observed.update(await self._read(name, sent, effect))
                    return observed

                # IdeaReconciler reads only descriptor and model. Its shared annotation also carries a CSI PID.
                lost = cast(LostWrite, _LostLoading(descriptor, request))
                try:
                    plan = self._plan(args)
                    path, host = self._bound(plan.model)
                    if request.connection_id == plan.connection and path in (
                        Path(request.path),
                        Path(request.out_path),
                    ):
                        decision = await IdeaReconciler(tolerance_ratio=self._tolerance()).decide(lost, read)
                    if decision.outcome == "applied":
                        self._settle_loads(
                            plan.model, Path(request.out_path), request.connection_id, request.loads, observed, []
                        )
                        result = self._load_result(tool, plan.model, observed, request.connection_id, timing, {})
                except ContractError as error:
                    decision = Decision(outcome="unknown", evidence={"read_failed": error.detail.code.value})
        evidence = self._store_result(
            tool, _OUTPUT, {"value": _replies.reduce_paths(decision.evidence)}, host, {}, timing
        )
        self._health.reconciled(op_id)
        return Reconciliation(
            outcome=decision.outcome,
            result=result,
            evidence=(Ref.model_validate({"$ref": f"{evidence.result_id}#/value"}),),
        )
