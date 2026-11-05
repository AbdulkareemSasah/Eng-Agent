"""Types of the ctx API: results, approvals, previews and the basis view (spec 0001 4.3.2, 4.9).

Purpose: the values block code receives from and passes to `ctx`; the `Ctx` protocol itself follows with the calls.
Units: quantities are `Quantity` objects; the basis view returns values in the unit the basis field declares.
Errors: `BlockRuleViolation` when block code asks the basis view for a path the workflow did not declare or for
a value of the wrong shape.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from eng_contract.errors import ContractWarning
from eng_contract.ids import ModelId, ResultId
from eng_contract.kinds.basis import DesignBasis
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref, parse_ref
from pydantic import BaseModel, ConfigDict, Field, InstanceOf, model_validator

from eng_harness.calc import CalcStatus
from eng_harness.errors import BlockRuleViolation

__all__ = [
    "Answered",
    "Approval",
    "ApprovalKind",
    "ArgValue",
    "Attempt",
    "BasisCount",
    "BasisView",
    "CalcResult",
    "Decision",
    "DecisionRequest",
    "ModelHandle",
    "Preview",
    "PreviewItem",
    "Promotion",
    "ReadResult",
    "SummaryValue",
    "ToolResult",
]

type SummaryValue = (
    str | bool | int | float | InstanceOf[Quantity] | Sequence[SummaryValue] | Mapping[str, SummaryValue] | None
)
"""A JSON value in which every quantity object of contract 4.8 is a `Quantity` or `LabeledQuantity`."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ApprovalKind(StrEnum):
    """What an approval authorizes (spec 4.9)."""

    CHANGE_SET = "change_set"
    PROMOTION = "promotion"
    SIGN_OFF = "sign_off"
    INFO = "info"


class Promotion(StrEnum):
    """How a working copy becomes the model of record (spec 4.7); `REPLAY_WRITES` is a gap (E-G1)."""

    FILE_COPY = "file_copy"
    REPLAY_WRITES = "replay_writes"


class ModelHandle(_Frozen):
    """A model a result or a preview refers to: its key, contract id and revision."""

    model_key: str
    model_id: ModelId
    revision: int = Field(ge=0)


class ToolResult(_Frozen):
    """A tool's success envelope as the block sees it; `ref` is the stored result."""

    tool: str
    ref: Ref
    summary: Mapping[str, SummaryValue]
    warnings: tuple[ContractWarning, ...]
    complete: bool
    model: ModelHandle | None


class ReadResult(_Frozen):
    """A value read from a stored result at a pointer."""

    ref: Ref
    kind: str
    value: SummaryValue


class CalcResult(_Frozen):
    """A calc's stored result; `draft` is true for a `draft` or `verified` calc."""

    calc_id: str
    calc_version: int
    status: CalcStatus
    ref: Ref
    summary: Mapping[str, SummaryValue]
    draft: bool


class Decision[T](_Frozen):
    """The outcome of `ctx.decide`: the choice, who decided and the confidence (`None` for rules and engineers)."""

    choice: T
    decided_by: str
    confidence: float | None = None


class Answered[M: BaseModel](_Frozen):
    """The engineer's validated answer to `ctx.ask`; `ref` is the stored `basis.engineer_input/1` result."""

    value: M
    ref: Ref

    def field_ref(self, name: str) -> Ref:
        """Reference to one answered field, `res_<id>#/fields/<name>/value`."""
        return Ref.model_validate({"$ref": f"{parse_ref(self.ref.ref)[0]}#/fields/{name}/value"})


class Attempt(_Frozen):
    """One iteration of `ctx.attempts`."""

    index: int = Field(ge=0)
    is_last: bool


class PreviewItem(_Frozen):
    """One accept-or-reject unit of an approval."""

    id: str
    label: str
    refs: tuple[Ref, ...]


class Preview(_Frozen):
    """What an approval shows (stored as `harness.approval_preview/1`); item ids are unique."""

    items: tuple[PreviewItem, ...]
    diff_ref: Ref | None
    models: tuple[ModelHandle, ...]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [item.id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("preview item ids must be unique")
        return self


class Approval(_Frozen):
    """The engineer's answer to `ctx.approve`; a rejected approval is returned, not raised."""

    request_id: str
    approved: bool
    rejected_items: tuple[str, ...]
    item_reasons: Mapping[str, str]
    reason: str | None

    def accepts(self, item_id: str) -> bool:
        """True when the approval is approved and `item_id` is not among the rejected items."""
        return self.approved and item_id not in self.rejected_items


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    """One item of `ctx.decide_many`: the arguments of `decide` (checked by the engine and the cascade)."""

    question: str
    options: object
    state: BaseModel
    rules: Sequence[object]
    policy: object


type ArgValue = (
    str
    | bool
    | int
    | float
    | Ref
    | ToolResult
    | CalcResult
    | ReadResult
    | StrEnum
    | Sequence[ArgValue]
    | Mapping[str, ArgValue]
    | None
)


class BasisCount(int):
    """A non-negative `int` read from the design basis, the only limit `ctx.attempts` accepts (gate FB005)."""

    __slots__ = ()

    def __new__(cls, value: int) -> Self:
        """Raises:
        ValueError: `value` is negative.
        """
        if value < 0:
            raise ValueError("a basis count must be non-negative")
        return super().__new__(cls, value)


class BasisView:
    """The frozen design basis as block code sees it; only paths declared in `required_basis` are readable."""

    def __init__(self, result_id: ResultId, basis: DesignBasis, declared: Iterable[str]) -> None:
        """Bind the stored basis result `result_id`, its content and the declared paths."""
        self._id = result_id
        self._basis = basis
        self._declared = frozenset(declared)

    def _field(self, path: str) -> tuple[object, str | None]:
        if path not in self._declared or path not in self._basis.fields:
            raise BlockRuleViolation(f"basis path {path!r} is not declared in required_basis")
        field = self._basis.fields[path]
        return field.value, field.unit

    def ref(self, path: str) -> Ref:
        """Reference `res_<id>#/fields/<path>/value` (contract 4.10.2)."""
        self._field(path)
        return Ref.model_validate({"$ref": f"{self._id}#/fields/{path}/value"})

    def quantity(self, path: str) -> Quantity:
        """The field as a `Quantity` in its declared unit."""
        value, unit = self._field(path)
        if unit is None or isinstance(value, bool) or not isinstance(value, int | float):
            raise BlockRuleViolation(f"basis path {path!r} is not a number with a unit")
        return Quantity(float(value), unit)

    def count(self, path: str) -> BasisCount:
        """The field as a `BasisCount` (an integer of at least zero)."""
        value, _ = self._field(path)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BlockRuleViolation(f"basis path {path!r} is not a non-negative integer")
        return BasisCount(value)

    def choice[E: StrEnum](self, path: str, enum: type[E]) -> E:
        """The field as a member of `enum`."""
        value, _ = self._field(path)
        if not isinstance(value, str):
            raise BlockRuleViolation(f"basis path {path!r} is not a value of {enum.__name__}")
        try:
            return enum(value)
        except ValueError as exc:
            raise BlockRuleViolation(f"basis path {path!r} is not a value of {enum.__name__}") from exc
