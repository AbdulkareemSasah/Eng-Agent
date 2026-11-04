"""Result store: atomic writes, payload split, integrity (plan T14; spec 4.4, 4.5.3, 4.5.4; AC16 to AC21a).

Expected paths, delays and limits come from the spec text, not from the implementation.
"""

import copy
import gzip
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from eng_contract._fs import FakeFileSystem, FileSystem, RealFileSystem
from pydantic import BaseModel, ConfigDict, JsonValue

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


KINDS = NEUTRAL_KINDS.extend({"test.note/1": Note})
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
    for bad in ("../../etc/passwd", "res_short", "mdl_" + _next_id()[4:], ""):
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
    for kind, payload in (
        ("test.note/1", {"text": 5}),  # wrong type
        ("test.note/1", {"text": "a", "surplus": 1}),  # extra field
        ("verdicts.set/1", {}),  # required fields missing
        ("test.unknown/1", {"text": "a"}),  # not registered
        ("test.note", {"text": "a"}),  # not a kind name
    ):
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


def test_real_filesystem_write_is_exclusive(tmp_path: Path) -> None:
    fs = RealFileSystem()
    fs.write_new(tmp_path / "a.tmp", b"1")
    with pytest.raises(FileExistsError):
        fs.write_new(tmp_path / "a.tmp", b"2")
    assert fs.read(tmp_path / "a.tmp") == b"1"
