"""ModelIssue and CheckModelSummary: findings of a model check (spec 4.9.2).

Purpose: report problems found in an analysis model with a stable producer-defined code.
Errors: `pydantic.ValidationError` for a malformed issue or an inconsistent summary.
"""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from eng_contract.verdicts import Subject


class Severity(StrEnum):
    """Issue severity."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ModelIssue(BaseModel):
    """One finding; `code` is defined by the producer and listed in its documentation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    severity: Severity
    code: Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")]
    subject: Subject
    message: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class CheckModelSummary(BaseModel):
    """Counts of a `check_model` run; `clean` must equal `errors == 0`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    errors: Annotated[int, Field(ge=0)]
    warnings: Annotated[int, Field(ge=0)]
    infos: Annotated[int, Field(ge=0)]
    clean: bool

    @model_validator(mode="after")
    def _clean_matches_errors(self) -> Self:
        if self.clean != (self.errors == 0):
            raise ValueError("clean must equal (errors == 0)")
        return self


__all__ = ["CheckModelSummary", "ModelIssue", "Severity"]
