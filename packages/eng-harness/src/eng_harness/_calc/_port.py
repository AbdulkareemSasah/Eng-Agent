"""HarnessCalcPort: the engine's `CalcPort` over the calc registry, approvals and the result store (spec 0003 4.12).

Purpose: `describe` publishes a calc's identity, status and the `RefRule` of each reference field; `run` checks the
status against the run class, validates the input with references required, builds `InputMeta` from the records,
applies the item limit, runs the pure function, adds `CalcMeta`, the draft mark and the trace, and stores the result.
`preflight` lists the calcs a run may not use. Units: those of the calc inputs; none here.
Errors: contract errors become failure envelopes; `CalcRefused` (`CALC_NOT_APPROVED`, `CALC_WITHDRAWN`) and
`NotImplementedGap` propagate; any other exception is a defect, reported as `INTERNAL` with an incident id and logged.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated

from eng_contract.envelope import FailureEnvelope, Provenance, RefInput, SuccessEnvelope, make_failure, make_success
from eng_contract.errors import ContractError, ContractWarning, ErrorCode, WarningCode
from eng_contract.ids import Clock, IdSource
from eng_contract.params import InputPolicy, validate_input
from eng_contract.refs import RefRule, parse_ref
from eng_contract.store import ResultStore
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from eng_harness import __version__
from eng_harness._calc._approvals import ApprovalsFile, resolve_status
from eng_harness._calc._code_packs import CodePackRoute
from eng_harness.calc import CalcDef, CalcInput, CalcRegistry, CalcStatus, InputMeta, RefMeta, TraceBuilder
from eng_harness.errors import CalcRefused, HarnessCode, StepError
from eng_harness.kinds.calcs import CalcMeta
from eng_harness.ports import CalcInfo, RunClass

_LOG = logging.getLogger(__name__)
_DRAFT = (CalcStatus.DRAFT, CalcStatus.VERIFIED)
_Obj = Mapping[str, JsonValue]


class CalcSettings(BaseModel):
    """Resource limits of the CalcPort (from `harness.toml`, not engineering content); `max_items` has no default."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_items: Annotated[int, Field(ge=1)]


@dataclass(frozen=True, slots=True)
class CalcRefusal:
    """A calc a run may not use: its id, status and the harness code `run` would refuse it with."""

    calc_id: str
    status: CalcStatus
    code: HarnessCode


def _count_items(value: JsonValue) -> int:
    """The number of list elements in `value`, nested lists included."""
    if isinstance(value, list):
        return len(value) + sum(_count_items(v) for v in value)
    if isinstance(value, dict):
        return sum(_count_items(v) for v in value.values())
    return 0


class HarnessCalcPort:
    """The engine's `CalcPort` for the calcs of the registry (spec 0003 4.12).

    `basis_fields` maps a calc id to the basis paths it reads (`CalcInfo.basis_fields`); the calc declaration has no
    such field yet, so a calc that reads the basis is listed by its caller. `code_packs` is the route that serves an
    id that does not start with `harness.` (spec 0003 4.12 item 4); without it such an id is unknown.
    """

    def __init__(  # B-144: the seven collaborators of spec 0003 4.12, plus the basis map
        self,
        registry: CalcRegistry,
        approvals: ApprovalsFile,
        store: ResultStore,
        settings: CalcSettings,
        run_class: RunClass,
        clock: Clock,
        ids: IdSource,
        *,
        basis_fields: Mapping[str, Sequence[str]] | None = None,
        code_packs: CodePackRoute | None = None,
    ) -> None:
        """Hold the collaborators; the run class does not change.

        Raises:
            ValueError: the route has another run class than the port.
        """
        if code_packs is not None and code_packs.run_class is not run_class:
            raise ValueError("the code-pack route and the port must have the same run class")
        self._packs = code_packs
        self._registry, self._approvals, self._store, self._settings = registry, approvals, store, settings
        self._run_class, self._clock, self._ids = run_class, clock, ids
        self._basis = dict(basis_fields or {})

    @property
    def run_class(self) -> RunClass:
        """The run class given at construction."""
        return self._run_class

    def _routed(self, calc_id: str) -> CodePackRoute | None:
        """The code-pack route for an id that does not start with `harness.`, else `None`."""
        return None if calc_id.startswith("harness.") else self._packs

    def _find(self, calc_id: str) -> tuple[CalcDef, str, CalcStatus]:
        if calc_id not in self._registry:
            raise ContractError(ErrorCode.NOT_FOUND, "unknown calc", received=calc_id[:200])
        definition, digest = self._registry[calc_id], self._registry.content_hash(calc_id)
        return definition, digest, resolve_status(definition, digest, self._approvals)

    def _refusal(self, calc_id: str, status: CalcStatus) -> CalcRefusal | None:
        if status is CalcStatus.WITHDRAWN:
            return CalcRefusal(calc_id, status, HarnessCode.CALC_WITHDRAWN)
        if self._run_class is RunClass.PRODUCTION and status is not CalcStatus.APPROVED:
            return CalcRefusal(calc_id, status, HarnessCode.CALC_NOT_APPROVED)
        return None

    def preflight(self, calc_ids: Sequence[str]) -> list[CalcRefusal]:
        """List the calcs `run` would refuse: withdrawn ones, and in a production run every one not approved.

        Raises:
            ContractError: `NOT_FOUND` for an unknown id.
        """
        refused: list[CalcRefusal] = []
        for calc_id in calc_ids:
            if (route := self._routed(calc_id)) is not None:
                if (hit := route.refusal(calc_id)) is not None:
                    refused.append(CalcRefusal(calc_id, *hit))
            elif (refusal := self._refusal(calc_id, self._find(calc_id)[2])) is not None:
                refused.append(refusal)
        return refused

    def describe(self, calc_id: str) -> CalcInfo:
        """Return the calc's info; `ref_rules` come from the `x-eng` metadata of the input schema (AC13).

        Raises:
            ContractError: `NOT_FOUND` for an unknown id.
        """
        if (route := self._routed(calc_id)) is not None:
            return route.describe(calc_id)
        definition, digest, status = self._find(calc_id)
        properties = self._input_type(definition).model_json_schema()["properties"]
        rules = {
            name: RefRule(kinds=frozenset(meta["ref_kinds"]), unit=meta["unit"], stale_ok=meta["stale_ok"], field=name)
            for name, prop in properties.items()
            if (meta := prop.get("x-eng", {})).get("ref_capable")
        }
        return CalcInfo(
            id=calc_id,
            version=definition.version,
            content_sha256=digest,
            status=status,
            engineering_params=tuple(rules),
            basis_fields=tuple(self._basis.get(calc_id, ())),
            ref_rules=rules,
        )

    @staticmethod
    def _input_type(definition: CalcDef) -> type[CalcInput]:
        input_type = definition.input_type
        if not (isinstance(input_type, type) and issubclass(input_type, CalcInput)):
            raise TypeError(f"{definition.id}: input type is no CalcInput")  # the registry checked this at load
        return input_type

    def run(self, calc_id: str, args: _Obj) -> SuccessEnvelope | FailureEnvelope:
        """Run a calc (spec 0003 4.12 item 2); nothing is stored unless the run succeeds.

        Raises:
            CalcRefused: the calc is withdrawn, or not approved in a production run.
            NotImplementedGap: the calc reached a path marked not implemented.
        """
        if (route := self._routed(calc_id)) is not None:
            return route.run(calc_id, args)
        try:
            return self._run(calc_id, args)
        except ContractError as exc:
            return make_failure(exc)
        except StepError:
            raise
        except Exception as exc:  # B-144: a defect of a calc is INTERNAL (spec 4.2), logged with its incident id
            incident = self._ids.new_ulid()
            _LOG.exception("calc defect", extra={"calc_id": calc_id, "incident_id": incident})
            return make_failure(
                ContractError(ErrorCode.INTERNAL, f"calc {calc_id} failed: {type(exc).__name__}", incident_id=incident)
            )

    def _run(self, calc_id: str, args: _Obj) -> SuccessEnvelope | FailureEnvelope:
        definition, digest, status = self._find(calc_id)
        if (refusal := self._refusal(calc_id, status)) is not None:
            raise CalcRefused(refusal.code, f"{calc_id} is {status.value}", evidence=[calc_id])
        started, began = self._clock.now(), self._clock.now_ms()
        validated = validate_input(
            self._input_type(definition),
            args,
            source=self._store,
            current_revision=lambda _: None,
            policy=InputPolicy(require_refs=True),
        )
        refs = {name: i.ref for name, i in validated.inputs.items() if isinstance(i, RefInput)}
        records = {name: self._store.get(parse_ref(ref)[0]) for name, ref in refs.items()}
        meta = InputMeta(
            refs={
                name: RefMeta(
                    result_id=r.result_id,
                    ref=refs[name],
                    kind=r.kind,
                    complete=r.complete,
                    model_id=r.producer.host.model_id if r.producer.host else None,
                    model_revision=r.producer.host.model_revision if r.producer.host else None,
                    parents=tuple(r.parents),
                    producer_tool=r.producer.tool,
                )
                for name, r in records.items()
            }
        )
        parents = list(dict.fromkeys(r.result_id for r in records.values()))
        items = sum(_count_items(dict(self._store.payload(p))) for p in parents)
        if items > self._settings.max_items:
            raise ContractError(
                ErrorCode.LIMIT_EXCEEDED,
                "the referenced records hold more items than the calc may take",
                expected={"max": self._settings.max_items},
                received=items,
            )
        trace = TraceBuilder()
        body = definition(validated.model, meta, trace)
        draft = status in _DRAFT
        payload = body.model_dump(mode="json") | {
            "calc": CalcMeta(id=calc_id, version=definition.version, content_sha256=digest, status=status).model_dump(
                mode="json"
            ),
            "draft": draft,
            "trace": trace.build(definition, digest).model_dump(mode="json"),
        }
        complete = payload.get("complete")
        producer = Provenance(
            tool="harness",
            tool_version=__version__,
            inputs={name: RefInput(ref=ref) for name, ref in refs.items()},
            started_at=started,
            duration_ms=max(0, self._clock.now_ms() - began),
        )
        record = self._store.put(
            definition.output_kind,
            payload,
            producer,
            parents,
            complete=complete if isinstance(complete, bool) else True,
        )
        summary: dict[str, JsonValue] = {
            "calc": calc_id,
            "version": definition.version,
            "status": status.value,
            "draft": draft,
        }
        warnings = (
            []
            if record.complete
            else [ContractWarning(code=WarningCode.PARTIAL_DATA, message="the result is not complete")]
        )
        return make_success(record, summary, warnings)
