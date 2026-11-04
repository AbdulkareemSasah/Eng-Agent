"""Blocks, workflows, registry, code hash and lock check (plan 0001 T5; spec 0001 AC2, AC3, AC4)."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from eng_harness.block import (
    BlockDef,
    LockFinding,
    Registry,
    RegistryError,
    WorkflowDef,
    block,
    check_lock,
    workflow,
    write_lock,
)
from pydantic import BaseModel

DATA = Path(__file__).resolve().parents[1] / "data" / "blocks"


def _load(path: Path, name: str) -> ModuleType:
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


class In(BaseModel):
    value: int


class Out(BaseModel):
    value: int


def _expected_hash(path: Path) -> str:
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_registration_rules() -> None:
    async def good(ctx: object, inp: In) -> Out:
        return Out(value=inp.value)

    def sync_fn(ctx: object, inp: In) -> Out:
        return Out(value=inp.value)

    async def plain_input(ctx: object, inp: int) -> Out:
        return Out(value=inp)

    async def plain_output(ctx: object, inp: In) -> int:
        return inp.value

    with pytest.raises(RegistryError, match="async"):
        block(name="sync_one", version=1)(sync_fn)  # type: ignore[arg-type]  # B-104: wrong shape on purpose
    with pytest.raises(RegistryError, match="input"):
        block(name="plain_in", version=1)(plain_input)  # type: ignore[arg-type]  # B-104: wrong shape on purpose
    with pytest.raises(RegistryError, match="output"):
        block(name="plain_out", version=1)(plain_output)  # type: ignore[arg-type]  # B-104: wrong shape on purpose
    for bad_name in ("Upper", "1abc", "has-dash", "", "a b"):
        with pytest.raises(RegistryError, match="name"):
            block(name=bad_name, version=1)(good)
    for bad_version in (0, -1, 10000, True):
        with pytest.raises(RegistryError, match="version"):
            block(name="ok_name", version=bad_version)(good)

    first = block(name="same", version=1)(good)
    second = block(name="same", version=2)(good)
    assert isinstance(first, BlockDef)
    assert first.input_model is In
    assert first.output_model is Out
    with pytest.raises(RegistryError, match="duplicate"):
        Registry([first, second])
    registry = Registry([first])
    extended = registry.with_(block(name="other", version=9999)(good))
    assert [b.name for b in registry.blocks] == ["same"]
    assert [b.name for b in extended.blocks] == ["other", "same"]


def test_workflow_rules() -> None:
    module = _load(DATA / "beta_v2.py", "fixture_beta_v2")
    beta = module.beta
    assert isinstance(beta, WorkflowDef)
    assert isinstance(beta, BlockDef)
    assert beta.required_basis == ("limits.drift_ratio",)
    assert beta.min_server_builds == {"fixture-server": "build-1"}
    assert beta.always_ask == ("fixture_unlock",)
    assert beta.options_model is None

    async def fn(ctx: object, inp: In) -> Out:
        return Out(value=inp.value)

    for description in ("", "x" * 501):
        with pytest.raises(RegistryError, match="description"):
            workflow(name="wf", version=1, description=description)(fn)
    assert workflow(name="wf", version=1, description="x" * 500)(fn).description == "x" * 500


def test_missing_source_is_refused() -> None:
    namespace: dict[str, object] = {"In": In, "Out": Out, "block": block}
    exec(  # noqa: S102  # B-104: builds a function whose module has no readable source
        "async def f(ctx, inp: In) -> Out:\n    return Out(value=1)\n", namespace
    )
    fn = namespace["f"]
    with pytest.raises(RegistryError, match="source"):
        block(name="nosrc", version=1)(fn)  # type: ignore[arg-type]  # B-104: namespace value is untyped


def test_code_hash_is_stable(tmp_path: Path) -> None:
    path = DATA / "alpha_v1.py"
    alpha = _load(path, "fixture_alpha_v1").alpha
    assert alpha.name == "alpha"
    assert alpha.version == 1
    assert alpha.code_sha256 == _expected_hash(path)

    crlf = tmp_path / "alpha_crlf.py"
    crlf.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert _load(crlf, "fixture_alpha_crlf").alpha.code_sha256 == alpha.code_sha256

    code = (
        "import importlib.util, sys\n"
        "spec = importlib.util.spec_from_file_location('fx', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['fx'] = m; spec.loader.exec_module(m)\n"
        "sys.stdout.write(m.alpha.code_sha256)\n"
    )
    out = subprocess.run(  # noqa: S603  # B-104: runs this interpreter on a fixed snippet
        [sys.executable, "-c", code, str(path)], capture_output=True, text=True, check=True
    )
    assert out.stdout == alpha.code_sha256


def test_check_lock(tmp_path: Path) -> None:
    alpha = _load(DATA / "alpha_v1.py", "fixture_alpha_v1").alpha
    changed = _load(DATA / "alpha_v1_changed.py", "fixture_alpha_changed").alpha
    beta = _load(DATA / "beta_v2.py", "fixture_beta_v2").beta
    assert alpha.code_sha256 != changed.code_sha256

    lock = [
        {"name": "alpha", "version": 1, "code_sha256": alpha.code_sha256},
        {"name": "beta", "version": 2, "code_sha256": beta.code_sha256},
    ]
    assert check_lock(Registry([alpha, beta]), lock) == ()

    findings = check_lock(Registry([changed, beta]), lock)
    assert [(f.name, f.code) for f in findings] == [("alpha", "VERSION_BUMP_REQUIRED")]
    assert isinstance(findings[0], LockFinding)

    # A bumped version with a new hash is not a bump violation, but the lock is stale until rewritten.
    bumped = BlockDef(**{**vars_of(changed), "version": 2})
    assert [(f.name, f.code) for f in check_lock(Registry([bumped, beta]), lock)] == [("alpha", "LOCK_STALE")]
    assert [(f.name, f.code) for f in check_lock(Registry([alpha]), lock)] == [("beta", "LOCK_STALE")]
    assert [(f.name, f.code) for f in check_lock(Registry([alpha, beta]), lock[:1])] == [("beta", "LOCK_STALE")]

    # write_lock writes entries sorted by name and refuses a changed hash under an unchanged version.
    path = tmp_path / "blocks.lock.json"
    write_lock(Registry([beta, alpha]), path)
    assert json.loads(path.read_text(encoding="utf-8")) == lock
    with pytest.raises(RegistryError, match="VERSION_BUMP_REQUIRED"):
        write_lock(Registry([changed, beta]), path)
    assert json.loads(path.read_text(encoding="utf-8")) == lock
    write_lock(Registry([bumped, beta]), path)
    assert [e["version"] for e in json.loads(path.read_text(encoding="utf-8"))] == [2, 2]


def vars_of(definition: BlockDef[BaseModel, BaseModel]) -> dict[str, object]:
    return {
        "name": definition.name,
        "version": definition.version,
        "input_model": definition.input_model,
        "output_model": definition.output_model,
        "fn": definition.fn,
        "module": definition.module,
        "code_sha256": definition.code_sha256,
    }
