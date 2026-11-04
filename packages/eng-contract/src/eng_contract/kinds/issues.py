"""The `issues.model_check/1` kind (spec 4.10.2): a model check's summary and its issues.

Errors: `pydantic.ValidationError` when the summary counts differ from the issues.
"""

from collections import Counter
from typing import Self

from pydantic import model_validator

from eng_contract.issues import CheckModelSummary, ModelIssue, Severity
from eng_contract.kinds._common import Payload


class ModelCheck(Payload):
    """`issues.model_check/1`."""

    summary: CheckModelSummary
    issues: list[ModelIssue]

    @model_validator(mode="after")
    def _counts_match(self) -> Self:
        tally = Counter(i.severity for i in self.issues)
        s = self.summary
        if (s.errors, s.warnings, s.infos) != (tally[Severity.ERROR], tally[Severity.WARNING], tally[Severity.INFO]):
            raise ValueError("counts must match the issues")
        return self
