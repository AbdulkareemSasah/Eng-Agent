"""Content hash over the static import closure (plan 0003 T2; spec 0003 AC6, AC7, 4.5)."""

import hashlib
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


def _tree(root: Path, files: dict[str, str]) -> None:
    """Write `files` (path relative to the `eng_harness` root -> source) under `root`."""
    for relative, source in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)


@pytest.mark.parametrize(
    ("calc_source", "files", "expected"),
    [
        # relative imports: level 1 in a module, level 2 in a module of a subpackage
        (
            "from eng_harness.sub import a\n",
            {"sub/__init__.py": "", "sub/a.py": "from . import c\n", "sub/c.py": ""},
            {"eng_harness.sub.a", "eng_harness.sub.c"},
        ),
        (
            "from eng_harness.sub import a\n",
            {"sub/__init__.py": "", "sub/a.py": "from .. import b\n", "b.py": ""},
            {"eng_harness.sub.a", "eng_harness.b"},
        ),
        (
            "from eng_harness.sub import a\n",
            {"sub/__init__.py": "", "sub/a.py": "from ..b import X\n", "b.py": ""},
            {"eng_harness.sub.a", "eng_harness.b"},
        ),
        (
            "from eng_harness.sub import a\n",
            {"sub/__init__.py": "", "sub/a.py": "from .c import X\n", "sub/c.py": ""},
            {"eng_harness.sub.a", "eng_harness.sub.c"},
        ),
        # in a package __init__, level 1 is the package itself
        (
            "from eng_harness.sub import X\n",
            {"sub/__init__.py": "from . import c\nX = 1\n", "sub/c.py": ""},
            {"eng_harness.sub", "eng_harness.sub.c"},
        ),
        (
            "from eng_harness.sub import X\n",
            {"sub/__init__.py": "from .c import Y\nX = 1\n", "sub/c.py": ""},
            {"eng_harness.sub", "eng_harness.sub.c"},
        ),
        # a package __init__ is hashed only when it supplies an attribute (never as an implicit parent)
        ("from eng_harness.sub import c\n", {"sub/__init__.py": "X = 1\n", "sub/c.py": ""}, {"eng_harness.sub.c"}),
        (
            "from eng_harness.sub import c, X\n",
            {"sub/__init__.py": "X = 1\n", "sub/c.py": ""},
            {"eng_harness.sub", "eng_harness.sub.c"},
        ),
        (
            "from eng_harness.sub import X, c\n",
            {"sub/__init__.py": "X = 1\n", "sub/c.py": ""},
            {"eng_harness.sub", "eng_harness.sub.c"},
        ),
        (
            "from eng_harness.sub import c, d\n",
            {"sub/__init__.py": "X = 1\n", "sub/c.py": "", "sub/d.py": ""},
            {"eng_harness.sub.c", "eng_harness.sub.d"},
        ),
        ("import eng_harness.sub.c\n", {"sub/__init__.py": "X = 1\n", "sub/c.py": ""}, {"eng_harness.sub.c"}),
        (
            "import eng_harness.sub.c, eng_harness.b\n",
            {"sub/c.py": "", "b.py": ""},
            {"eng_harness.sub.c", "eng_harness.b"},
        ),
        ("import eng_harness\n", {"__init__.py": "X = 1\n"}, {"eng_harness"}),
        ("from eng_harness import b\n", {"__init__.py": "X = 1\n", "b.py": ""}, {"eng_harness.b"}),
        # names that are not in eng_harness are not followed, even when a file of that name exists
        ("import os\nfrom other import b\nimport eng_harness_x\n", {"b.py": "", "eng_harness_x.py": ""}, set()),
        # an import under `else` of a `__main__` test runs on import; one in its body does not
        (
            'if __name__ == "__main__":\n    from eng_harness import b\nelse:\n    from eng_harness import c\n',
            {"b.py": "", "c.py": ""},
            {"eng_harness.c"},
        ),
        (
            'if __name__ == "__main__":\n    pass\nelif True:\n    from eng_harness import c\n',
            {"c.py": ""},
            {"eng_harness.c"},
        ),
        # a `try` is scanned; a module that is imported twice is hashed once
        (
            "try:\n    from eng_harness import b\nexcept ImportError:\n    from eng_harness import b\n",
            {"b.py": ""},
            {"eng_harness.b"},
        ),
    ],
)
def test_closure_exact(
    calc_source: str,
    files: dict[str, str],
    expected: set[str],
    fixtures: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "eng_harness"
    _tree(root, files)
    definition = _calc_from(tmp_path, monkeypatch, fixtures, calc_source, name="tmpmod")
    closure = _hash.module_hashes(definition, root=root)
    assert set(closure) == expected | {"tmpmod"}
    assert list(closure) == sorted(closure)
    own = (tmp_path / "tmpmod.py").read_bytes()
    assert closure["tmpmod"] == hashlib.sha256(own).hexdigest()


def test_closure_digest_is_of_lf_source(fixtures: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "eng_harness"
    root.mkdir()
    (root / "b.py").write_bytes(b"x = 1\r\ny = 2\rz = 3\n")
    definition = _calc_from(tmp_path, monkeypatch, fixtures, "from eng_harness import b\n", name="tmpmod")
    closure = _hash.module_hashes(definition, root=root)
    assert closure["eng_harness.b"] == hashlib.sha256(b"x = 1\ny = 2\nz = 3\n").hexdigest()


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("import importlib\n", "imports importlib"),
        ("from importlib import util\n", "imports importlib"),
        ("x = __import__('os')\n", "uses __import__"),
        ("y = builtins.__import__\n", "uses __import__"),
        ("def f() -> None:\n    import os\n", "imports inside a function or class"),
        ("async def f() -> None:\n    from os import path\n", "imports inside a function or class"),
        ("class C:\n    import os\n", "imports inside a function or class"),
        ("f = lambda: __import__('os')\n", "uses __import__"),
        ('if __name__ == "__main__":\n    pass\nelse:\n    x = __import__("os")\n', "uses __import__"),
        ('if __name__ == "__main__":\n    pass\nelse:\n    import importlib\n', "imports importlib"),
        (
            "def f() -> None:\n    if __name__ == '__main__':\n        pass\n    else:\n        import os\n",
            "imports inside a function or class",
        ),
    ],
)
def test_refusal_messages(
    source: str,
    message: str,
    fixtures: ModuleType,
    kinds: KindRegistry,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = _calc_from(tmp_path, monkeypatch, fixtures, source)
    with pytest.raises(CalcRegistryError) as caught:
        _hash.content_hash(definition, kinds)
    assert caught.value.rule == "hash"
    assert str(caught.value) == f"harness.fixture_sum: hash: {message}"


def test_else_branch_of_main_test_is_hashed(
    fixtures: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A helper imported only under `else` of `if __name__ == '__main__'` changes the closure (AC6)."""
    root = tmp_path / "eng_harness"
    _tree(root, {"errors.py": "x = 1\n"})
    source = 'if __name__ == "__main__":\n    pass\nelse:\n    x = 1\n    from eng_harness import errors\n'
    definition = _calc_from(tmp_path, monkeypatch, fixtures, source, name="tmpmod")
    before = _hash.module_hashes(definition, root=root)
    assert "eng_harness.errors" in before
    (root / "errors.py").write_text("x = 2\n")
    assert _hash.module_hashes(definition, root=root) != before


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("no_file", "the source of badcalc is not available"),
        ("pyc", "badcalc has no source file (badcalc.pyc)"),
        ("pyc_helper", "eng_harness.calcs._gone has no source file (bytecode only)"),
        ("syntax", "badcalc does not parse: "),
        ("nul", "badcalc does not parse: "),
    ],
)
def test_source_refusal_messages(
    setup: str,
    message: str,
    fixtures: ModuleType,
    kinds: KindRegistry,
    root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = {"syntax": "def (:\n", "nul": "x = 1\x00\n", "pyc_helper": "from eng_harness.calcs import _gone\n"}
    definition = _calc_from(
        tmp_path, monkeypatch, fixtures, None if setup == "no_file" else sources.get(setup, "x = 1\n")
    )
    if setup == "pyc":
        (tmp_path / "badcalc.py").rename(tmp_path / "badcalc.pyc")
        monkeypatch.setattr(sys.modules["badcalc"], "__file__", str(tmp_path / "badcalc.pyc"))
    if setup == "pyc_helper":
        (root / "calcs" / "_gone.pyc").write_bytes(b"\x00")
    with pytest.raises(CalcRegistryError) as caught:
        _hash.content_hash(definition, kinds, root=root)
    assert caught.value.rule == "hash"
    assert str(caught.value).startswith(f"harness.fixture_sum: hash: {message}")


def test_locate_prefers_module_then_package_and_ignores_others(tmp_path: Path) -> None:
    _tree(tmp_path, {"m.py": "", "m/__init__.py": "", "p/__init__.py": "", "p/q.py": ""})
    assert _hash._locate("eng_harness.m", tmp_path, "c") == tmp_path / "m.py"
    assert _hash._locate("eng_harness.p", tmp_path, "c") == tmp_path / "p" / "__init__.py"
    assert _hash._locate("eng_harness.p.q", tmp_path, "c") == tmp_path / "p" / "q.py"
    assert _hash._locate("eng_harness", tmp_path, "c") is None  # no root __init__ in this tree
    (tmp_path / "__init__.py").write_text("")
    assert _hash._locate("eng_harness", tmp_path, "c") == tmp_path / "__init__.py"
    assert _hash._locate("eng_harness.absent", tmp_path, "c") is None
    assert _hash._locate("eng_harnessx", tmp_path, "c") is None
    assert _hash._locate("os", tmp_path, "c") is None


def test_hash_object_fields(fixtures: ModuleType, kinds: KindRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    """The hashed object is exactly the one of spec 0003 4.5 (checked through `payload_sha256`)."""
    definition: CalcDef = fixtures.fixture_sum
    seen: list[dict[str, object]] = []

    def spy(payload: dict[str, object]) -> str:
        seen.append(payload)
        return "0" * 64

    monkeypatch.setattr(_hash, "payload_sha256", spy)
    assert _hash.content_hash(definition, kinds) == "0" * 64
    (payload,) = seen
    assert payload == {
        "hash_version": "harness.calc_hash/1",
        "calc_id": definition.id,
        "version": definition.version,
        "title": definition.title,
        "method_source": definition.method_source,
        "verification": str(definition.verification),
        "output_kind": definition.output_kind,
        "input_schema": fixtures.FixtureIn.model_json_schema(),
        "output_schema": fixtures.FixtureOut.model_json_schema(),
        "modules": _hash.module_hashes(definition),
        "eng_contract_version": eng_contract.__version__,
    }


def test_input_type_must_be_a_model(fixtures: ModuleType, kinds: KindRegistry) -> None:
    definition = replace(fixtures.fixture_sum, input_type=int)
    with pytest.raises(CalcRegistryError) as caught:
        _hash.content_hash(definition, kinds)
    assert str(caught.value) == "harness.fixture_sum: hash: the input type is not a model"


def test_registry_error_message_and_rule() -> None:
    error = CalcRegistryError("some_rule", "a.b", "why")
    assert str(error) == "a.b: some_rule: why"
    assert error.rule == "some_rule"
    assert isinstance(error, ValueError)
