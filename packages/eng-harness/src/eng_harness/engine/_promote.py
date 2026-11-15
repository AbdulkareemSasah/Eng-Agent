"""Promotion of a working copy by file copy over the internal `FileOps` port (spec 0001 4.7; AC52).

Purpose: `copy_files` backs the original's files up into the run folder and replaces them with the files of the accepted
revision, verifying every copy by hash; nothing is copied unless the original still has the hash its working copy was
taken from. The hash of several files is the SHA-256 of their bytes in the order of `HostPort.model_files`. Units: none.
Errors: `ContractError` `CONFLICT` (the original changed since the working copy was taken, a count of files that
differs, or a copy that does not match its source).
"""

import hashlib
import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from eng_contract.errors import ContractError, ErrorCode


class FileOps(Protocol):
    """The file operations of a promotion (`sha256` of the bytes of paths in order; `copy` creates the target folder;
    `replace` moves over the target); a fake stands in for the file system in tests."""

    def sha256(self, paths: Sequence[Path]) -> str: ...

    def copy(self, source: Path, target: Path) -> None: ...

    def replace(self, source: Path, target: Path) -> None: ...


class LocalFileOps:
    """`FileOps` over the local file system."""

    def sha256(self, paths: Sequence[Path]) -> str:
        """Hex SHA-256 of the bytes of `paths`, in order."""
        return hashlib.sha256(b"".join(path.read_bytes() for path in paths)).hexdigest()

    def copy(self, source: Path, target: Path) -> None:
        """Copy `source` to `target`, creating its folder."""
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def replace(self, source: Path, target: Path) -> None:
        """Move `source` over `target`."""
        os.replace(source, target)


def _verified(files: FileOps, source: Path, target: Path) -> None:
    files.copy(source, target)
    if files.sha256([source]) != files.sha256([target]):
        raise ContractError(ErrorCode.CONFLICT, f"the copy {target.name} does not match {source.name}")


def copy_files(
    files: FileOps, originals: Sequence[Path], accepted: Sequence[Path], backups: Path, origin_sha256: str
) -> None:
    """Replace `originals` by `accepted` (the same count, in order) after a backup of them in `backups`.

    Raises:
        ContractError: `CONFLICT`; nothing is copied when the originals no longer have `origin_sha256`, or the counts
            differ, and the originals are left as they were when a copy does not match its source.
    """
    if files.sha256(originals) != origin_sha256:
        raise ContractError(ErrorCode.CONFLICT, "the original changed since the working copy was taken")
    if len(accepted) != len(originals):
        raise ContractError(ErrorCode.CONFLICT, "the working copy has another count of files than the original")
    for original in originals:
        _verified(files, original, backups / original.name)
    staged = [target.with_name(target.name + ".promoting") for target in originals]
    for source, temporary in zip(accepted, staged, strict=True):
        _verified(files, source, temporary)
    for temporary, target in zip(staged, originals, strict=True):
        files.replace(temporary, target)
