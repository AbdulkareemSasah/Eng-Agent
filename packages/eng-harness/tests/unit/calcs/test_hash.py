"""Content hash over the static import closure (plan 0003 T2; spec 0003 AC6, AC7, 4.5)."""

import importlib.util
import re
import shutil
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import eng_contract
import pytest
from eng_contract.kinds import NEUTRAL_KINDS, KindRegistry
from eng_contract.params import eng_param
from pydantic import BaseModel, ConfigDict, create_model

import eng_harness
from eng_harness._calc import _hash
from eng_harness.calc import CalcDef, CalcRegistry, CalcRegistryError, InputMeta, TraceBuilder

SRC = Path(eng_harness.__file__).resolve().parent
_FIXTURES = Path(__file__).resolve().parents[2] / "data" / "calcs" / "fixture_calcs.py"
_DIGEST = "[0-9a-f]{64}"


@pytest.fixture(scope="module")
def fixtures() -> ModuleType:
    """The fixture calc module, loaded by path (it is test data, not a package)."""
    spec = importlib.util.spec_from_file_location("fixture_calcs", _FIXTURES)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fixture_calcs"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def kinds(fixtures: ModuleType) -> KindRegistry:
    return NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: fixtures.FixtureOut})


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A private copy of the `eng_harness` sources, so a test may change a helper."""
    target = tmp_path / "eng_harness"
    shutil.copytree(SRC, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def _calc_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixtures: ModuleType, source: str | None, *, name: str = "badcalc"
) -> CalcDef:
    """The fixture calc, moved into a module `name` whose file holds `source` (None: the module has no file)."""
    module = ModuleType(name)
    if source is not None:
        path = tmp_path / f"{name}.py"
        path.write_text(source)
        module.__file__ = str(path)
    monkeypatch.setitem(sys.modules, name, module)

    def fn(inp: object, meta: InputMeta, trace: TraceBuilder) -> BaseModel:
        raise AssertionError("never run")

    fn.__module__ = name
    result: CalcDef = replace(fixtures.fixture_sum, fn=fn)
    return result


def test_hash_covers_helpers_and_metadata(
    fixtures: ModuleType, kinds: KindRegistry, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    definition: CalcDef = fixtures.fixture_sum
    base = _hash.content_hash(definition, kinds)
    assert re.fullmatch(_DIGEST, base)
    assert _hash.content_hash(definition, kinds) == base
    assert _hash.content_hash(definition, kinds, root=root) == base
    closure = _hash.module_hashes(definition)
    assert {"fixture_calcs", "eng_harness.calc", "eng_harness.errors"} <= set(closure)  # errors: a transitive helper
    assert all(re.fullmatch(_DIGEST, digest) for digest in closure.values())

    helper = root / "errors.py"
    original = helper.read_bytes()
    helper.write_bytes(original + b" ")  # one byte
    one_byte = _hash.content_hash(definition, kinds, root=root)
    for line_ending in (b"\r\n", b"\r"):  # only the line endings change: same hash
        helper.write_bytes(original.replace(b"\n", line_ending))
        assert _hash.content_hash(definition, kinds, root=root) == base

    wider_input = create_model("WiderInput", __base__=fixtures.FixtureIn, extra_mm=(float, eng_param(unit="mm")))

    class OtherOut(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        total: float
        more: float

    other_kinds = NEUTRAL_KINDS.extend({fixtures.OUTPUT_KIND: OtherOut})
    with monkeypatch.context() as patch:
        patch.setattr(eng_contract, "__version__", "9.9.9")
        contract_version = _hash.content_hash(definition, kinds)
    variants = {
        "helper byte": one_byte,
        "id": _hash.content_hash(replace(definition, id="harness.other"), kinds),
        "version": _hash.content_hash(replace(definition, version=4), kinds),
        "title": _hash.content_hash(replace(definition, title="Other"), kinds),
        "method_source": _hash.content_hash(replace(definition, method_source="Other"), kinds),
        "verification": _hash.content_hash(replace(definition, verification="verified"), kinds),
        "input schema": _hash.content_hash(replace(definition, input_type=wider_input), kinds),
        "output schema": _hash.content_hash(definition, other_kinds),
        "contract version": contract_version,
    }
    assert all(digest != base for digest in variants.values()), variants
    assert len(set(variants.values())) == len(variants)


def test_closure_follows_relative_and_type_checking_imports(
    fixtures: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "eng_harness"
    root.mkdir()
    (root / "a.py").write_text(
        "from typing import TYPE_CHECKING\nfrom . import b\n"
        "if TYPE_CHECKING:\n    from .c import X\n"
        'if __name__ == "__main__":\n    from eng_harness.d import y\n'
    )
    for name in ("b", "c", "d"):
        (root / f"{name}.py").write_text(f"{name} = 1\n")
    definition = _calc_from(tmp_path, monkeypatch, fixtures, "import os\nfrom eng_harness.a import Z\n", name="tmpmod")
    names = set(_hash.module_hashes(definition, root=root))
    assert names == {"tmpmod", "eng_harness.a", "eng_harness.b", "eng_harness.c"}


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\n",
        "from importlib import import_module\n",
        "import importlib.util\n",
        "x = __import__('os')\n",
        "def f() -> None:\n    import os\n",
        "class C:\n    from os import path\n",
    ],
)
def test_unhashable_calc_refused(
    source: str,
    fixtures: ModuleType,
    kinds: KindRegistry,
    root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    own = _calc_from(tmp_path, monkeypatch, fixtures, source)
    with pytest.raises(CalcRegistryError) as caught:
        CalcRegistry(kinds, [own])  # the default hasher is the real one
    assert caught.value.rule == "hash"
    # the same source in a helper that the calc imports, one level down
    (root / "calcs").mkdir(exist_ok=True)
    (root / "calcs" / "_helper.py").write_text(source)
    (root / "calcs" / "_outer.py").write_text("from eng_harness.calcs import _helper\n")
    via_helper = _calc_from(tmp_path, monkeypatch, fixtures, "from eng_harness.calcs import _outer\n")
    with pytest.raises(CalcRegistryError) as nested:
        _hash.content_hash(via_helper, kinds, root=root)
    assert nested.value.rule == "hash"


def test_source_not_available_refused(
    fixtures: ModuleType, kinds: KindRegistry, root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_file = _calc_from(tmp_path, monkeypatch, fixtures, None, name="no_file")
    not_loaded = _calc_from(tmp_path, monkeypatch, fixtures, "x = 1\n", name="not_loaded")
    monkeypatch.delitem(sys.modules, "not_loaded")
    bytecode = _calc_from(tmp_path, monkeypatch, fixtures, "x = 1\n", name="bytecode_only")
    (tmp_path / "bytecode_only.py").rename(tmp_path / "bytecode_only.pyc")
    monkeypatch.setattr(sys.modules["bytecode_only"], "__file__", str(tmp_path / "bytecode_only.pyc"))
    (root / "calcs").mkdir(exist_ok=True)
    (root / "calcs" / "_gone.pyc").write_bytes(b"\x00")  # a helper that is bytecode only
    sourceless_helper = _calc_from(tmp_path, monkeypatch, fixtures, "from eng_harness.calcs import _gone\n", name="h")
    broken = _calc_from(tmp_path, monkeypatch, fixtures, "def (:\n", name="broken_syntax")
    for definition in (no_file, not_loaded, bytecode, sourceless_helper, broken):
        with pytest.raises(CalcRegistryError) as caught:
            _hash.content_hash(definition, kinds, root=root)
        assert caught.value.rule == "hash", definition.fn.__module__
