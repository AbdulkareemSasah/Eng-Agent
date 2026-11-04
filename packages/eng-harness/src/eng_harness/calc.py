"""Calc framework: decorator, registry, input metadata, trace builder and statuses (spec 0003 4.1, 4.2).

Purpose: a calc is a pure function registered under a stable id; the registry checks the registration rules and holds
the content hash; the trace builder builds the contract `Trace` that every calc result carries.
Units: none here; units belong to the calc inputs and trace values.
Errors: `CalcRegistryError` (programming error, names the broken rule), `TraceError` (a trace built wrongly);
a calc itself raises `ContractError` or `NotImplementedGap`.
"""

import inspect
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import get_type_hints

from eng_contract.cited import Cited
from eng_contract.kinds import KindRegistry
from eng_contract.params import ParamModel
from eng_contract.trace import Trace, TraceConstant, TraceInput, TraceStep
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness.errors import NotImplementedGap

__all__ = [
    "CalcDef",
    "CalcInput",
    "CalcRegistry",
    "CalcRegistryError",
    "CalcStatus",
    "InputMeta",
    "NotImplementedGap",
    "RefMeta",
    "TraceBuilder",
    "TraceError",
    "calc",
]

_ID = re.compile(r"^harness\.[a-z][a-z0-9_]*$")
_VERSIONS = range(1, 10000)


class CalcStatus(StrEnum):
    """Lifecycle of a calc; `approved` and `withdrawn` come only from `approvals.yaml` (spec 4.5)."""

    DRAFT = "draft"
    VERIFIED = "verified"
    APPROVED = "approved"
    WITHDRAWN = "withdrawn"


class CalcRegistryError(ValueError):
    """A registration rule is broken; `rule` names it (`id`, `version`, `input_type`, ...)."""

    def __init__(self, rule: str, calc_id: str, why: str) -> None:
        """Keep `rule` for callers and tests."""
        super().__init__(f"{calc_id}: {rule}: {why}")
        self.rule = rule


class TraceError(ValueError):
    """The trace builder was used wrongly (duplicate name, `uses` not earlier, blank source, unknown output)."""


class CalcInput(ParamModel):
    """Base class of calc input models (frozen, extra fields forbidden, parameters declared with `eng_param`)."""


class RefMeta(BaseModel):
    """What the CalcPort knows about one referenced record; the calc never reads the store."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result_id: str
    kind: str
    complete: bool
    model_id: str | None
    model_revision: int | None
    parents: tuple[str, ...]
    producer_tool: str


class InputMeta(BaseModel):
    """`RefMeta` per input field name that was given as a reference."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    refs: dict[str, RefMeta]


class TraceBuilder:
    """Collects inputs, cited constants and steps in order and builds the contract `Trace`.

    Raises:
        TraceError: a name is used twice, a step uses a name that is not earlier, a step has a blank `source`, or
            an output names no input or step.
    """

    def __init__(self) -> None:
        """Start with an empty trace."""
        self._inputs: list[TraceInput] = []
        self._constants: list[TraceConstant] = []
        self._steps: list[TraceStep] = []
        self._outputs: list[str] = []
        self._names: set[str] = set()

    def _claim(self, name: str) -> None:
        if name in self._names:
            raise TraceError(f"duplicate name {name!r}")
        self._names.add(name)

    def input(self, name: str, value: JsonValue, *, unit: str | None = None, ref: str | None = None) -> None:
        """Record an input value with its unit and the reference (or basis pointer) it came from."""
        self._claim(name)
        self._inputs.append(TraceInput(name=name, value=value, unit=unit, ref=ref))

    def constant(self, name: str, cited: Cited) -> None:
        """Record a cited constant."""
        self._claim(name)
        self._constants.append(TraceConstant(name=name, cited=cited))

    def step(
        self,
        name: str,
        value: int | float | bool | str,  # B-140: matches TraceStep.value
        *,
        formula: str,
        source: str,
        uses: Iterable[str] = (),
        unit: str | None = None,
    ) -> None:
        """Record one step; `source` names its method rule and every `uses` name must already be recorded."""
        used = tuple(uses)
        later = [u for u in used if u not in self._names]
        if later:
            raise TraceError(f"step {name!r} uses names that are not earlier: {later}")
        if not source.strip():
            raise TraceError(f"step {name!r} has a blank source")
        self._claim(name)
        self._steps.append(
            TraceStep(name=name, value=value, unit=unit, formula=formula, source=source, uses=list(used))
        )

    def output(self, *names: str) -> None:
        """Name the steps or inputs that are the calc's outputs."""
        known = {i.name for i in self._inputs} | {s.name for s in self._steps}
        unknown = [n for n in names if n not in known]
        if unknown:
            raise TraceError(f"output names no input or step: {unknown}")
        self._outputs.extend(names)

    def build(self, definition: CalcDef, content_sha256: str) -> Trace:
        """Return the `Trace` of `definition` with its content hash."""
        return Trace(
            calc_id=definition.id,
            calc_version=str(definition.version),
            content_sha256=content_sha256,
            inputs=self._inputs,
            constants=self._constants,
            steps=self._steps,
            outputs=self._outputs,
        )


@dataclass(frozen=True, slots=True)
class CalcDef:
    """A calc as declared by `@calc`: metadata and the pure function; checked when a registry takes it."""

    id: str
    version: int
    output_kind: str
    title: str
    method_source: str
    verification: str
    fn: Callable[..., BaseModel]
    input_type: object

    def __call__(self, inp: CalcInput, meta: InputMeta, trace: TraceBuilder) -> BaseModel:
        """Run the pure function."""
        return self.fn(inp, meta, trace)


def calc(
    *, id: str, version: int, output_kind: str, title: str, method_source: str, verification: str = "draft"
) -> Callable[[Callable[..., BaseModel]], CalcDef]:
    """Declare a calc (spec 4.2); the input type is the annotation of the function's first parameter."""

    def wrap(fn: Callable[..., BaseModel]) -> CalcDef:
        first = next(iter(inspect.signature(fn).parameters), None)
        input_type = get_type_hints(fn).get(first or "")
        return CalcDef(id, version, output_kind, title, method_source, verification, fn, input_type)

    return wrap


def _unhashed(definition: CalcDef) -> str:
    raise NotImplementedError("the content hash arrives with plan 0003 T2 (spec 0003 4.5)")


def _check(definition: CalcDef, kinds: KindRegistry) -> None:
    """Raise `CalcRegistryError` for the first broken registration rule (AC1)."""
    d = definition

    def fail(rule: str, why: str) -> CalcRegistryError:
        return CalcRegistryError(rule, d.id, why)

    if not _ID.fullmatch(d.id):
        raise fail("id", "must match ^harness\\.[a-z][a-z0-9_]*$")
    if type(d.version) is not int or d.version not in _VERSIONS:
        raise fail("version", "must be an integer from 1 to 9999")
    if not (isinstance(d.input_type, type) and issubclass(d.input_type, CalcInput)):
        raise fail("input_type", "the first parameter must be annotated with a CalcInput subclass")
    if not d.output_kind.startswith("harness.") or d.output_kind not in kinds:
        raise fail("output_kind", f"{d.output_kind!r} is not a registered harness kind")
    if not d.method_source.strip():
        raise fail("method_source", "must not be blank")
    if d.verification not in (CalcStatus.DRAFT, CalcStatus.VERIFIED):
        raise fail("verification", "must be 'draft' or 'verified'")


class CalcRegistry(Mapping[str, CalcDef]):
    """Immutable id to `CalcDef` mapping with the content hash of each; there is no global registration.

    Raises:
        CalcRegistryError: a calc breaks a registration rule or its id is already registered.
    """

    def __init__(
        self,
        kinds: KindRegistry,
        calcs: Iterable[CalcDef] = (),
        *,
        hasher: Callable[[CalcDef], str] = _unhashed,
    ) -> None:
        """Check and hold `calcs`; `hasher` gives the content hash (the real one arrives with T2)."""
        entries: dict[str, CalcDef] = {}
        hashes: dict[str, str] = {}
        for definition in calcs:
            _check(definition, kinds)
            if definition.id in entries:
                raise CalcRegistryError("duplicate", definition.id, "the id is already registered")
            entries[definition.id] = definition
            hashes[definition.id] = hasher(definition)
        self._calcs = MappingProxyType(entries)
        self._hashes = MappingProxyType(hashes)

    def __getitem__(self, calc_id: str) -> CalcDef:
        """Return the calc; raises `KeyError` for an unknown id."""
        return self._calcs[calc_id]

    def __iter__(self) -> Iterator[str]:
        """Iterate the registered ids."""
        return iter(self._calcs)

    def __len__(self) -> int:
        """Number of registered calcs."""
        return len(self._calcs)

    def content_hash(self, calc_id: str) -> str:
        """Return the content hash of a registered calc; raises `KeyError` for an unknown id."""
        return self._hashes[calc_id]
