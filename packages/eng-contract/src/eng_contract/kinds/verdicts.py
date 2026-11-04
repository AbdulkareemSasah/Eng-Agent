"""The `verdicts.set/1` kind (spec 4.10.2): verdicts with the traces they cite, self-contained.

Errors: `pydantic.ValidationError` for a full trace reference, a local one out of range, or counts that differ.
"""

from collections import Counter
from typing import Self

from pydantic import StrictBool, TypeAdapter, ValidationError, model_validator

from eng_contract.kinds._common import Payload
from eng_contract.refs import LocalTraceRef
from eng_contract.trace import Trace
from eng_contract.verdicts import Verdict, VerdictStatus

_LOCAL = TypeAdapter(LocalTraceRef)


class VerdictSet(Payload):
    """`verdicts.set/1`; `draft` marks the output of draft checks (10 section 4)."""

    verdicts: list[Verdict]
    traces: list[Trace]
    counts: dict[VerdictStatus, int]
    draft: StrictBool

    @model_validator(mode="after")
    def _check(self) -> Self:
        for verdict in self.verdicts:
            ref = verdict.trace_ref
            if ref is None:
                continue
            try:
                index = int(_LOCAL.validate_python(ref).rsplit("/", 1)[1])
            except ValidationError:
                raise ValueError(f"trace_ref {ref!r} must be a LocalTraceRef (#/traces/<n>)") from None
            if index >= len(self.traces):
                raise ValueError(f"trace_ref {ref!r} is out of range for {len(self.traces)} traces")
        tally = Counter(v.status for v in self.verdicts)
        if self.counts != {s: tally[s] for s in VerdictStatus}:
            raise ValueError("counts must match the verdicts, one entry per status")
        return self
