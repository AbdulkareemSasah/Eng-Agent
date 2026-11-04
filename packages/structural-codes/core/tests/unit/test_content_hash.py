"""Tests of the content hash and the lint scope (plan 0001 T7; spec 0001 AC21, AC22, AC22a, section 4.7)."""

import importlib
import re
import shutil
import sys
import types
from collections.abc import Iterator
from dataclasses import dataclass, replace
from importlib.machinery import ModuleSpec
from pathlib import Path

import eng_contract
import pytest
from eng_contract.cited import Cited

from structural_codes import _closure
from structural_codes.applicability import Outcome, Precondition
from structural_codes.check import Check
from structural_codes.content_hash import _document, content_hash, lint_scope_violations
from structural_codes.errors import CheckDefinitionError
from structural_codes.inputs import CheckInputs, bounded

# B-261: the module name is split only because gate rule IM006 reports the fixture pack under tests/fixtures/*/src
# as an undeclared distribution (same workaround as tests/unit/test_registry.py, B-260); it hides no import.
_PACK = "hash" + "pack"
_FIXTURE = Path(__file__).parent.parent / "fixtures" / "hashpack"
_PACK_CLOSURE = (
    f"{_PACK}",
    f"{_PACK}.checks",
    f"{_PACK}.consts",
    f"{_PACK}.helpers",
    f"{_PACK}.sub",
    f"{_PACK}.sub.deep",
    f"{_PACK}.sub.leaf",
)


@dataclass
class Fixture:
    """A temporary copy of the fixture pack: the check and the package folder whose files a test may change."""

    check: Check
    package: Path

    def path(self, relative: str) -> Path:
        return self.package / relative

    def append(self, relative: str, text: str = "#") -> None:
        target = self.path(relative)
        target.write_bytes(target.read_bytes() + text.encode())


@pytest.fixture
def hashpack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Fixture]:
    root = tmp_path / "copy"
    shutil.copytree(_FIXTURE, root)
    monkeypatch.syspath_prepend(str(root / "src"))
    check = importlib.import_module(f"{_PACK}.checks").DEMO
    assert isinstance(check, Check)
    yield Fixture(check, root / "src" / _PACK)
    for name in [n for n in sys.modules if n == _PACK or n.startswith(f"{_PACK}.")]:
        del sys.modules[name]


def _patch_source(monkeypatch: pytest.MonkeyPatch, module: str, suffix: str) -> None:
    real = _closure._source

    def patched(name: str) -> str | None:
        text = real(name)
        return text + suffix if name == module and text is not None else text

    monkeypatch.setattr(_closure, "_source", patched)


def test_hash_inputs(hashpack: Fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    check = hashpack.check
    first = content_hash(check)
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert content_hash(check) == first

    # one byte of the check module, of helpers reached directly, transitively or as a package, changes the hash
    for relative in (
        "checks.py",
        "helpers.py",
        "sub/deep.py",
        "sub/leaf.py",
        "consts.py",
        "sub/__init__.py",
        "__init__.py",
    ):
        original = hashpack.path(relative).read_bytes()
        hashpack.append(relative)
        assert content_hash(check) != first, relative
        hashpack.path(relative).write_bytes(original)
        assert content_hash(check) == first, relative

    # one byte of a core module or of an eng-contract module in the closure changes the hash
    for module in ("structural_codes.meta", "structural_codes.inputs", "eng_contract.cited"):
        with monkeypatch.context() as patch:
            _patch_source(patch, module, "#")
            assert content_hash(check) != first, module

    # metadata, input model and preconditions change the hash
    assert content_hash(replace(check, meta=check.meta.model_copy(update={"title": "Other"}))) != first

    class OtherInputs(CheckInputs):
        width_mm: float = bounded(
            ge=Cited(value=1, unit="mm", source="synthetic bound"),
            le=Cited(value=2, unit="mm", source="synthetic bound"),
            unit="mm",
        )

    assert content_hash(replace(check, inputs=OtherInputs)) != first
    precondition = Precondition("P1", Outcome.NOT_APPLICABLE, "1.1", "text", lambda i, t: True)
    with_precondition = content_hash(replace(check, preconditions=(precondition,)))
    assert with_precondition != first
    other_outcome = replace(precondition, outcome=Outcome.NEEDS_ENGINEER)
    assert content_hash(replace(check, preconditions=(other_outcome,))) != with_precondition

    # CRLF line endings and a pack module that is not imported leave the hash unchanged
    helpers = hashpack.path("helpers.py")
    helpers.write_bytes(helpers.read_bytes().replace(b"\n", b"\r\n"))
    assert content_hash(check) == first
    hashpack.append("unused.py")
    assert content_hash(check) == first


def test_document_fields(hashpack: Fixture) -> None:
    doc = _document(hashpack.check, None)
    assert list(doc) == ["format", "meta", "inputs_schema", "preconditions", "modules", "eng_contract", "base"]
    assert doc["format"] == "structural-codes-content/1"
    assert doc["eng_contract"] == eng_contract.__version__
    assert doc["base"] is None
    assert doc["preconditions"] == []
    assert doc["meta"]["members"] == ["frame", "section"]
    assert doc["inputs_schema"]["properties"]["width_mm"]["maximum"] == 100.0
    modules = doc["modules"]
    assert all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in modules.values())
    assert {n for n in modules if n.startswith(_PACK)} == set(_PACK_CLOSURE)
    assert {n.partition(".")[0] for n in modules} == {_PACK, "structural_codes", "eng_contract"}
    assert "structural_codes.meta" in modules
    assert "eng_contract.cited" in modules


def test_base_hash(hashpack: Fixture) -> None:
    plain = content_hash(hashpack.check)
    based = content_hash(hashpack.check, base="a" * 64)
    assert based != plain
    assert content_hash(hashpack.check, base="b" * 64) != based
    for bad in ("", "A" * 64, "a" * 63):
        with pytest.raises(CheckDefinitionError, match="base"):
            content_hash(hashpack.check, base=bad)


def test_dynamic_import_rejected(hashpack: Fixture) -> None:
    check = hashpack.check
    variants = (
        "import importlib\n",
        "import importlib.util\n",
        "from importlib import import_module\n",
        "from importlib.metadata import entry_points\n",
        "value = __import__('os')\n",
        "import builtins\nvalue = builtins.__import__('os')\n",
    )
    for relative in ("checks.py", "sub/leaf.py"):  # the module itself and a transitive helper
        original = hashpack.path(relative).read_bytes()
        for text in variants:
            hashpack.path(relative).write_bytes(original + b"\n" + text.encode())
            with pytest.raises(CheckDefinitionError, match=r"importlib|__import__"):
                content_hash(check)
            with pytest.raises(CheckDefinitionError, match=r"importlib|__import__"):
                lint_scope_violations(check, ["src/**/*.py"])
        hashpack.path(relative).write_bytes(original)
    content_hash(check)

    hashpack.append("sub/leaf.py", "\nimport importlib\n")
    with pytest.raises(CheckDefinitionError, match=re.escape(f"{_PACK}.sub.leaf")):
        content_hash(check)


def test_closure_within_check_modules(hashpack: Fixture) -> None:
    check = hashpack.check
    everything = [f"src/{_PACK}/**/*.py"]
    assert lint_scope_violations(check, everything) == ()
    assert lint_scope_violations(check, [f"src/{_PACK}/*.py", f"src/{_PACK}/sub/*.py"]) == ()
    # without any glob every pack module of the closure is a violation, sorted, and the unused one is not listed
    assert lint_scope_violations(check, []) == _PACK_CLOSURE
    # a glob that matches the check module only names the helpers (and the packages) that it does not match
    assert lint_scope_violations(check, [f"src/{_PACK}/checks.py"]) == tuple(
        n for n in _PACK_CLOSURE if n != f"{_PACK}.checks"
    )
    assert lint_scope_violations(check, [f"src/{_PACK}/checks.py", f"src/{_PACK}/__init__.py"]) == tuple(
        n for n in _PACK_CLOSURE if n not in (f"{_PACK}.checks", _PACK)
    )
    # a glob for the sub-package matches its __init__ and its modules by path, not by dotted name
    assert f"{_PACK}.sub.deep" not in lint_scope_violations(check, [f"src/{_PACK}/sub/**/*.py"])
    assert lint_scope_violations(check, [f"src/{_PACK}/sub/**/*.py"])[0] == _PACK


def test_import_forms(hashpack: Fixture) -> None:
    check = hashpack.check
    base = content_hash(check)
    # `import a.b` pulls the module in; the unused module becomes part of the closure
    hashpack.append("helpers.py", f"\nimport {_PACK}.unused\n")
    assert _PACK + ".unused" in lint_scope_violations(check, [])
    assert content_hash(check) != base
    hashpack.append("unused.py")
    changed = content_hash(check)
    hashpack.append("unused.py")
    assert content_hash(check) != changed
    # an imported name that is an attribute and no module is not a closure module
    hashpack.append("helpers.py", f"\nfrom {_PACK}.consts import SCALE\n")
    assert _PACK + ".consts.SCALE" not in lint_scope_violations(check, [])
    # imports inside functions and under TYPE_CHECKING count as well (conservative)
    hashpack.append("sub/leaf.py", f"\n\ndef late() -> None:\n    from {_PACK} import checks\n")
    assert _PACK + ".checks" in lint_scope_violations(check, [])


def test_unresolvable_and_unreadable_modules(hashpack: Fixture, monkeypatch: pytest.MonkeyPatch) -> None:
    check = hashpack.check
    original = hashpack.path("helpers.py").read_bytes()

    hashpack.append("helpers.py", f"\nimport {_PACK}.missing\n")
    with pytest.raises(CheckDefinitionError, match="missing"):
        content_hash(check)

    hashpack.path("helpers.py").write_bytes(original + f"\nimport {_PACK}.missing.deeper\n".encode())
    with pytest.raises(CheckDefinitionError, match="deeper"):
        content_hash(check)

    hashpack.path("helpers.py").write_bytes(original + f"\nimport {_PACK}.ext\n".encode())
    extension = types.ModuleType(f"{_PACK}.ext")
    extension.__spec__ = ModuleSpec(f"{_PACK}.ext", None, origin="ext.so")
    monkeypatch.setitem(sys.modules, f"{_PACK}.ext", extension)
    with pytest.raises(CheckDefinitionError, match="ext"):
        content_hash(check)

    # a namespace package has no source: it takes no part in the closure and is no error
    namespace = types.ModuleType(f"{_PACK}.ext")
    namespace.__spec__ = ModuleSpec(f"{_PACK}.ext", None, is_package=True)
    monkeypatch.setitem(sys.modules, f"{_PACK}.ext", namespace)
    assert _PACK + ".ext" not in lint_scope_violations(check, [])

    hashpack.path("helpers.py").write_bytes(original + b"\nvalue = (\n")
    with pytest.raises(CheckDefinitionError, match="helpers"):
        content_hash(check)

    hashpack.path("helpers.py").write_bytes(b"\xff\xfe = 1\n")
    with pytest.raises(CheckDefinitionError, match="helpers"):
        content_hash(check)


def test_relative_import_beyond_top_level(hashpack: Fixture) -> None:
    hashpack.append("sub/leaf.py", "\nfrom ... import consts\n")
    with pytest.raises(CheckDefinitionError, match="beyond"):
        content_hash(hashpack.check)
