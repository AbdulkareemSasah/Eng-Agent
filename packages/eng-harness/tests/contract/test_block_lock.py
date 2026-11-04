"""The committed block lock file matches the registry (plan 0001 T5; spec 0001 AC4)."""

import importlib.util
import json
import sys
from pathlib import Path

from eng_harness.block import LOCK_PATH, Registry, check_lock, discover, load_lock

import eng_harness

DATA = Path(__file__).resolve().parents[1] / "data" / "blocks"


def _load(path: Path, name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[name]
    return module


def test_lock_matches_registry() -> None:
    assert Path(eng_harness.__file__).parent / "blocks.lock.json" == LOCK_PATH
    registry = discover()
    assert check_lock(registry, load_lock(LOCK_PATH)) == ()
    # Sorted by name, as the spec requires.
    names = [entry["name"] for entry in json.loads(LOCK_PATH.read_text(encoding="utf-8"))]
    assert names == sorted(names)


def test_lock_on_fixture_blocks(tmp_path: Path) -> None:
    alpha = _load(DATA / "alpha_v1.py", "fixture_alpha_v1").alpha  # type: ignore[attr-defined]  # B-104: module object
    changed = _load(DATA / "alpha_v1_changed.py", "fixture_alpha_changed").alpha  # type: ignore[attr-defined]  # B-104: module object
    lock = tmp_path / "fixture.lock.json"
    lock.write_text(json.dumps([{"name": "alpha", "version": 1, "code_sha256": alpha.code_sha256}]), encoding="utf-8")
    assert check_lock(Registry([alpha]), load_lock(lock)) == ()
    findings = check_lock(Registry([changed]), load_lock(lock))
    assert [f.code for f in findings] == ["VERSION_BUMP_REQUIRED"]
