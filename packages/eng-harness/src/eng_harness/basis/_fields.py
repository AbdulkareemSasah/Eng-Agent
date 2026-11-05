"""FieldSpec and the workflow declaration rules (spec 0004 section 4.5, AC21).

Purpose: a workflow declares the basis fields it uses; this module checks each declaration is coherent and that the
workflow's `required_basis` equals the paths of its required fields. No value, bound or default is held here: a bound
exists only when the declaration states it as a `Cited`.
Units: the unit of a quantity is the canonical unit of its path suffix (contract 4.7.2); a count has none.
Errors: `BasisInvalid` (contract code INVALID_ARGUMENT) with reason `field_invalid` or `declaration_mismatch`.
"""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Annotated, Literal, Self

from eng_contract.cited import Cited
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.units import kind_for_field
from pydantic import (
    BaseModel,
    ConfigDict,
    ModelWrapValidatorHandler,
    StringConstraints,
    ValidationError,
    model_validator,
)

BasisReason = Literal[
    "unknown_field",
    "field_invalid",
    "confirmed_not_allowed",
    "declaration_mismatch",
    "not_a_basis",
    "not_found",
    "hash_mismatch",
]

_SEGMENT = r"[A-Za-z_][A-Za-z0-9_]*"
_PATH = re.compile(rf"{_SEGMENT}(\.{_SEGMENT})+")  # contract field-path name rule (spec Q1), at least two segments


class BasisInvalid(ContractError):  # noqa: N818  # B-159: the name is fixed by spec 0004 section 6
    """Values or declarations break a rule of spec 0004; `reason` is the key, `path` the offending field."""

    def __init__(self, reason: BasisReason, path: str = "") -> None:
        """Build the error; the message holds only the reason key and the path."""
        self.reason: BasisReason = reason
        self.path = path
        super().__init__(ErrorCode.INVALID_ARGUMENT, f"basis invalid: {reason} at {path or '<root>'}")


def _bad(path: str) -> BasisInvalid:
    return BasisInvalid("field_invalid", path)


class FieldSpec(BaseModel):
    """One basis field a workflow uses: path, kind, label, whether it is required, unit, choices and cited bounds."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    path: Annotated[str, StringConstraints(strict=True)]
    kind: Literal["quantity", "count", "choice", "text"]
    label: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=120)]
    required: bool = True
    unit: str | None = None
    choices: tuple[str, ...] | None = None
    min: Cited | None = None
    max: Cited | None = None

    @model_validator(mode="wrap")
    @classmethod
    def _shape(cls, data: object, handler: ModelWrapValidatorHandler[Self]) -> Self:
        """Turn any structural failure (type, extra key, length) into `BasisInvalid` `field_invalid`."""
        try:
            return handler(data)
        except ValidationError as error:
            path = data.get("path", "") if isinstance(data, Mapping) else ""
            raise _bad(path if isinstance(path, str) else "") from error

    @model_validator(mode="after")
    def _rules(self) -> Self:
        path = self.path
        if not _PATH.fullmatch(path):
            raise _bad(path)
        if self.kind == "quantity":
            kind = kind_for_field(path.rpartition(".")[2])
            if kind is None or self.unit != kind.canonical_unit:
                raise _bad(path)
        elif self.unit is not None:
            raise _bad(path)
        if self.kind == "choice":
            choices = self.choices
            if choices is None or len(set(choices)) < 2 or len(set(choices)) != len(choices):
                raise _bad(path)
        elif self.choices is not None:
            raise _bad(path)
        limits = [limit for limit in (self.min, self.max) if limit is not None]
        if limits and self.kind not in ("quantity", "count"):
            raise _bad(path)
        if any(limit.unit != (self.unit or "1") for limit in limits):
            raise _bad(path)
        if self.min is not None and self.max is not None and self.min.value > self.max.value:
            raise _bad(path)
        return self


def check_declaration(fields: Iterable[FieldSpec], required_basis: Iterable[str]) -> None:
    """Check a workflow's declaration (AC21): paths are unique and `required_basis` equals the required paths.

    Raises:
        BasisInvalid: `field_invalid` for a repeated path; `declaration_mismatch` when the sets differ.
    """
    specs = tuple(fields)
    for path, count in Counter(spec.path for spec in specs).items():
        if count > 1:
            raise _bad(path)
    declared = {spec.path for spec in specs if spec.required}
    given = list(required_basis)
    if declared != set(given) or len(given) != len(declared):
        raise BasisInvalid("declaration_mismatch", ", ".join(sorted(declared.symmetric_difference(given))))
