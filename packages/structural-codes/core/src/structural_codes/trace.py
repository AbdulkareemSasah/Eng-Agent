"""Trace recorder of one evaluation (spec 0001 section 4.5; EC section 4.9).

Purpose: `TraceRecorder` records the inputs, cited constants and calculation steps of one evaluation and converts them
to the contract's `Trace`. The content hash is passed in as a value, so the recorder never hashes anything.
Units: a step or constant unit is a symbol of `eng_contract.units.UNITS` or None; a unit suffix in a name
(`_kN`, `_mm2`, ...) fixes the unit to the suffix's canonical unit (AC10). Values are float64.
Errors: `CheckDefinitionError` for a reused or malformed name, an unrecorded `uses` entry, a wrong unit or an
unbuildable trace; `TraceValueError` for a NaN, infinite or non-numeric step value (AC8).
"""

import math
import re
from collections.abc import Sequence

from eng_contract.cited import Cited
from eng_contract.envelope import RefInput
from eng_contract.params import ParamSpec, ValidatedInput
from eng_contract.quantity import Quantity
from eng_contract.trace import Trace, TraceConstant, TraceInput, TraceStep
from eng_contract.units import UNITS, kind_for_field
from eng_contract.verdicts import Subject, VerdictStatus
from pydantic import JsonValue, ValidationError

from structural_codes._verdict import DEFAULT_RATIO_LIMIT, VerdictDraft, assess
from structural_codes.errors import CheckDefinitionError, TraceValueError
from structural_codes.inputs import CheckInputs, _UnboundedSpec

__all__ = ["TraceRecorder"]

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class TraceRecorder:
    """Records one evaluation; created by the runner, used by the check body (`t.const`, `t.step`, `t.value`)."""

    def __init__(
        self,
        validated: ValidatedInput[CheckInputs],
        *,
        calc_id: str,
        calc_version: str,
        content_sha256: str,
        subject: Subject,
    ) -> None:
        """Record every input field of `validated` (unit from the field metadata, `ref` from the provenance).

        An unbounded field adds the message `<field>: unbounded (<reason>)` (AC4b).
        """
        self._header = (calc_id, calc_version, content_sha256, subject)
        self._names: set[str] = set()
        self._values: dict[str, float] = {}
        self._inputs: list[TraceInput] = []
        self._constants: list[TraceConstant] = []
        self._steps: list[TraceStep] = []
        self._messages: list[str] = []
        self._units: dict[str, str | None] = {}
        self._verdicts: list[VerdictDraft] = []
        dumped = validated.model.model_dump(mode="json")
        for name, info in type(validated.model).model_fields.items():
            spec = info.json_schema_extra
            unit = spec.unit if isinstance(spec, ParamSpec) else None
            provenance = validated.inputs.get(name)
            value: JsonValue = dumped[name]
            ref = provenance.ref if isinstance(provenance, RefInput) else None
            self._inputs.append(TraceInput(name=name, value=value, unit=unit, ref=ref))
            self._names.add(name)
            self._units[name] = unit
            if isinstance(value, bool | int | float):
                self._values[name] = float(value)
            if isinstance(spec, _UnboundedSpec):
                self._messages.append(f"{name}: unbounded ({spec.reason})")

    def _claim(self, name: str, unit: str | None) -> None:
        """Check a new name and its unit; nothing is recorded.

        Raises:
            CheckDefinitionError: malformed or reused name, unknown unit, or a unit that differs from the suffix's.
        """
        if not _NAME.fullmatch(name):
            raise CheckDefinitionError(f"{name!r} is not a valid name")
        if name in self._names:
            raise CheckDefinitionError(f"name {name!r} is already recorded")
        if unit is not None and unit not in UNITS:
            raise CheckDefinitionError(f"{name}: unknown unit {unit!r}")
        kind = kind_for_field(name)
        if kind is not None and unit != kind.canonical_unit:
            raise CheckDefinitionError(f"{name}: the suffix fixes the unit {kind.canonical_unit!r}, got {unit!r}")

    def const(self, name: str, cited: Cited) -> float:
        """Record a cited constant and return its value as a float.

        Raises:
            CheckDefinitionError: see `_claim`.
        """
        self._claim(name, cited.unit)
        self._constants.append(TraceConstant(name=name, cited=cited))
        self._names.add(name)
        self._units[name] = cited.unit
        self._values[name] = float(cited.value)
        return self._values[name]

    def step(
        self, name: str, value: float | bool, *, unit: str | None, formula: str, source: str, uses: Sequence[str]
    ) -> float:
        """Record a calculation step and return its value as a float (a `bool` is kept as a logical step).

        Raises:
            CheckDefinitionError: see `_claim`, or `uses` names something not recorded earlier.
            TraceValueError: `value` is NaN, infinite or not a number.
        """
        self._claim(name, unit)
        missing = [u for u in uses if u not in self._names]
        if missing:
            raise CheckDefinitionError(f"step {name}: uses {missing} which are not recorded earlier")
        if not isinstance(value, bool | int | float) or not math.isfinite(value):
            raise TraceValueError(f"step {name}: value {value!r} is not a finite number")
        stored = value if isinstance(value, bool) else float(value)
        try:
            recorded = TraceStep(name=name, value=stored, unit=unit, formula=formula, source=source, uses=list(uses))
        except ValidationError as exc:
            raise CheckDefinitionError(f"step {name}: invalid step: {exc}") from exc
        self._steps.append(recorded)
        self._names.add(name)
        self._units[name] = unit
        self._values[name] = float(value)
        return self._values[name]

    def value(self, name: str) -> float:
        """Return a recorded numeric value.

        Raises:
            CheckDefinitionError: the name is unknown, or the input has no numeric value (None or text).
        """
        if name not in self._names:
            raise CheckDefinitionError(f"unknown name {name!r}")
        if name not in self._values:
            raise CheckDefinitionError(f"{name!r} has no numeric value")
        return self._values[name]

    def note(self, text: str) -> None:
        """Add a trace message."""
        self._messages.append(text)

    @property
    def verdicts(self) -> tuple[VerdictDraft, ...]:
        """The verdicts built so far, in order; the runner turns them into contract verdicts."""
        return tuple(self._verdicts)

    def _operand(self, name: str) -> tuple[float, str]:
        """Return a recorded value and its unit symbol (`"1"` for a name without a unit)."""
        return self.value(name), self._units[name] or "1"

    def verdict(
        self, *, demand: str, capacity: str, clause: str | None = None, assumptions: Sequence[str] = ()
    ) -> None:
        """Build one verdict from two recorded names (AC11, AC12); `clause` is checked by `build_verdict`.

        Records step `ratio` (`ratio_2`, ... for later verdicts) and decides the status against the reserved input
        `ratio_limit` (the contract default when null). An unusable demand or capacity gives an `ERROR` draft with a
        trace message and no ratio step. Units: both names must have one unit, or none.

        Raises:
            CheckDefinitionError: a name is unknown or has no numeric value, the two differ in dimension or unit,
                or the ratio name is taken.
        """
        demand_value, demand_unit = self._operand(demand)
        capacity_value, capacity_unit = self._operand(capacity)
        if UNITS[demand_unit].dimension != UNITS[capacity_unit].dimension:
            raise CheckDefinitionError(f"{demand} ({demand_unit}) and {capacity} ({capacity_unit}) differ in dimension")
        if demand_unit != capacity_unit:
            raise CheckDefinitionError(f"{demand} and {capacity} must be recorded in the same unit")
        limit = self._values.get("ratio_limit")
        limit = DEFAULT_RATIO_LIMIT if limit is None else limit
        ratio, status, message = assess(demand, demand_value, capacity, capacity_value, limit)
        ordinal = len(self._verdicts) + 1
        ratio_name = None
        if ratio is not None:
            ratio_name = "ratio" if ordinal == 1 else f"ratio_{ordinal}"
            self.step(
                ratio_name,
                ratio,
                unit="1",
                formula="demand / capacity",
                source="04-tool-contract §5.1",
                uses=[demand, capacity],
            )
        if message is not None:
            self.note(message)
        self._verdicts.append(
            VerdictDraft(
                status,
                demand,
                capacity,
                Quantity(demand_value, demand_unit),
                Quantity(capacity_value, capacity_unit),
                ratio_name,
                ratio,
                limit,
                clause,
                tuple(assumptions),
            )
        )

    def to_trace(self, *, outputs: Sequence[str], status: VerdictStatus | None) -> Trace:
        """Build the contract `Trace` with the runner's `outputs` and `status` (AC9).

        Raises:
            CheckDefinitionError: the recorded content does not validate as a `Trace` (for example an output that
                is no input or step, or a text over the contract's length limit).
        """
        calc_id, calc_version, content_sha256, subject = self._header
        try:
            return Trace(
                calc_id=calc_id,
                calc_version=calc_version,
                content_sha256=content_sha256,
                subject=subject,
                inputs=list(self._inputs),
                constants=list(self._constants),
                steps=list(self._steps),
                outputs=list(outputs),
                status=status,
                messages=list(self._messages),
            )
        except ValidationError as exc:
            raise CheckDefinitionError(f"{calc_id}: the recorded trace is invalid: {exc}") from exc
