"""Harness-side model identity (plan 0002 T10; spec 0002 AC30, ADR-0032).

The import of the store is inside the test so a missing module fails the test (ImportError) rather than collection.
"""

import hashlib
import json
from pathlib import Path

from eng_contract.errors import WarningCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import ModelStateStore, Workspace
from eng_contract.store._workspace import LocationClass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_resolution_rules(tmp_path: Path) -> None:
    """Content hash, path hash, a new identity, a copy derived from the older one, and a save with no path stored."""
    from eng_harness.adapters._identity import IdentityStore

    clock = FixedClock(1_700_000_000_000)
    workspace = Workspace(root=tmp_path, classification=LocationClass.LOCAL)
    states = ModelStateStore(workspace, clock)
    store = IdentityStore(workspace=workspace, states=states, ids=SeededIdSource(b"identity", clock))
    original = tmp_path / "original.EDB"
    original.write_bytes(b"model-v1")

    first = store.resolve(original)
    assert first.revision == 0
    assert first.derived_from is None
    assert first.warnings == ()
    again = store.resolve(original)
    assert (again.model_id, again.revision, again.warnings) == (first.model_id, 0, ())

    original.write_bytes(b"model-v2")  # same location, bytes the harness did not write
    edited = store.resolve(original)
    assert edited.model_id == first.model_id
    assert edited.revision == 1
    assert edited.warnings == (WarningCode.MODEL_CHANGED_OUTSIDE,)
    quiet = store.resolve(original)
    assert (quiet.model_id, quiet.revision, quiet.warnings) == (first.model_id, 1, ())

    copy = tmp_path / "copies" / "original.EDB"
    copy.parent.mkdir()
    copy.write_bytes(original.read_bytes())
    derived = store.resolve(copy)
    assert derived.model_id != first.model_id
    assert derived.derived_from == first.model_id
    assert derived.revision == 0
    assert derived.warnings == ()
    assert store.resolve(copy).model_id == derived.model_id
    assert store.resolve(original).model_id == first.model_id  # the path that matches keeps its identity

    third = tmp_path / "third.EDB"
    third.write_bytes(original.read_bytes())
    other = store.resolve(third)  # the content is known, the path is not: derived from the older identity
    assert other.model_id not in {first.model_id, derived.model_id}
    assert other.derived_from == first.model_id

    copy.write_bytes(b"model-v3")
    saved = store.record_save(derived.model_id, copy)
    digest = _sha(copy)
    assert saved.file_sha256 == digest
    assert saved.revision == derived.revision + 1
    content = json.loads((tmp_path / ".eng/state/model-files/by-sha256" / f"{digest}.json").read_text())
    assert content == {"model_id": derived.model_id, "revision": saved.revision}

    root = tmp_path / ".eng" / "state" / "model-files"
    for path in (root / "by-sha256").glob("*.json"):
        assert set(json.loads(path.read_text())) == {"model_id", "revision"}
    for path in (root / "by-path").glob("*.json"):
        text = path.read_text()
        assert set(json.loads(text)) == {"model_id", "last_file_sha256"}
        assert "/" not in text
        assert "\\" not in text
        assert "original" not in text
        assert str(copy) not in text
        assert str(third) not in text
