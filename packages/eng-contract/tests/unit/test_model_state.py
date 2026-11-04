"""Model identity and revision state (plan T14; spec 4.5.5; AC22).

The expected file location and revisions come from the spec text, not from the implementation.
"""

import json
from pathlib import Path

import pytest
from eng_contract._fs import FakeFileSystem, FileSystem, RealFileSystem
from pydantic import ValidationError

from eng_contract.canonical import canonical_json
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource, new_model_id
from eng_contract.store import LocationClass, ModelState, ModelStateStore, StoreIntegrityError, Workspace

MODEL = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"
OTHER = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAW"
SHA = "c" * 64


def _store(root: Path, fs: FileSystem | None = None) -> ModelStateStore:
    ws = Workspace(root=root, classification=LocationClass.LOCAL)
    return ModelStateStore(ws, FixedClock(1_767_323_045_678, 1000), fs)


def _file(root: Path, model_id: str = MODEL) -> Path:
    return root / ".eng" / "state" / "models" / f"{model_id}.json"


def _code(info: pytest.ExceptionInfo[ContractError]) -> ErrorCode:
    return info.value.detail.code


def test_increment_compare_and_set(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create(MODEL)
    assert (created.revision, created.derived_from, created.promoted_from) == (0, None, [])
    for expected in range(3):
        assert store.increment(MODEL, expected_revision=expected).revision == expected + 1
    assert store.increment(MODEL, expected_revision=3, fingerprint="fp", file_sha256=SHA).revision == 4
    before = _file(tmp_path).read_bytes()
    with pytest.raises(ContractError) as info:
        store.increment(MODEL, expected_revision=2)
    assert _code(info) is ErrorCode.CONFLICT
    assert _file(tmp_path).read_bytes() == before  # unchanged
    state = store.get(MODEL)
    assert state is not None
    assert (state.revision, state.fingerprint, state.file_sha256) == (4, "fp", SHA)
    assert before == canonical_json(state.model_dump(mode="json"))
    assert [p.name for p in _file(tmp_path).parent.iterdir()] == [_file(tmp_path).name]  # no temporary file


def test_increment_replaces_fingerprint_and_hash(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create(MODEL)
    store.increment(MODEL, 0, fingerprint="fp", file_sha256=SHA)
    state = store.increment(MODEL, 1)
    assert (state.fingerprint, state.file_sha256) == (None, None)  # they describe the earlier revision


def test_create_and_get(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.get(MODEL) is None
    derived = store.create(OTHER, derived_from=MODEL)
    assert derived.derived_from == MODEL
    assert derived.updated_at == "2026-01-02T03:04:05.678Z"
    assert store.get(OTHER) == derived
    with pytest.raises(ContractError) as info:
        store.create(OTHER)
    assert _code(info) is ErrorCode.CONFLICT
    assert store.get(OTHER) == derived


def test_unknown_model(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ContractError) as info:
        store.increment(MODEL, 0)
    assert _code(info) is ErrorCode.NOT_FOUND
    with pytest.raises(ContractError) as promoted:
        store.record_promotion(MODEL, OTHER)
    assert _code(promoted) is ErrorCode.NOT_FOUND


def test_malformed_model_id_is_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    for bad in ("../x", "mdl_short", "res_01ARZ3NDEKTSV4RRFFQ69G5FAV", ""):
        for call in (store.get, store.create, lambda m: store.increment(m, 0)):
            with pytest.raises(ContractError) as info:
                call(bad)
            assert _code(info) is ErrorCode.INVALID_ARGUMENT
    with pytest.raises(ContractError):
        store.create(MODEL, derived_from="bad")
    assert not (tmp_path / ".eng").exists()


def test_record_promotion(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create(MODEL)
    first = store.record_promotion(MODEL, OTHER)
    assert first.promoted_from == [OTHER]
    assert first.revision == 0  # a promotion is a link, not a write to the model
    assert store.record_promotion(MODEL, OTHER).promoted_from == [OTHER]  # recorded once
    third = new_model_id(SeededIdSource(b"s", FixedClock(0)))
    assert store.record_promotion(MODEL, third).promoted_from == [OTHER, third]
    assert store.get(MODEL) is not None
    with pytest.raises(ContractError):
        store.record_promotion(MODEL, "bad")


def test_state_write_retries_a_sharing_violation(tmp_path: Path) -> None:
    fs = FakeFileSystem()
    store = _store(tmp_path, fs)
    store.create(MODEL)
    fs.commit_errors = [PermissionError("sharing violation")] * 2
    assert store.increment(MODEL, 0).revision == 1  # os.replace with the retries of spec 4.5.4 step 5
    fs.commit_errors = [PermissionError("sharing violation")] * 4
    with pytest.raises(ContractError) as info:
        store.increment(MODEL, 1)
    assert _code(info) is ErrorCode.INTERNAL
    state = store.get(MODEL)
    assert state is not None
    assert state.revision == 1
    assert list(fs.files) == [_file(tmp_path)]


@pytest.mark.parametrize(
    "content",
    [b"{", b'{"revision":0,"revision":1}', b'{"revision":NaN}', json.dumps({"revision": -1}).encode()],
)
def test_corrupt_state_is_integrity_error(tmp_path: Path, content: bytes) -> None:
    store = _store(tmp_path)
    store.create(MODEL)
    _file(tmp_path).write_bytes(content)
    with pytest.raises(StoreIntegrityError) as info:
        store.get(MODEL)
    assert _code(info) is ErrorCode.INTERNAL


def test_state_of_another_model_is_integrity_error(tmp_path: Path) -> None:
    store = _store(tmp_path, RealFileSystem())
    store.create(MODEL)
    store.create(OTHER)
    _file(tmp_path, OTHER).write_bytes(_file(tmp_path).read_bytes())
    with pytest.raises(StoreIntegrityError):
        store.get(OTHER)


def test_state_model_rules() -> None:
    base = {
        "contract": "eng-contract/1",
        "model_id": MODEL,
        "revision": 0,
        "derived_from": None,
        "fingerprint": None,
        "file_sha256": None,
        "updated_at": "2026-01-02T03:04:05.678Z",
    }
    assert ModelState.model_validate(base).promoted_from == []
    for over in ({"revision": -1}, {"fingerprint": "x" * 201}, {"file_sha256": "ABC"}, {"extra": 1}):
        with pytest.raises(ValidationError):
            ModelState.model_validate(base | over)
