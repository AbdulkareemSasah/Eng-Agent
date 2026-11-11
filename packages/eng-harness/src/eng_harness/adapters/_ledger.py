"""The write ledger `run_dir/adapter/ops.jsonl` (plan 0002 T8b; spec 0002 4.5.7). Units: none. Errors: `OSError` when an
entry cannot be made durable; the caller then sends nothing."""

import os
from pathlib import Path

from eng_contract.ids import Timestamp
from pydantic import BaseModel, ConfigDict, Field

from eng_harness.adapters._args import HostTarget

__all__ = ["LedgerEntry", "WriteLedger"]


class LedgerEntry(BaseModel):
    """One write about to be sent; `pre_image_ref` points to the last model-state read of the object, if any."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    op_id: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    args_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target: HostTarget
    pre_image_ref: str | None
    sent_at: Timestamp


class WriteLedger:
    """Append-only JSON lines, each `fsync`ed before `append` returns (and the folder, for a new file)."""

    def __init__(self, run_dir: Path) -> None:
        """The ledger of the run in `run_dir`; nothing is created until the first write."""
        self.path = run_dir / "adapter" / "ops.jsonl"

    def append(self, entry: LedgerEntry) -> None:
        """Append `entry` durably; raises `OSError` when the folder or file cannot be created, written or synced."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        created = not self.path.exists()
        with self.path.open("ab") as handle:
            handle.write(entry.model_dump_json().encode("utf-8") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        if created and os.name == "posix":  # a new directory entry is durable only after its folder is synced
            folder = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(folder)
            finally:
                os.close(folder)
