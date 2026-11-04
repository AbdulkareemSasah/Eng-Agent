"""Result records (spec 4.4; 04 section 2).

Purpose: the stored form of one result. Units: payload sizes in bytes. Errors: `pydantic.ValidationError`.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from eng_contract._types import KindName, Sha256Hex
from eng_contract.envelope import Provenance
from eng_contract.ids import ResultId, Timestamp

PAYLOAD_SPLIT_BYTES = 8 * 1024 * 1024
"""Canonical payload size above which the store writes the payload to its own file (spec 4.5.4; 8 MiB)."""


class ResultRecord(BaseModel):
    """One stored result (spec 4.4): exactly one of `payload` and `payload_file` is set."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, strict=False)

    contract: Literal["eng-contract/1"]
    result_id: ResultId
    kind: KindName
    created_at: Timestamp
    units: Literal["canonical/1"]
    complete: bool
    producer: Provenance
    parents: list[ResultId]
    payload_sha256: Sha256Hex
    payload: dict[str, JsonValue] | None = None
    payload_file: str | None = None

    @model_validator(mode="after")
    def _check_rules(self) -> Self:
        if (self.payload is None) is (self.payload_file is None):
            raise ValueError("exactly one of payload and payload_file must be set")
        if self.payload_file is not None and self.payload_file != f"{self.result_id}.payload.json.gz":
            raise ValueError("payload_file must be '<result_id>.payload.json.gz'")
        if len(set(self.parents)) != len(self.parents):
            raise ValueError("parents must be unique")
        return self
