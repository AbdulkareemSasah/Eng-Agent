"""File-system port, its fake and the atomic write protocol (spec 4.5.4); the only module that touches the disk.

Units: seconds for retry delays. Errors: `StoreWriteError` and `StoreIntegrityError` (both `INTERNAL`);
`ContractError` `INVALID_ARGUMENT` for a malformed identifier that would otherwise become part of a path.
"""

import logging
import os
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import IdSource

_LOG = logging.getLogger(__name__)
RETRY_DELAYS_S = (0.05, 0.1, 0.2)
"""Delays before the second, third and fourth commit attempt (spec 4.5.4 step 5; a software decision)."""


class _InternalStoreError(ContractError):
    def __init__(self, message: str, ids: IdSource) -> None:
        super().__init__(ErrorCode.INTERNAL, message[:2000], incident_id=ids.new_ulid())


class StoreWriteError(_InternalStoreError):
    """A file could not be written or committed (`INTERNAL`); the cause is chained."""


class StoreIntegrityError(_InternalStoreError):
    """Stored bytes are unreadable, corrupt or inconsistent (`INTERNAL`, never `INVALID_ARGUMENT`)."""


def checked_id(adapter: TypeAdapter[str], value: str) -> str:
    """Return `value` when it is a well-formed identifier of `adapter`'s kind.

    Raises:
        ContractError: `INVALID_ARGUMENT`; no path is ever built from an unchecked identifier.
    """
    try:
        return adapter.validate_python(value)
    except ValidationError:
        raise ContractError(ErrorCode.INVALID_ARGUMENT, "malformed identifier", received=value[:200]) from None


class FileSystem(Protocol):
    """The disk operations of the stores."""

    def makedirs(self, path: Path) -> None:
        """Create `path` and its parents; an existing folder is fine."""

    def write_new(self, path: Path, data: bytes) -> None:
        """Create `path` exclusively, write `data`, flush and fsync. Raises `FileExistsError` if it exists."""

    def commit(self, tmp: Path, final: Path) -> None:
        """Move `tmp` to `final` only if `final` is absent (`FileExistsError`); `PermissionError` may be retried."""

    def replace(self, tmp: Path, final: Path) -> None:
        """Move `tmp` over `final` (mutable state files only)."""

    def read(self, path: Path) -> bytes:
        """Return the bytes of `path`. Raises `FileNotFoundError` if it is missing."""

    def exists(self, path: Path) -> bool:
        """Whether the file `path` exists."""

    def remove(self, path: Path) -> None:
        """Delete `path`; a missing file is not an error."""


class RealFileSystem:
    """The operating system: exclusive create, fsync, and link (POSIX) or rename (Windows) as the exclusive commit."""

    def __init__(self, *, link_commit: bool = os.name != "nt") -> None:
        """`link_commit` selects `os.link` plus `os.unlink` (default off Windows) over `os.rename`."""
        self._link = link_commit

    def makedirs(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def write_new(self, path: Path, data: bytes) -> None:
        """Write `data` to a new file with `O_CREAT | O_EXCL`, then fsync it."""
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    def commit(self, tmp: Path, final: Path) -> None:
        """Exclusive move; with `link_commit` the folder is fsynced afterwards. `os.replace` is never used here."""
        if not self._link:
            os.rename(tmp, final)
            return
        os.link(tmp, final)
        os.unlink(tmp)
        fd = os.open(final.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def replace(self, tmp: Path, final: Path) -> None:
        os.replace(tmp, final)

    def read(self, path: Path) -> bytes:
        return path.read_bytes()

    def exists(self, path: Path) -> bool:
        return path.is_file()

    def remove(self, path: Path) -> None:
        path.unlink(missing_ok=True)


class FakeFileSystem:
    """In-memory port for tests: `commit_errors` and `read_errors` are raised one per call, `partial_write` is a byte
    count after which `write_new` fails and leaves the partial file."""

    def __init__(self) -> None:
        self.files: dict[Path, bytes] = {}
        self.commit_errors: list[OSError] = []
        self.read_errors: list[OSError] = []
        self.partial_write: int | None = None

    def makedirs(self, path: Path) -> None:
        """Folders are implicit."""

    def write_new(self, path: Path, data: bytes) -> None:
        """Store `data`, or a prefix of it followed by `OSError` when `partial_write` is set."""
        if path in self.files:
            raise FileExistsError(str(path))
        if self.partial_write is not None:
            self.files[path] = data[: self.partial_write]
            raise OSError("disk full")
        self.files[path] = data

    def commit(self, tmp: Path, final: Path) -> None:
        """Raise the next injected error, else move `tmp` unless `final` exists."""
        if self.commit_errors:
            raise self.commit_errors.pop(0)
        if final in self.files:
            raise FileExistsError(str(final))
        self.files[final] = self.files.pop(tmp)

    def replace(self, tmp: Path, final: Path) -> None:
        if self.commit_errors:
            raise self.commit_errors.pop(0)
        self.files[final] = self.files.pop(tmp)

    def read(self, path: Path) -> bytes:
        """Raise the next injected error, else return the bytes or raise `FileNotFoundError`."""
        if self.read_errors:
            raise self.read_errors.pop(0)
        try:
            return self.files[path]
        except KeyError:
            raise FileNotFoundError(str(path)) from None

    def exists(self, path: Path) -> bool:
        return path in self.files

    def remove(self, path: Path) -> None:
        self.files.pop(path, None)


def write_atomic(
    fs: FileSystem, final: Path, data: bytes, ids: IdSource, sleep: Callable[[float], None], *, replace: bool = False
) -> None:
    """Write `data` to `final` through a temporary file in the same folder (spec 4.5.4 steps 2 to 6).

    `PermissionError` on commit is retried after each of `RETRY_DELAYS_S` (four attempts in all); `FileExistsError`
    is not. With `replace` the commit overwrites (state files); otherwise it fails if `final` exists.

    Raises:
        StoreWriteError: any `OSError`, after the temporary file was removed (best effort, logged).
    """
    tmp = final.with_name(f"{final.name}.{secrets.token_hex(8)}.tmp")
    commit = fs.replace if replace else fs.commit
    try:
        fs.write_new(tmp, data)
        for delay in (*RETRY_DELAYS_S, None):
            try:
                commit(tmp, final)
                return
            except PermissionError:
                if delay is None:
                    raise
                sleep(delay)
    except OSError as exc:
        try:
            fs.remove(tmp)
        except OSError:
            _LOG.warning("temporary file not removed", extra={"file": tmp.name}, exc_info=True)
        raise StoreWriteError(f"cannot write {final.name}: {exc}", ids) from exc
