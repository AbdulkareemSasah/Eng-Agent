"""`csi_save_model` with `as_new_revision` and `csi_open_revision` on the synthetic fake (plan 0007 T5; spec 0007 AC31).

The run's copies folder holds the working file `W` (the file the host has open) and the snapshots. A snapshot is a
verified copy of `W` saved in place first; the host keeps `W` open. `csi_open_revision` copies a snapshot whose hash
still is the recorded one to a new working file and opens that file. The adapter imports are inside the tests so a
missing module fails the test.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from eng_contract.envelope import FailureEnvelope, SuccessEnvelope
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.store import ResultStore

from eng_harness.adapters.csi._reconcile import CsiReconciler
from eng_harness.servers import CallEffect, ServerManager

from . import test_csi_read_state_tool as base
from .test_csi_session_ops import ConfigFactory

store = base.store  # the fixture of the read-state tests, by name
_call, _seeded, run_port = base._call, base._seeded, base.run_port

ORIGINAL = b"model-v1"
SAVE = {"as_new_revision": True}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _working(run_dir: Path) -> Path:
    """The working file `W`: a working copy in the run's copies folder."""
    path = run_dir / "copies" / "model.EDB"
    path.parent.mkdir(parents=True)
    path.write_bytes(ORIGINAL)
    return path


def _revisions(run_dir: Path) -> Any:
    from eng_harness.adapters.csi._revisions import Revisions

    return Revisions(run_dir / "copies", run_dir / "adapter" / "revisions.json")


async def _path(manager: ServerManager, pid: int) -> str | None:
    """The path of the model the host has open, asked of the fake directly."""
    target = {"target": {"product": "ETABS", "pid": pid}}
    reply = await manager.call("csi", "main", "csi_model_info", target, CallEffect.READ)
    block = reply.content[0]
    assert hasattr(block, "text")
    path = json.loads(block.text)["model_path"]
    assert path is None or isinstance(path, str)
    return path


def test_save_as_new_revision_and_open_revision(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """AC31: a snapshot of the saved working file, W stays open; a restore opens a copy of an unchanged snapshot."""
    _seeded(control)
    work = _working(run_dir)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        target = {"target": {"product": "ETABS", "pid": pid}}
        info = await port.describe("csi_save_model")
        assert (info.effect, info.action, info.model_param) == ("write", "save", "model")
        assert info.saves_new_file({"model": "m", "as_new_revision": True}) is True
        assert info.saves_new_file({"model": "m", "as_new_revision": False}) is False
        assert info.saves_new_file({"model": "m"}) is False
        opening = await port.describe("csi_open_revision")
        assert (opening.effect, opening.action, opening.model_param) == ("write", "open", "model")
        assert opening.saves_new_file({"model": "m", "revision": "x"}) is True
        assert (await port.describe("csi_read_model_state")).saves_new_file({"model": "m"}) is False

        saved = await _call(port, "csi_save_model", **SAVE)
        assert isinstance(saved, SuccessEnvelope), saved
        snapshot = run_dir / "copies" / "model.rev001.EDB"
        assert work.read_bytes() == ORIGINAL + b"\n"  # the fake's save changed the bytes of W in place
        assert snapshot.read_bytes() == work.read_bytes()
        assert saved.summary["saved_file"] == {"name": snapshot.name, "sha256": _sha(snapshot)}
        assert _sha(snapshot) == _sha(work)
        assert await _path(manager, pid) == str(work)  # the host keeps W open
        assert [(role, tool) for role, tool, _ in recorder.sent] == [
            ("main", "csi_model_info"),
            ("main", "csi_save_model"),
        ]
        assert recorder.sent[1][2] == {"confirm": True, **target}  # in place: no path, and not as_new_revision

        fixed = _sha(snapshot)
        recorder.sent.clear()
        opened = await _call(port, "csi_open_revision", revision=snapshot.name)
        assert isinstance(opened, SuccessEnvelope), opened
        restored = run_dir / "copies" / "model.rev001.w1.EDB"
        assert restored.read_bytes() == snapshot.read_bytes()
        assert _sha(snapshot) == fixed  # the snapshot is unchanged
        assert opened.summary["saved_file"] == {"name": restored.name, "sha256": fixed}
        assert await _path(manager, pid) == str(restored)  # opened on the bound instance
        assert [(role, tool) for role, tool, _ in recorder.sent] == [("main", "csi_open_model")]
        assert recorder.sent[0][2] == {"path": str(restored), "confirm": True, **target}  # W was not saved first
        assert work.read_bytes() == ORIGINAL + b"\n"

    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir), opened=work)


def test_second_snapshot_and_second_restore(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """Each snapshot has its own number and each restore its own working file; nothing is overwritten."""
    _seeded(control)
    work = _working(run_dir)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        for _ in range(2):
            assert isinstance(await _call(port, "csi_save_model", **SAVE), SuccessEnvelope)
        first, second = (run_dir / "copies" / f"model.rev00{n}.EDB" for n in (1, 2))
        assert first.read_bytes() == ORIGINAL + b"\n"
        assert second.read_bytes() == ORIGINAL + b"\n\n"
        for expected in ("model.rev001.w1.EDB", "model.rev001.w2.EDB"):
            answer = await _call(port, "csi_open_revision", revision=first.name)
            assert isinstance(answer, SuccessEnvelope), answer
            saved = answer.summary["saved_file"]
            assert isinstance(saved, dict)
            assert saved["name"] == expected
        assert work.read_bytes() == ORIGINAL + b"\n\n"

    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir), opened=work)


def test_existing_snapshot_target_is_refused(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """The snapshot's path is the adapter's; a file already there is refused before anything is saved or replaced."""
    _seeded(control)
    work = _working(run_dir)
    taken = run_dir / "copies" / "model.rev001.EDB"
    taken.write_bytes(b"somebody's file")

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        refused = await _call(port, "csi_save_model", **SAVE)
        assert isinstance(refused, FailureEnvelope), refused
        assert refused.error.code is ErrorCode.CONFLICT
        assert taken.read_bytes() == b"somebody's file"
        assert work.read_bytes() == ORIGINAL  # the in-place save was not sent either
        assert [tool for _role, tool, _args in recorder.sent] == ["csi_model_info"]

    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir), opened=work)


def test_changed_snapshot_is_a_conflict(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """A snapshot saved over after it was made (its hash is not the recorded one) is not opened."""
    _seeded(control)
    work = _working(run_dir)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        saved = await _call(port, "csi_save_model", **SAVE)
        assert isinstance(saved, SuccessEnvelope), saved
        snapshot = run_dir / "copies" / "model.rev001.EDB"
        snapshot.write_bytes(snapshot.read_bytes() + b"x")
        recorder.sent.clear()
        refused = await _call(port, "csi_open_revision", revision=snapshot.name)
        assert isinstance(refused, FailureEnvelope), refused
        assert refused.error.code is ErrorCode.CONFLICT
        assert sorted(p.name for p in (run_dir / "copies").iterdir()) == ["model.EDB", "model.rev001.EDB"]
        assert await _path(manager, pid) == str(work)
        assert recorder.sent == []  # nothing reached the host

    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir), opened=work)


def test_unknown_snapshot(make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path) -> None:
    """A file that no save of this run made is not a snapshot, wherever it lies."""
    _seeded(control)
    work = _working(run_dir)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        for name in ("model.EDB", "model.rev009.EDB", "../model.EDB"):
            refused = await _call(port, "csi_open_revision", revision=name)
            assert isinstance(refused, FailureEnvelope), refused
            assert refused.error.code is ErrorCode.NOT_FOUND
        assert recorder.sent == []

    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir), opened=work)


def test_no_write_to_a_snapshot(make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path) -> None:
    """With a snapshot open in the host, any write or save is refused; reading and restoring are not writes to it."""
    _seeded(control)
    work = _working(run_dir)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        assert isinstance(await _call(port, "csi_save_model", **SAVE), SuccessEnvelope)
        snapshot = run_dir / "copies" / "model.rev001.EDB"
        target = {"target": {"product": "ETABS", "pid": pid}}
        await manager.call(
            "csi", "main", "csi_open_model", {"path": str(snapshot), "confirm": True, **target}, CallEffect.WRITE
        )
        before = snapshot.read_bytes()
        recorder.sent.clear()
        for tool, args in (
            ("csi_save_model", {}),
            ("csi_save_model", SAVE),
            ("csi_assign_frame_section", {"frame": "F1", "section": "C30"}),
            ("csi_run_analysis", {}),
        ):
            refused = await _call(port, tool, **args)
            assert isinstance(refused, FailureEnvelope), (tool, refused)
            assert refused.error.code is ErrorCode.CONFLICT
        assert snapshot.read_bytes() == before
        assert all(tool == "csi_model_info" for _role, tool, _args in recorder.sent)
        read = await _call(port, "csi_read_model_state")
        assert isinstance(read, SuccessEnvelope), read
        restored = await _call(port, "csi_open_revision", revision=snapshot.name)
        assert isinstance(restored, SuccessEnvelope), restored  # opening a copy is not a write to the snapshot

    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir), opened=work)


def test_writes_pass_when_the_open_file_is_not_a_snapshot(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """An in-place save and an edit go through on W, and with no model open the host's own answer is given."""
    _seeded(control, frames=[{"name": "F1", "section": "B1"}], frame_sections=[{"name": "C30"}])
    work = _working(run_dir)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        assert isinstance(await _call(port, "csi_save_model"), SuccessEnvelope)
        edited = await _call(port, "csi_assign_frame_section", frame="F1", section="C30")
        assert isinstance(edited, SuccessEnvelope), edited
        assert work.read_bytes() == ORIGINAL + b"\n"

    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir), opened=work)


def test_no_model_open(make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path) -> None:
    """A snapshot needs the open file: with none the save is refused with `model_open`, and nothing is saved."""
    _seeded(control)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        refused = await _call(port, "csi_save_model", **SAVE)
        assert isinstance(refused, FailureEnvelope), refused
        assert refused.error.code is ErrorCode.PRECONDITION_FAILED
        assert refused.error.precondition is not None
        assert refused.error.precondition.value == "model_open"
        assert [tool for _role, tool, _args in recorder.sent] == ["csi_model_info"]

    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir))


def test_revision_files_need_the_wiring(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """A port built without a revision store refuses both operations; a plain save still works."""
    _seeded(control)
    work = _working(run_dir)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        for tool, args in (("csi_save_model", SAVE), ("csi_open_revision", {"revision": "model.rev001.EDB"})):
            refused = await _call(port, tool, **args)
            assert isinstance(refused, FailureEnvelope), refused
            assert refused.error.code is ErrorCode.INTERNAL
            assert refused.error.incident_id is not None
        assert recorder.sent == []
        assert isinstance(await _call(port, "csi_save_model"), SuccessEnvelope)
        assert work.read_bytes() == ORIGINAL + b"\n"

    run_port(make_config(), run_dir, store, body, opened=work)


def test_open_model_is_not_a_tool_of_the_workflow(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """`csi_open_model` takes no path from a block; only `csi_open_revision` sends one: a failure envelope (B-543)."""
    _seeded(control)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        refused = await _call(port, "csi_open_model", path="x.EDB")
        assert isinstance(refused, FailureEnvelope), refused
        assert refused.error.code is ErrorCode.INVALID_ARGUMENT
        assert refused.error.field == "path"
        assert recorder.sent == []

    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir))


def test_no_reconciliation_of_saves(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """A save or a restore cut off by a timeout is not reconciled by reading edit state: the engineer decides."""
    _seeded(control)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        assert port.supports_reconcile("csi_assign_frame_section") is True  # the reconciler is wired
        for tool in ("csi_save_model", "csi_open_revision", "csi_open_model"):
            assert port.supports_reconcile(tool) is False, tool

    reconciler = CsiReconciler(product="ETABS", tolerance_ratio=None)
    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir), reconciler=reconciler)


def test_revisions_files(tmp_path: Path) -> None:
    """The record survives a new process, names count up, and a snapshot is told by name and folder."""
    from eng_harness.adapters.csi._revisions import Revisions

    folder, record = tmp_path / "copies", tmp_path / "adapter" / "revisions.json"
    folder.mkdir()
    work = folder / "model.EDB"
    work.write_bytes(b"one")
    revisions = Revisions(folder, record)
    assert revisions.target(work) == folder / "model.rev001.EDB"
    saved = revisions.snapshot(work, revisions.target(work))
    assert saved.model_dump() == {"name": "model.rev001.EDB", "sha256": hashlib.sha256(b"one").hexdigest()}
    work.write_bytes(b"two")
    again = Revisions(folder, record)  # a resumed process reads the record from disk
    assert again.target(work) == folder / "model.rev002.EDB"
    assert again.snapshot(work, again.target(work)).name == "model.rev002.EDB"
    assert again.is_snapshot(folder / "model.rev001.EDB") is True
    assert again.is_snapshot(folder / "model.rev003.EDB") is False
    assert again.is_snapshot(work) is False
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "model.rev001.EDB").write_bytes(b"one")
    assert again.is_snapshot(other / "model.rev001.EDB") is False
    path, restored = again.reopen("model.rev001.EDB")
    assert (path, restored.name, path.read_bytes()) == (folder / "model.rev001.w1.EDB", "model.rev001.w1.EDB", b"one")
    assert restored.sha256 == hashlib.sha256(b"one").hexdigest()
    assert again.reopen("model.rev001.EDB")[0] == folder / "model.rev001.w2.EDB"
    assert json.loads(record.read_text()) == {
        "snapshots": {
            "model.rev001.EDB": hashlib.sha256(b"one").hexdigest(),
            "model.rev002.EDB": hashlib.sha256(b"two").hexdigest(),
        }
    }


def test_revisions_refusals(tmp_path: Path) -> None:
    """An existing target, a changed or missing snapshot and an unknown name are each refused, nothing written."""
    from eng_harness.adapters.csi._revisions import Revisions

    folder = tmp_path / "copies"
    folder.mkdir()
    work = folder / "model.EDB"
    work.write_bytes(b"one")
    revisions = Revisions(folder, tmp_path / "revisions.json")
    (folder / "model.rev001.EDB").write_bytes(b"taken")
    with pytest.raises(ContractError) as taken:
        revisions.target(work)
    assert taken.value.detail.code is ErrorCode.CONFLICT
    assert taken.value.detail.message == "a file is already at the snapshot's path"
    assert taken.value.detail.received == "model.rev001.EDB"
    with pytest.raises(ContractError) as raced:
        revisions.snapshot(work, folder / "model.rev001.EDB")
    assert raced.value.detail.code is ErrorCode.CONFLICT
    assert raced.value.detail.message == "a file is already at the target"
    assert raced.value.detail.received == "model.rev001.EDB"
    assert (folder / "model.rev001.EDB").read_bytes() == b"taken"
    assert not (tmp_path / "revisions.json").exists()  # a refused snapshot is not recorded
    (folder / "model.rev001.EDB").unlink()
    snapshot = revisions.snapshot(work, revisions.target(work))
    (folder / snapshot.name).write_bytes(b"changed")
    with pytest.raises(ContractError) as changed:
        revisions.reopen(snapshot.name)
    assert changed.value.detail.code is ErrorCode.CONFLICT
    assert changed.value.detail.message == "the snapshot's hash differs from the recorded one"
    assert changed.value.detail.received == snapshot.name
    assert sorted(p.name for p in folder.iterdir()) == ["model.EDB", "model.rev001.EDB"]
    (folder / snapshot.name).unlink()
    with pytest.raises(ContractError) as missing:
        revisions.reopen(snapshot.name)
    assert missing.value.detail.code is ErrorCode.NOT_FOUND
    with pytest.raises(ContractError) as unknown:
        revisions.reopen("model.rev005.EDB")
    assert unknown.value.detail.code is ErrorCode.NOT_FOUND
    assert unknown.value.detail.received == "model.rev005.EDB"
    assert unknown.value.detail.message == "no snapshot of this run has that name"
    assert missing.value.detail.message == "no snapshot of this run has that name"
    assert missing.value.detail.received == snapshot.name


def test_copy_with_a_different_hash_is_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A copy whose bytes do not hash as the original is deleted, refused with `CONFLICT` and not recorded."""
    from eng_harness.adapters.csi import _revisions

    class Unreliable:
        """`hashlib` whose second digest differs: the first is of the original, the second of the copy."""

        calls = 0

        @staticmethod
        def sha256(data: bytes) -> Any:
            Unreliable.calls += 1
            return hashlib.sha256(data + (b"?" if Unreliable.calls > 1 else b""))

    folder = tmp_path / "copies"
    folder.mkdir()
    work = folder / "model.EDB"
    work.write_bytes(b"one")
    revisions = _revisions.Revisions(folder, tmp_path / "revisions.json")
    monkeypatch.setattr(_revisions, "hashlib", Unreliable)
    with pytest.raises(ContractError) as refused:
        revisions.snapshot(work, revisions.target(work))
    assert refused.value.detail.code is ErrorCode.CONFLICT
    assert refused.value.detail.received == "model.rev001.EDB"
    assert refused.value.detail.message == "the copy's hash differs from the original"
    assert [p.name for p in folder.iterdir()] == ["model.EDB"]
    assert not (tmp_path / "revisions.json").exists()


def test_record_is_written_through_a_temporary_file_in_new_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record's folders are created as deep as needed and the file is swapped in from `<record>.tmp`."""
    import os

    from eng_harness.adapters.csi import _revisions

    folder = tmp_path / "copies"
    folder.mkdir()
    work = folder / "model.EDB"
    work.write_bytes(b"one")
    record = tmp_path / "deep" / "er" / "revisions.json"
    swaps: list[tuple[str, str]] = []
    real = os.replace

    def replace(source: Any, destination: Any) -> None:
        swaps.append((Path(source).name, Path(destination).name))
        real(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    revisions = _revisions.Revisions(folder, record)
    revisions.snapshot(work, revisions.target(work))
    assert swaps == [("revisions.json.tmp", "revisions.json")]
    assert sorted(p.name for p in record.parent.iterdir()) == ["revisions.json"]


def test_only_the_pathless_original_open_changes_no_model_content(
    make_config: ConfigFactory, control: Path, store: ResultStore, run_dir: Path
) -> None:
    """AC52 (B-562): the descriptor guarantees unchanged content only for `csi_open_model` without `path`."""
    _seeded(control)

    async def body(port: Any, recorder: Any, pid: int, manager: ServerManager) -> None:
        opening = await port.describe("csi_open_model")
        assert (opening.effect, opening.action) == ("write", "open")  # the write effect and open action stay
        assert opening.opens_model_without_writing({"model": "m"}) is True
        assert opening.opens_model_without_writing({"model": "m", "path": "x.EDB"}) is False
        assert opening.opens_model_without_writing({"model": "m", "path": None}) is False
        revision = await port.describe("csi_open_revision")
        assert revision.opens_model_without_writing({"model": "m", "revision": "x"}) is False
        assert revision.opens_model_without_writing({"model": "m"}) is False
        for tool in ("csi_save_model", "csi_assign_frame_section", "csi_read_model_state"):
            assert (await port.describe(tool)).opens_model_without_writing({"model": "m"}) is False, tool
        assert recorder.sent == []

    run_port(make_config(), run_dir, store, body, revisions=_revisions(run_dir))
