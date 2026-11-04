"""Blocks, workflows, registry, code hash and lock check (plan 0001 T5; spec 0001 AC2, AC3, AC4)."""

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import BaseModel

import eng_harness.block as block_module
from eng_harness.block import (
    BlockDef,
    LockFinding,
    Registry,
    RegistryError,
    WorkflowDef,
    block,
    check_lock,
    load_lock,
    main,
    workflow,
    write_lock,
)

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
        block(name="sync_one", version=1)(cast_any(sync_fn))
    with pytest.raises(RegistryError, match="input"):
        block(name="plain_in", version=1)(cast_any(plain_input))
    with pytest.raises(RegistryError, match="output"):
        block(name="plain_out", version=1)(cast_any(plain_output))
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
    with pytest.raises(RegistryError, match="source") as info:
        block(name="nosrc", version=1)(cast_any(fn))
    assert str(info.value) == f"source of module {fn.__module__} is not available"


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
    bumped: BlockDef[BaseModel, BaseModel] = BlockDef(**{**vars_of(changed), "version": 2})
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


def cast_any(value: object) -> Any:
    """Hand a deliberately wrong shape to a typed decorator."""
    return value


def vars_of(definition: BlockDef[BaseModel, BaseModel]) -> dict[str, Any]:
    return {
        "name": definition.name,
        "version": definition.version,
        "input_model": definition.input_model,
        "output_model": definition.output_model,
        "fn": definition.fn,
        "module": definition.module,
        "code_sha256": definition.code_sha256,
    }


def test_error_messages_name_the_rule() -> None:
    async def good(ctx: object, inp: In) -> Out:
        return Out(value=inp.value)

    async def one_param(ctx: object) -> Out:
        return Out(value=1)

    async def plain_input(ctx: object, inp: int) -> Out:
        return Out(value=inp)

    async def plain_output(ctx: object, inp: In) -> int:
        return inp.value

    def sync_fn(ctx: object, inp: In) -> Out:
        return Out(value=inp.value)

    def message(name: str, version: int, fn: object) -> str:
        with pytest.raises(RegistryError) as info:
            block(name=name, version=version)(cast_any(fn))
        return str(info.value)

    assert message("a", 1, sync_fn) == "a: the block function must be async def"
    assert message("a", 1, one_param) == "a: the block function takes (ctx, inp)"
    assert message("a", 1, plain_input) == "a: the input type must be a Pydantic BaseModel subclass"
    assert message("a", 1, plain_output) == "a: the output type must be a Pydantic BaseModel subclass"
    assert message("Bad", 1, good) == "block name 'Bad' must match ^[a-z][a-z0-9_]*$"
    assert message("a", 0, good) == "a: version 0 must match ^[1-9][0-9]{0,3}$"
    assert message("a", True, good).startswith("a: version True")
    assert block(name="a", version=1)(good).version == 1
    assert block(name="a", version=9999)(good).version == 9999
    with pytest.raises(RegistryError) as info:
        Registry([block(name="x", version=1)(good), block(name="x", version=1)(good)])
    assert str(info.value) == "duplicate block name 'x'"


def test_definition_fields() -> None:
    async def fn(ctx: object, inp: In) -> Out:
        return Out(value=inp.value)

    definition = block(name="fields", version=3)(fn)
    assert definition.fn is fn
    assert definition.module == fn.__module__
    assert (definition.name, definition.version) == ("fields", 3)
    assert len(definition.code_sha256) == 64

    plain = workflow(name="wf_plain", version=1, description="d")(fn)
    assert plain.description == "d"
    assert plain.required_basis == ()
    assert plain.min_server_builds == {}
    assert plain.always_ask == ()
    assert plain.options_model is None
    assert plain.fn is fn
    assert plain.module == fn.__module__
    assert plain.code_sha256 == definition.code_sha256

    full = workflow(
        name="wf_full",
        version=2,
        description="desc",
        required_basis=("a.b",),
        min_server_builds={"srv": "b1"},
        always_ask=("tool",),
        options_model=In,
    )(fn)
    assert (full.name, full.version, full.input_model, full.output_model) == ("wf_full", 2, In, Out)
    assert full.required_basis == ("a.b",)
    assert full.min_server_builds == {"srv": "b1"}
    assert full.always_ask == ("tool",)
    assert full.options_model is In
    with pytest.raises(RegistryError) as info:
        workflow(name="wf", version=1, description="")(fn)
    assert str(info.value) == "wf: description must be 1 to 500 characters"


def test_lock_file_round_trip(tmp_path: Path) -> None:
    alpha = _load(DATA / "alpha_v1.py", "fixture_alpha_v1").alpha
    path = tmp_path / "lock.json"
    write_lock(Registry([alpha]), path)
    expected = [{"name": "alpha", "version": 1, "code_sha256": alpha.code_sha256}]
    assert path.read_text(encoding="utf-8") == json.dumps(expected, indent=2) + "\n"
    assert load_lock(path) == expected
    write_lock(Registry([alpha]), path)  # an unchanged lock is rewritten without error
    assert load_lock(path) == expected


@pytest.mark.parametrize(
    "content",
    [
        '{"name": "a"}',
        "[1]",
        '[{"name": "a", "version": 1}]',
        '[{"name": "a", "code_sha256": "x"}]',
        '[{"version": 1, "code_sha256": "x"}]',
    ],
)
def test_malformed_lock_is_refused(tmp_path: Path, content: str) -> None:
    path = tmp_path / "bad.lock.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(RegistryError) as info:
        load_lock(path)
    assert str(info.value) == "bad.lock.json: expected a list of {name, version, code_sha256} entries"


def test_main_writes_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "blocks.lock.json"
    monkeypatch.setattr(block_module, "LOCK_PATH", path)
    assert main(["--write-lock"]) == 0
    assert path.read_text(encoding="utf-8") == "[]\n"
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "eng_harness.block" in err
    assert "--write-lock" in err
