"""The result store (spec 4.5.3, 4.5.4; 04 section 3.1): immutable records under `.eng/results/<yyyy>/<mm>/<dd>/`.

Units: sizes in bytes. Errors: `ContractError` with `INVALID_ARGUMENT` (payload, kind or id), `REF_NOT_FOUND`;
`StoreWriteError` and `StoreIntegrityError` (`INTERNAL`).
"""

import gzip
import time
import zlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import JsonValue, TypeAdapter, ValidationError

from eng_contract._fs import FileSystem, RealFileSystem, StoreIntegrityError, checked_id, write_atomic
from eng_contract._validation import _field_path
from eng_contract.canonical import CanonicalJsonError, canonical_json, loads, payload_sha256
from eng_contract.envelope import Provenance
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import Clock, IdSource, ResultId, new_result_id, ulid_timestamp_ms
from eng_contract.kinds import KindRegistry
from eng_contract.records import PAYLOAD_SPLIT_BYTES, ResultRecord
from eng_contract.store._workspace import Workspace

_RESULT_ID = TypeAdapter(ResultId)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class ResultStore:
    """Writes and reads `ResultRecord`s; implements `RecordSource`. There is no delete and no update."""

    def __init__(
        self,
        workspace: Workspace,
        kinds: KindRegistry,
        ids: IdSource,
        clock: Clock,
        fs: FileSystem | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """`fs` defaults to the real disk, `sleep` (seconds) is injected so tests need no waiting."""
        self._ws, self._kinds, self._ids, self._clock, self._sleep = workspace, kinds, ids, clock, sleep
        self._fs = RealFileSystem() if fs is None else fs

    def _path(self, result_id: str) -> Path:
        checked_id(_RESULT_ID, result_id)
        try:
            day = _EPOCH + timedelta(milliseconds=ulid_timestamp_ms(result_id))
        except OverflowError:
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT, "result id time is out of range", received=result_id
            ) from None
        return self._ws.results_dir / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}" / f"{result_id}.json"

    def put(
        self,
        kind: str,
        payload: dict[str, JsonValue],
        producer: Provenance,
        parents: Sequence[str] = (),
        complete: bool = True,
    ) -> ResultRecord:
        """Validate, normalize (spec 4.4), hash and commit a new record; it is visible only once committed.

        Raises:
            ContractError: `INVALID_ARGUMENT` (unregistered kind, invalid payload,
            repeated parent), `REF_NOT_FOUND` (a parent).
            StoreWriteError: the files could not be committed.
        """
        try:
            body = self._kinds[kind].model_validate(payload).model_dump(mode="json", by_alias=True, exclude_none=False)
        except ValidationError as exc:
            first = exc.errors()[0]
            hint = f"{'.'.join(map(str, first['loc']))}: {first['msg']}"
            location = ""
            for part in first["loc"]:
                location += f"[{part}]" if isinstance(part, int) else (f".{part}" if location else str(part))
            raise ContractError(
                ErrorCode.INVALID_ARGUMENT,
                f"payload is not a valid {kind}",
                field=_field_path(location),
                expected={"kind": kind},
                hint=hint[:2000],
            ) from exc
        if len(set(parents)) != len(parents):
            raise ContractError(ErrorCode.INVALID_ARGUMENT, "parents must be unique", hint="remove the repeated id")
        for parent in parents:
            if not self.exists(parent):
                raise ContractError(ErrorCode.REF_NOT_FOUND, "parent result not found", received=parent)
        result_id = new_result_id(self._ids)
        data = canonical_json(body)
        split = len(data) > PAYLOAD_SPLIT_BYTES
        gz_name = f"{result_id}.payload.json.gz"
        record = ResultRecord(
            contract="eng-contract/1",
            result_id=result_id,
            kind=kind,
            created_at=self._clock.now(),
            units="canonical/1",
            complete=complete,
            producer=producer,
            parents=list(parents),
            payload_sha256=payload_sha256(body),
            payload=None if split else body,
            payload_file=gz_name if split else None,
        )
        path = self._path(result_id)
        self._fs.makedirs(path.parent)
        if split:  # the payload file first: the record's presence commits the result
            blob = gzip.compress(data, compresslevel=6, mtime=0)
            write_atomic(self._fs, path.with_name(gz_name), blob, self._ids, self._sleep)
        write_atomic(self._fs, path, canonical_json(record.model_dump(mode="json")), self._ids, self._sleep)
        return record

    def _read(self, result_id: str) -> tuple[ResultRecord, dict[str, JsonValue]]:
        path = self._path(result_id)
        if not self._fs.exists(path):
            raise ContractError(ErrorCode.REF_NOT_FOUND, f"no result {result_id}", received=result_id)
        try:
            record = ResultRecord.model_validate(loads(self._fs.read(path)))
            if record.result_id != result_id:
                raise ValueError("the record holds another result id")
            if record.payload_file is None:
                payload: JsonValue = record.payload
            else:
                payload = loads(gzip.decompress(self._fs.read(path.with_name(record.payload_file))))
            if not isinstance(payload, dict):
                raise ValueError("the payload is not an object")
            if payload_sha256(payload) != record.payload_sha256:
                raise ValueError("the payload hash differs from payload_sha256")
        except (CanonicalJsonError, OSError, ValueError, EOFError, zlib.error) as exc:
            raise StoreIntegrityError(
                f"stored result {result_id} is damaged: {exc}", self._ids, received=result_id
            ) from exc
        return record, payload

    def get(self, result_id: str) -> ResultRecord:
        """The verified record; `payload` is null when the payload is in its own file (see `payload`).

        Raises:
            ContractError: `INVALID_ARGUMENT` (malformed id), `REF_NOT_FOUND`.
            StoreIntegrityError: the bytes do not parse, validate or match `payload_sha256`.
        """
        return self._read(result_id)[0]

    def exists(self, result_id: str) -> bool:
        """Whether the record is committed. Raises `ContractError` `INVALID_ARGUMENT` for a malformed id."""
        return self._fs.exists(self._path(result_id))

    def payload(self, result_id: str) -> dict[str, JsonValue]:
        """The verified payload, loaded from its own file when split. Errors as for `get`."""
        return self._read(result_id)[1]
