"""Result store: atomic writes, payload split, integrity (plan T14; spec 4.4, 4.5.3, 4.5.4; AC16 to AC21a).

Expected paths, delays and limits come from the spec text, not from the implementation.
"""

import copy
import gzip
import json
import logging
import os
import stat
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from eng_contract._fs import FakeFileSystem, FileSystem, RealFileSystem, write_atomic
from eng_contract.canonical import canonical_json, payload_sha256
from eng_contract.envelope import Provenance
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource, new_result_id
from eng_contract.kinds import NEUTRAL_KINDS
from eng_contract.refs import RefRule, rebase_local_ref, resolve_ref
from eng_contract.store import LocationClass, ResultStore, StoreIntegrityError, StoreWriteError, Workspace

START_MS = 1_767_323_045_678  # 2026-01-02T03:04:05.678Z
DAY = ("2026", "01", "02")
SPLIT = 8_388_608  # spec 4.5.4: 8 MiB


class Note(BaseModel):
    """Test kind with a defaulted field."""

    model_config = ConfigDict(extra="forbid")

    text: str
    level: int = 1


class Rich(BaseModel):
    """Test kind whose dump differs between Python and JSON mode, by alias, and with a null."""

    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    when: datetime
    odd_name: int = Field(alias="odd-name")
    maybe: str | None = None
    items: list[int] = []


class Huge(BaseModel):
    """Test kind whose validation message is longer than an error field may be."""

    model_config = ConfigDict(extra="forbid")

    v: int

    @field_validator("v")
    @classmethod
    def _always_fails(cls, value: int) -> int:
        raise ValueError("x" * 3000)


KINDS = NEUTRAL_KINDS.extend({"test.note/1": Note, "test.rich/1": Rich, "test.huge/1": Huge})
PRODUCER = Provenance.model_validate(
    {
        "tool": "harness",
        "tool_version": "1",
        "inputs": {},
        "started_at": "2026-01-02T03:04:05.678Z",
        "duration_ms": 0,
    }
)


def _ids(seed: bytes = b"seed") -> SeededIdSource:
    return SeededIdSource(seed, FixedClock(START_MS))


def _store(
    root: Path,
    fs: FileSystem | None = None,
    sleep: Callable[[float], None] = lambda _s: None,
    seed: bytes = b"seed",
) -> ResultStore:
    ws = Workspace(root=root, classification=LocationClass.LOCAL)
    return ResultStore(ws, KINDS, _ids(seed), FixedClock(START_MS), fs, sleep)


def _final(root: Path, result_id: str) -> Path:
    return root / ".eng" / "results" / DAY[0] / DAY[1] / DAY[2] / f"{result_id}.json"


def _next_id(seed: bytes = b"seed") -> str:
    return new_result_id(_ids(seed))


def _verdict_set(**verdict_over: Any) -> dict[str, Any]:
    fixture = Path(__file__).parents[1] / "data" / "kinds" / "verdicts.set-1" / "valid.json"
    payload: dict[str, Any] = json.loads(fixture.read_text(encoding="utf-8"))
    payload["verdicts"][0].update(verdict_over)
    return payload


def test_put_get_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = store.put("test.note/1", {"text": "hello"}, PRODUCER)
    path = _final(tmp_path, record.result_id)
    assert path.read_bytes() == canonical_json(record.model_dump(mode="json"))
    assert [p for p in tmp_path.rglob("*") if p.is_file()] == [path]  # no temporary file remains
    assert record.created_at == "2026-01-02T03:04:05.678Z"
    assert record.payload == {"text": "hello", "level": 1}
    assert record.payload_sha256 == payload_sha256({"text": "hello", "level": 1})
    assert store.get(record.result_id) == record
    assert store.exists(record.result_id)
    assert store.payload(record.result_id) == {"text": "hello", "level": 1}


def test_get_of_a_missing_or_malformed_id(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert not store.exists(_next_id())
    with pytest.raises(ContractError) as missing:
        store.get(_next_id())
    assert missing.value.detail.code is ErrorCode.REF_NOT_FOUND
    year_11000 = "res_7" + "Z" * 25  # well formed, but its time is beyond year 9999
    for bad in ("../../etc/passwd", "res_short", "mdl_" + _next_id()[4:], "", year_11000):
        with pytest.raises(ContractError) as info:
            store.get(bad)
        assert info.value.detail.code is ErrorCode.INVALID_ARGUMENT
        with pytest.raises(ContractError):
            store.exists(bad)


def test_parents_must_exist(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.put("test.note/1", {"text": "a"}, PRODUCER)
    child = store.put("test.note/1", {"text": "b"}, PRODUCER, parents=[first.result_id], complete=False)
    assert child.parents == [first.result_id]
    assert not child.complete
    with pytest.raises(ContractError) as info:
        store.put("test.note/1", {"text": "c"}, PRODUCER, parents=[_next_id(b"other")])
    assert info.value.detail.code is ErrorCode.REF_NOT_FOUND


def test_duplicate_parents_are_invalid_argument_and_write_nothing(tmp_path: Path) -> None:
    fs = FakeFileSystem()
    store = _store(tmp_path, fs)
    first = store.put("test.note/1", {"text": "a"}, PRODUCER)
    before = dict(fs.files)
    with pytest.raises(ContractError) as info:
        store.put("test.note/1", {"text": "b"}, PRODUCER, parents=[first.result_id, first.result_id])
    assert info.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert "unique" in info.value.detail.message
    assert fs.files == before


@pytest.mark.parametrize("failures", [0, 1, 2, 3])
def test_rename_retries_with_backoff(tmp_path: Path, failures: int) -> None:
    fs = FakeFileSystem()
    fs.commit_errors = [PermissionError("sharing violation")] * failures
    delays: list[float] = []
    record = _store(tmp_path, fs, delays.append).put("test.note/1", {"text": "x"}, PRODUCER)
    assert delays == [0.05, 0.1, 0.2][:failures]  # spec 4.5.4 step 5
    assert list(fs.files) == [_final(tmp_path, record.result_id)]


def test_rename_gives_up(tmp_path: Path) -> None:
    fs = FakeFileSystem()
    fs.commit_errors = [PermissionError("sharing violation")] * 4
    delays: list[float] = []
    with pytest.raises(StoreWriteError) as info:
        _store(tmp_path, fs, delays.append).put("test.note/1", {"text": "x"}, PRODUCER)
    assert delays == [0.05, 0.1, 0.2]
    assert info.value.detail.code is ErrorCode.INTERNAL
    assert info.value.detail.incident_id
    assert info.value.detail.hint is not None
    assert isinstance(info.value.__cause__, PermissionError)
    assert fs.files == {}  # no record and no temporary file


def test_failed_write_removes_the_temporary_file(tmp_path: Path) -> None:
    fs = FakeFileSystem()
    fs.partial_write = 5
    with pytest.raises(StoreWriteError):
        _store(tmp_path, fs).put("test.note/1", {"text": "x"}, PRODUCER)
    assert fs.files == {}


@pytest.mark.parametrize("real", [False, True])
def test_exclusive_create(tmp_path: Path, real: bool) -> None:
    fs: FileSystem = RealFileSystem() if real else FakeFileSystem()
    existing = _final(tmp_path, _next_id())
    fs.makedirs(existing.parent)
    tmp = existing.with_name("seed.tmp")
    fs.write_new(tmp, b"old")
    fs.commit(tmp, existing)
    delays: list[float] = []
    with pytest.raises(StoreWriteError) as info:
        _store(tmp_path, fs, delays.append).put("test.note/1", {"text": "x"}, PRODUCER)
    assert info.value.detail.code is ErrorCode.INTERNAL
    assert isinstance(info.value.__cause__, FileExistsError)
    assert info.value.detail.hint is not None  # spec 6: StoreWriteError carries incident_id and hint
    assert delays == []  # a collision is not retried
    assert fs.read(existing) == b"old"
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == ([existing.name] if real else [])


def test_large_payload_split(tmp_path: Path) -> None:
    text = "x" * SPLIT  # the canonical payload is longer than SPLIT because of its keys and quotes
    store = _store(tmp_path)
    record = store.put("test.note/1", {"text": text}, PRODUCER)
    gz = _final(tmp_path, record.result_id).with_name(f"{record.result_id}.payload.json.gz")
    assert record.payload is None
    assert record.payload_file == gz.name
    expected = {"text": text, "level": 1}
    assert gzip.decompress(gz.read_bytes()) == canonical_json(expected)
    assert record.payload_sha256 == payload_sha256(expected)
    assert store.payload(record.result_id) == expected
    assert store.get(record.result_id) == record


def test_payload_at_the_split_limit_stays_inline(tmp_path: Path) -> None:
    overhead = len(canonical_json({"text": "", "level": 1}))
    record = _store(tmp_path).put("test.note/1", {"text": "x" * (SPLIT - overhead)}, PRODUCER)
    assert record.payload is not None
    assert record.payload_file is None


def test_gzip_bytes_are_reproducible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("eng_contract.store._results.PAYLOAD_SPLIT_BYTES", 10)
    blobs = []
    for sub in ("a", "b"):
        record = _store(tmp_path / sub).put("test.note/1", {"text": "x" * 100}, PRODUCER)
        blobs.append(_final(tmp_path / sub, record.result_id).with_name(f"{record.result_id}.payload.json.gz"))
    assert blobs[0].read_bytes() == blobs[1].read_bytes()
    assert blobs[0].read_bytes()[4:8] == b"\x00\x00\x00\x00"  # gzip header mtime is 0


def _integrity(store: ResultStore, result_id: str) -> StoreIntegrityError:
    with pytest.raises(StoreIntegrityError) as info:
        store.get(result_id)
    assert info.value.detail.code is ErrorCode.INTERNAL
    assert info.value.detail.incident_id
    assert info.value.detail.received == result_id  # spec 6
    return info.value


def test_hash_verified_on_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    record = store.put("test.note/1", {"text": "x"}, PRODUCER)
    path = _final(tmp_path, record.result_id)
    altered = json.loads(path.read_bytes())
    altered["payload"]["text"] = "y"
    path.write_bytes(canonical_json(altered))
    assert "hash" in _integrity(store, record.result_id).detail.message

    monkeypatch.setattr("eng_contract.store._results.PAYLOAD_SPLIT_BYTES", 10)
    split = store.put("test.note/1", {"text": "x" * 100}, PRODUCER)
    gz = _final(tmp_path, split.result_id).with_name(f"{split.result_id}.payload.json.gz")
    gz.write_bytes(gzip.compress(canonical_json({"text": "z" * 100, "level": 1})))  # valid gzip, other payload
    assert "hash" in _integrity(store, split.result_id).detail.message
    with pytest.raises(StoreIntegrityError):
        store.payload(split.result_id)
    gz.write_bytes(gz.read_bytes()[:20])  # truncated gzip
    _integrity(store, split.result_id)
    gz.write_bytes(gzip.compress(b"[1]"))  # a payload must be an object
    _integrity(store, split.result_id)
    gz.unlink()  # the payload file is gone
    _integrity(store, split.result_id)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b'"complete":true', b'"complete":true,"complete":false'),  # duplicate key
        (b'"duration_ms":0', b'"duration_ms":NaN'),  # NaN literal
        (b'"units":"canonical/1"', b'"units":"other"'),  # does not validate as a ResultRecord
        (b'{"complete"', b'{"surplus":1,"complete"'),  # extra field
        (b'"contract"', b'"cont\xffract"'),  # not UTF-8
    ],
)
def test_corrupt_record_is_integrity_error(tmp_path: Path, old: bytes, new: bytes) -> None:
    store = _store(tmp_path)
    record = store.put("test.note/1", {"text": "x"}, PRODUCER)
    path = _final(tmp_path, record.result_id)
    raw = path.read_bytes()
    assert old in raw
    path.write_bytes(raw.replace(old, new))
    _integrity(store, record.result_id)
    with pytest.raises(StoreIntegrityError):
        store.payload(record.result_id)


def test_record_of_another_result_is_integrity_error(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.put("test.note/1", {"text": "a"}, PRODUCER)
    second = store.put("test.note/1", {"text": "b"}, PRODUCER)
    _final(tmp_path, second.result_id).write_bytes(_final(tmp_path, first.result_id).read_bytes())
    _integrity(store, second.result_id)


def test_unreadable_record_is_integrity_error(tmp_path: Path) -> None:
    fs = FakeFileSystem()
    store = _store(tmp_path, fs)
    record = store.put("test.note/1", {"text": "x"}, PRODUCER)
    fs.read_errors = [PermissionError("denied")]
    assert isinstance(_integrity(store, record.result_id).__cause__, PermissionError)


def test_payload_validated_against_kind(tmp_path: Path) -> None:
    fs = FakeFileSystem()
    store = _store(tmp_path, fs)
    cases: list[tuple[str, dict[str, JsonValue]]] = [
        ("test.note/1", {"text": 5}),  # wrong type
        ("test.note/1", {"text": "a", "surplus": 1}),  # extra field
        ("verdicts.set/1", {}),  # required fields missing
        ("test.unknown/1", {"text": "a"}),  # not registered
        ("test.note", {"text": "a"}),  # not a kind name
    ]
    for kind, payload in cases:
        with pytest.raises(ContractError) as info:
            store.put(kind, payload, PRODUCER)
        assert info.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert fs.files == {}  # nothing is written


def test_payload_stored_normalized(tmp_path: Path) -> None:
    store = _store(tmp_path)
    plain = _verdict_set()
    del plain["verdicts"][1]["ratio_limit"]  # a defaulted field, omitted
    explicit = copy.deepcopy(plain)
    explicit["verdicts"][1]["ratio_limit"] = 1.0
    first = store.put("verdicts.set/1", plain, PRODUCER)
    second = store.put("verdicts.set/1", explicit, PRODUCER)
    stored_first: Any = first.payload
    assert stored_first["verdicts"][1]["ratio_limit"] == 1.0
    assert first.payload == second.payload
    assert first.payload_sha256 == second.payload_sha256
    assert store.payload(first.result_id) == first.payload
    # a lax-coerced value is replaced by its validated value
    assert store.put("test.note/1", {"text": "a", "level": "3"}, PRODUCER).payload == {"text": "a", "level": 3}


def test_verdict_trace_ref_end_to_end(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = store.put("verdicts.set/1", _verdict_set(), PRODUCER)
    stored: Any = record.payload
    assert stored["verdicts"][0]["trace_ref"] == "#/traces/0"
    ref = rebase_local_ref(record.result_id, stored["verdicts"][0]["trace_ref"])
    resolved = resolve_ref(ref, RefRule(), store, lambda _model_id: None)
    assert resolved.value == stored["traces"][0]
    assert resolved.ref == f"{record.result_id}#/traces/0"
    # the hash of the payload does not depend on the result id
    other = _store(tmp_path / "other", seed=b"other").put("verdicts.set/1", _verdict_set(), PRODUCER)
    assert other.result_id != record.result_id
    assert other.payload_sha256 == record.payload_sha256


def test_split_payload_resolves_through_the_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("eng_contract.store._results.PAYLOAD_SPLIT_BYTES", 10)
    store = _store(tmp_path)
    record = store.put("test.note/1", {"text": "a" * 50}, PRODUCER)
    value: JsonValue = resolve_ref(f"{record.result_id}#/text", RefRule(), store, lambda _m: None).value
    assert value == "a" * 50


def test_real_filesystem_commit_by_rename(tmp_path: Path) -> None:
    fs = RealFileSystem(link_commit=False)
    fs.makedirs(tmp_path / "d")
    fs.write_new(tmp_path / "d" / "a.tmp", b"data")
    fs.commit(tmp_path / "d" / "a.tmp", tmp_path / "d" / "a")
    assert fs.read(tmp_path / "d" / "a") == b"data"
    assert not fs.exists(tmp_path / "d" / "a.tmp")
    fs.write_new(tmp_path / "d" / "b.tmp", b"new")
    fs.replace(tmp_path / "d" / "b.tmp", tmp_path / "d" / "a")
    assert fs.read(tmp_path / "d" / "a") == b"new"
    fs.remove(tmp_path / "d" / "a")
    fs.remove(tmp_path / "d" / "a")  # removing a missing file is not an error
    assert not fs.exists(tmp_path / "d" / "a")


@pytest.mark.parametrize("failing", ["unlink", "fsync"])
def test_failure_after_the_link_still_counts_as_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, failing: str
) -> None:
    real_fsync = os.fsync

    def boom(*_args: object) -> None:
        raise PermissionError("after the commit")

    def folder_fsync_fails(fd: int) -> None:  # the file's own fsync, before the commit, must still work
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            boom()
        real_fsync(fd)

    monkeypatch.setattr(os, failing, boom if failing == "unlink" else folder_fsync_fails)
    fs = RealFileSystem(link_commit=True)
    with caplog.at_level(logging.WARNING):
        write_atomic(fs, tmp_path / "a.json", b"data", _ids(), lambda _s: None)  # no StoreWriteError
    assert (tmp_path / "a.json").read_bytes() == b"data"
    assert [r.levelno for r in caplog.records] == [logging.WARNING]
    assert "committed" in caplog.records[0].getMessage()


def test_real_filesystem_write_is_exclusive(tmp_path: Path) -> None:
    fs = RealFileSystem()
    fs.write_new(tmp_path / "a.tmp", b"1")
    with pytest.raises(FileExistsError):
        fs.write_new(tmp_path / "a.tmp", b"2")
    assert fs.read(tmp_path / "a.tmp") == b"1"


def test_unremovable_temporary_file_is_logged_not_hidden(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    class StuckFileSystem(FakeFileSystem):
        def remove(self, path: Path) -> None:
            raise PermissionError("locked")

    fs = StuckFileSystem()
    fs.commit_errors = [FileExistsError("taken")]
    with pytest.raises(StoreWriteError) as info:
        _store(tmp_path, fs).put("test.note/1", {"text": "x"}, PRODUCER)
    assert isinstance(info.value.__cause__, FileExistsError)  # the write failure, not the cleanup failure
    assert "temporary file not removed" in caplog.text


# --- details of errors, files and logs (the stored bytes and fields are part of the contract) ---


def test_stored_payload_is_json_mode_by_alias_with_nulls(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = store.put("test.rich/1", {"when": "2026-01-02T03:04:05Z", "odd-name": 7}, PRODUCER)
    expected = {"when": "2026-01-02T03:04:05Z", "odd-name": 7, "maybe": None, "items": []}
    assert record.payload == expected  # JSON types, the alias as key, the null kept
    assert store.payload(record.result_id) == expected
    assert record.payload_sha256 == payload_sha256(expected)


def test_invalid_payload_hint_names_the_path(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ContractError) as info:
        store.put("test.rich/1", {"when": "2026-01-02T03:04:05Z", "odd-name": 7, "items": [1, "a"]}, PRODUCER)
    detail = info.value.detail
    assert detail.message == "payload is not a valid test.rich/1"
    assert detail.field == "items[1]"  # spec 6: the path inside the payload
    assert detail.expected == {"kind": "test.rich/1"}
    assert detail.hint is not None
    assert detail.hint.startswith("items.1: ")
    with pytest.raises(ContractError) as long:
        store.put("test.huge/1", {"v": 1}, PRODUCER)
    assert long.value.detail.hint is not None
    assert len(long.value.detail.hint) == 2000


def test_missing_parent_is_reported_with_its_id(tmp_path: Path) -> None:
    missing = _next_id(b"other")
    with pytest.raises(ContractError) as info:
        _store(tmp_path).put("test.note/1", {"text": "c"}, PRODUCER, parents=[missing])
    assert info.value.detail.message == "parent result not found"
    assert info.value.detail.received == missing


def test_missing_result_is_reported_with_its_id(tmp_path: Path) -> None:
    missing = _next_id()
    with pytest.raises(ContractError) as info:
        _store(tmp_path).get(missing)
    assert info.value.detail.message == f"no result {missing}"
    assert info.value.detail.received == missing


def test_split_payload_bytes_follow_the_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("eng_contract.store._results.PAYLOAD_SPLIT_BYTES", 10)
    record = _store(tmp_path).put("test.note/1", {"text": "x" * 500}, PRODUCER)
    gz = _final(tmp_path, record.result_id).with_name(f"{record.result_id}.payload.json.gz")
    # spec 4.5.4 step 1: gzip with mtime=0 and compression level 6
    assert gz.read_bytes() == gzip.compress(canonical_json({"text": "x" * 500, "level": 1}), compresslevel=6, mtime=0)


@pytest.mark.parametrize("failure", [PermissionError("locked"), FileExistsError("taken")])
def test_split_payload_file_commit_is_retried_and_fails_with_an_incident(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: OSError
) -> None:
    monkeypatch.setattr("eng_contract.store._results.PAYLOAD_SPLIT_BYTES", 10)
    fs = FakeFileSystem()
    fs.commit_errors = [failure]
    delays: list[float] = []
    store = _store(tmp_path, fs, delays.append)
    if isinstance(failure, PermissionError):
        record = store.put("test.note/1", {"text": "x" * 50}, PRODUCER)
        assert delays == [0.05]  # the payload file is retried with the injected sleep
        assert store.payload(record.result_id) == {"text": "x" * 50, "level": 1}
    else:
        with pytest.raises(StoreWriteError) as info:
            store.put("test.note/1", {"text": "x" * 50}, PRODUCER)
        assert info.value.detail.incident_id
        assert delays == []


def test_integrity_messages_name_the_defect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    first = store.put("test.note/1", {"text": "a"}, PRODUCER)
    second = store.put("test.note/1", {"text": "b"}, PRODUCER)
    _final(tmp_path, second.result_id).write_bytes(_final(tmp_path, first.result_id).read_bytes())
    assert "another result id" in _integrity(store, second.result_id).detail.message
    monkeypatch.setattr("eng_contract.store._results.PAYLOAD_SPLIT_BYTES", 10)
    split = store.put("test.note/1", {"text": "x" * 100}, PRODUCER)
    gz = _final(tmp_path, split.result_id).with_name(f"{split.result_id}.payload.json.gz")
    gz.write_bytes(gzip.compress(b"[1]"))
    assert "not an object" in _integrity(store, split.result_id).detail.message
    gz.write_bytes(gzip.compress(canonical_json({"text": "z", "level": 1})))
    assert "differs from payload_sha256" in _integrity(store, split.result_id).detail.message


def test_store_errors_are_capped_at_the_message_limit(tmp_path: Path) -> None:
    fs = FakeFileSystem()
    fs.commit_errors = [FileExistsError("e" * 3000)]
    with pytest.raises(StoreWriteError) as info:
        _store(tmp_path, fs).put("test.note/1", {"text": "x"}, PRODUCER)
    assert len(info.value.detail.message) == 2000


def test_fake_filesystem_reports_paths_and_failures(tmp_path: Path) -> None:
    fs = FakeFileSystem()
    assert fs.commit_errors == []
    assert fs.read_errors == []
    fs.write_new(tmp_path / "a", b"1")
    with pytest.raises(FileExistsError) as exists:
        fs.write_new(tmp_path / "a", b"2")
    assert str(exists.value) == str(tmp_path / "a")
    with pytest.raises(FileNotFoundError) as missing:
        fs.read(tmp_path / "none")
    assert str(missing.value) == str(tmp_path / "none")
    fs.write_new(tmp_path / "b", b"2")
    with pytest.raises(FileExistsError) as taken:
        fs.commit(tmp_path / "b", tmp_path / "a")
    assert str(taken.value) == str(tmp_path / "a")
    fs.remove(tmp_path / "none")  # a missing file is not an error
    fs.partial_write = 3
    with pytest.raises(OSError, match="disk full"):
        fs.write_new(tmp_path / "c", b"123456")
    assert fs.read(tmp_path / "c") == b"123"  # the partial file stays


def test_fake_filesystem_replace_overwrites_and_injects_errors(tmp_path: Path) -> None:
    fs = FakeFileSystem()
    fs.write_new(tmp_path / "a", b"old")
    fs.write_new(tmp_path / "t", b"new")
    fs.commit_errors = [PermissionError("locked"), PermissionError("again")]
    with pytest.raises(PermissionError, match="locked"):
        fs.replace(tmp_path / "t", tmp_path / "a")
    assert [str(e) for e in fs.commit_errors] == ["again"]  # one error per call, in order
    fs.commit_errors = []
    fs.replace(tmp_path / "t", tmp_path / "a")
    assert fs.files == {tmp_path / "a": b"new"}


def test_write_atomic_replace_and_temporary_name(tmp_path: Path) -> None:
    class Spy(FakeFileSystem):
        def __init__(self) -> None:
            super().__init__()
            self.temporaries: list[Path] = []

        def write_new(self, path: Path, data: bytes) -> None:
            self.temporaries.append(path)
            super().write_new(path, data)

    fs = Spy()
    final = tmp_path / "state.json"
    fs.files[final] = b"old"
    write_atomic(fs, final, b"new", _ids(), lambda _s: None, replace=True)
    assert fs.files == {final: b"new"}
    suffix = fs.temporaries[0].name.removeprefix("state.json.").removesuffix(".tmp")
    assert len(suffix) == 16  # 8 random bytes in hexadecimal
    assert int(suffix, 16) >= 0


def test_unremovable_temporary_file_log_record(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    class Stuck(FakeFileSystem):
        def remove(self, path: Path) -> None:
            raise PermissionError("locked")

    fs = Stuck()
    fs.commit_errors = [FileExistsError("taken")]
    with caplog.at_level(logging.WARNING, logger="eng_contract._fs"), pytest.raises(StoreWriteError):
        _store(tmp_path, fs).put("test.note/1", {"text": "x"}, PRODUCER)
    (record,) = [r for r in caplog.records if r.name == "eng_contract._fs"]
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "temporary file not removed"
    assert getattr(record, "file", "").endswith(".tmp")
    assert record.exc_info is not None


def test_real_filesystem_new_files_are_private(tmp_path: Path) -> None:
    RealFileSystem().write_new(tmp_path / "a.tmp", b"1")
    if sys.platform != "win32":  # Windows has no POSIX permission bits
        assert stat.S_IMODE((tmp_path / "a.tmp").stat().st_mode) == 0o600
