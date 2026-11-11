"""CodePackRoute: the one way a code-pack check reaches the CalcPort (spec 0010 4.3; spec 0003 4.12 item 4).

Purpose: `describe` publishes a check of a `structural-codes` pack as a `CalcInfo`; `run` evaluates a batch of items
with `structural_codes.evaluate_batch` (references only, `require_refs`) and stores the payload as `verdicts.set/1`
with provenance tool `structural-codes/evaluate_batch`, the pack version and the references of every item (parents).
The route runs the ids of a fixed allowlist and no other, and `HarnessCalcPort` consults it for an id that does not
start with `harness.`. `run` takes `{"items": [{"subject", "inputs"}]}` or `{"batch": {"$ref": ...}}` (a reference
to that list).
Units: those of the check inputs; none here.
Errors: contract errors become failure envelopes; an id outside the allowlist or unknown to the registry is
`NOT_FOUND` before any evaluation; `CalcRefused` (`CALC_WITHDRAWN` in both run classes, `CALC_NOT_APPROVED` for a check
that is not approved in `production`) propagates before any evaluation, so the pack's `CheckNotUsable` is never
reached; a gap of a check is a verdict, any other exception is a defect, reported as `INTERNAL` with an incident id.
"""

import logging
from collections.abc import Collection, Mapping
from typing import Any, Final

from eng_contract.envelope import (
    FailureEnvelope,
    LiteralInput,
    Provenance,
    RefInput,
    SuccessEnvelope,
    make_failure,
    make_success,
)
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock, IdSource
from eng_contract.params import InputPolicy
from eng_contract.refs import RefRule, parse_ref, resolve_ref
from eng_contract.store import ResultStore
from eng_contract.verdicts import Subject
from pydantic import JsonValue, ValidationError
from structural_codes import BatchItem, Mode, evaluate_batch
from structural_codes.content_hash import content_hash
from structural_codes.lifecycle import resolve_state
from structural_codes.pack import Registry

from eng_harness.calc import CalcStatus
from eng_harness.errors import CalcRefused, HarnessCode, StepError
from eng_harness.ports import CalcInfo, RunClass

CODE_PACK_TOOL: Final = "structural-codes/evaluate_batch"
"""Provenance tool of a stored code-pack result: the contract's `<server>/<tool>` form (04 4.2.2) of the specs'
`structural-codes`, which the contract's pattern refuses on its own (owner queue, B-393)."""

FOOTING_CHECK_IDS: Final = (
    "aci318_14.13_3_1_1.bearing_pressure_service",
    "aci318_14.22_5_5_1.one_way_shear",
    "aci318_14.22_6_5_2.punching_shear",
    "aci318_14.13_2_7_1.flexure_at_column_face",
    "aci318_14.8_6_1_1.min_flexural_reinforcement",
    "aci318_14.25_4_2_3.development_length_bottom_bars",
)
"""The six ACI 318-14 footing checks (spec 0010 4.3); the SBC ids from `check_id_for` join them with plan 0010 T9."""

COLUMN_CHECK_IDS: Final = (
    "aci318_14.22_4_2_1.max_axial_strength",
    "aci318_14.22_4_1_1.axial_flexure_uniaxial",
    "aci318_14.10_6_1_1.longitudinal_reinforcement_limits",
)
"""The three column checks of spec 0013 4.5, which the route shares (spec 0010 C3)."""

ALLOWED_CHECK_IDS: Final = frozenset(FOOTING_CHECK_IDS) | frozenset(COLUMN_CHECK_IDS)
"""The fixed allowlist: any other id is `NOT_FOUND`."""

_LOG = logging.getLogger(__name__)
_Obj = Mapping[str, JsonValue]


def _untracked(_model_id: str) -> int | None:
    """Revision function of the route: the engine already checked staleness (spec 0003 4.12 item 2)."""
    return None


def _invalid(message: str, field: str | None = None) -> ContractError:
    return ContractError(ErrorCode.INVALID_ARGUMENT, message, field=field)


def _batch_item(k: int, raw: JsonValue) -> BatchItem:
    """Turn one raw item `{"subject": ..., "inputs": {...}}` into a `BatchItem`.

    Raises:
        ContractError: `INVALID_ARGUMENT` for any other shape or a subject that is not valid.
    """
    if not (isinstance(raw, dict) and set(raw) == {"subject", "inputs"} and isinstance(raw["inputs"], dict)):
        raise _invalid("an item is an object with exactly subject and inputs", f"items[{k}]")
    try:
        subject = Subject.model_validate(raw["subject"])
    except ValidationError as exc:
        raise _invalid(f"invalid subject: {exc.errors()[0]['msg'][:200]}", f"items[{k}].subject") from exc
    return BatchItem(subject, raw["inputs"])


class CodePackRoute:
    """The code-pack checks of the allowlist, served to `HarnessCalcPort` (spec 0010 4.3)."""

    def __init__(  # B-393: the collaborators of spec 0003 4.12, plus the registry and the allowlist
        self,
        registry: Registry,
        store: ResultStore,
        *,
        max_items: int,
        run_class: RunClass,
        clock: Clock,
        ids: IdSource,
        allowed: Collection[str] = ALLOWED_CHECK_IDS,
    ) -> None:
        """Hold the collaborators; `registry` is built once at engine construction, the run class does not change."""
        self._registry, self._store, self._max_items = registry, store, max_items
        self._run_class, self._clock, self._ids, self._allowed = run_class, clock, ids, frozenset(allowed)

    @property
    def run_class(self) -> RunClass:
        """The run class given at construction."""
        return self._run_class

    def _find(self, check_id: str) -> tuple[Any, str, CalcStatus]:
        if check_id not in self._allowed:
            raise ContractError(ErrorCode.NOT_FOUND, "unknown calc", received=check_id[:200])
        check = self._registry.get(check_id)  # NOT_FOUND for an id the registry does not know
        digest = content_hash(check)
        return check, digest, CalcStatus(resolve_state(check, self._registry, digest=digest))

    def refusal(self, check_id: str) -> tuple[CalcStatus, HarnessCode] | None:
        """The status and code `run` would refuse the check with, or `None`.

        Raises:
            ContractError: `NOT_FOUND` for an id outside the allowlist or unknown to the registry.
        """
        status = self._find(check_id)[2]
        if status is CalcStatus.WITHDRAWN:
            return status, HarnessCode.CALC_WITHDRAWN
        if self._run_class is RunClass.PRODUCTION and status is not CalcStatus.APPROVED:
            return status, HarnessCode.CALC_NOT_APPROVED
        return None

    def describe(self, check_id: str) -> CalcInfo:
        """Return the check's info: `version` is `CheckMeta.version`, `status` its lifecycle state, `ref_rules` the
        reference-capable inputs (never `stale_ok`), `basis_fields` empty (a check declares no basis source).

        Raises:
            ContractError: `NOT_FOUND` for an id outside the allowlist or unknown to the registry.
        """
        check, digest, status = self._find(check_id)
        properties = check.inputs.model_json_schema()["properties"]
        rules = {
            name: RefRule(kinds=frozenset(meta["ref_kinds"]), unit=meta["unit"], field=name)
            for name, prop in properties.items()
            if (meta := prop.get("x-eng", {})).get("ref_capable")
        }
        return CalcInfo(
            id=check_id,
            version=check.meta.version,
            content_sha256=digest,
            status=status,
            engineering_params=tuple(rules),
            basis_fields=(),
            ref_rules=rules,
        )

    def run(self, check_id: str, args: _Obj) -> SuccessEnvelope | FailureEnvelope:
        """Evaluate a batch (spec 0010 4.3 item 2); nothing is stored unless the evaluation succeeds.

        Raises:
            CalcRefused: the check is withdrawn, or not approved in a production run.
        """
        try:
            return self._run(check_id, args)
        except ContractError as exc:
            return make_failure(exc)
        except StepError:
            raise
        except Exception as exc:  # B-393: a defect of a pack is INTERNAL (spec 0003 4.12 item 3), logged with its id
            incident = self._ids.new_ulid()
            _LOG.exception("code pack defect", extra={"check_id": check_id, "incident_id": incident})
            return make_failure(
                ContractError(
                    ErrorCode.INTERNAL, f"check {check_id} failed: {type(exc).__name__}", incident_id=incident
                )
            )

    def _raw_items(self, args: _Obj) -> tuple[list[JsonValue], dict[str, RefInput | LiteralInput]]:
        """The raw item list of either argument form and the `batch` provenance input (none for `items`)."""
        inputs: dict[str, RefInput | LiteralInput] = {}
        if set(args) == {"items"}:
            raw, field = args["items"], "items"
        elif set(args) == {"batch"}:
            ref = args["batch"]
            if not (isinstance(ref, dict) and set(ref) == {"$ref"} and isinstance(ref["$ref"], str)):
                raise _invalid("batch is a reference object", "batch")
            resolved = resolve_ref(ref["$ref"], RefRule(field="batch"), self._store, _untracked, ids=self._ids)
            raw, field, inputs["batch"] = resolved.value, "batch", RefInput(ref=ref["$ref"])
        else:
            raise _invalid("give exactly one of items and batch")
        if not isinstance(raw, list):
            raise _invalid("the items are a list", field)
        if len(raw) > self._max_items:
            raise ContractError(
                ErrorCode.LIMIT_EXCEEDED,
                "more items than the route may take",
                expected={"max": self._max_items},
                received=len(raw),
            )
        return raw, inputs

    def _run(self, check_id: str, args: _Obj) -> SuccessEnvelope | FailureEnvelope:
        check = self._find(check_id)[0]
        if (refusal := self.refusal(check_id)) is not None:
            raise CalcRefused(refusal[1], f"{check_id} is {refusal[0].value}", evidence=[check_id])
        started, began = self._clock.now(), self._clock.now_ms()
        raw, inputs = self._raw_items(args)
        mode: Mode = "production" if self._run_class is RunClass.PRODUCTION else "trial"
        evaluation = evaluate_batch(
            check_id,
            [_batch_item(k, item) for k, item in enumerate(raw)],
            mode=mode,
            registry=self._registry,
            source=self._store,
            current_revision=_untracked,
            policy=InputPolicy(require_refs=True),
        )
        for k, per_item in enumerate(evaluation.inputs_provenance):
            inputs |= {f"items[{k}].{name}": value for name, value in per_item.items()}
        referenced = (parse_ref(v.ref)[0] for v in inputs.values() if isinstance(v, RefInput))
        pack = next(p for p in self._registry.packs if p.name == check.meta.pack)
        record = self._store.put(
            "verdicts.set/1",
            evaluation.payload.model_dump(mode="json"),
            Provenance(
                tool=CODE_PACK_TOOL,
                tool_version=pack.version,
                inputs=inputs,
                started_at=started,
                duration_ms=max(0, self._clock.now_ms() - began),
            ),
            list(dict.fromkeys(referenced)),
        )
        counts: dict[str, JsonValue] = {s.value: n for s, n in evaluation.payload.counts.items()}
        summary: dict[str, JsonValue] = {
            "check_id": check_id,
            "items": len(raw),
            "counts": counts,
            "draft": evaluation.payload.draft,
        }
        return make_success(record, summary)
