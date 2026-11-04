"""Content hash over the static import closure (plan 0003 T2; spec 0003 AC6, AC7, 4.5)."""

import dataclasses
import hashlib
import importlib
import sys
import textwrap
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import eng_contract
import pytest
from eng_contract.kinds import NEUTRAL_KINDS, KindRegistry
from pydantic import BaseModel, create_model

from eng_harness._calc._hash import content_hash, module_hashes
from eng_harness.calc import CalcDef, CalcRegistry, CalcRegistryError

KIND = "harness.tmp_out/1"
_CALC = textwrap.dedent("""
    from typing import TYPE_CHECKING

    from pydantic import BaseModel

    from eng_harness.calc import CalcInput, InputMeta, TraceBuilder, calc
    from {pkg}.helpers import double

    if TYPE_CHECKING:
        from {pkg} import typing_only


    class Out(BaseModel):
        value: float


    class In(CalcInput):
        x: float = 0.0


    @calc(id="harness.tmp_calc", version=1, output_kind="{kind}", title="T", method_source="M")
    def run(inp: In, meta: InputMeta, trace: TraceBuilder) -> Out:
        return Out(value=double(inp.x))
""")
_HELPERS = """
    from . import deep


    def double(x: float) -> float:
        return deep.twice(x)


    def lazy() -> None:
        from {pkg} import late
"""
_FILES = {
    "__init__.py": "",
    "deep.py": "def twice(x: float) -> float:\n    return x * 2\n",
    "typing_only.py": "T = 1\n",
    "late.py": "L = 1\n",
    "unrelated.py": "U = 1\n",
    "calcs/__init__.py": "",
}
_DYNAMIC = {
    "importlib": 'import importlib\n\n\ndef load():\n    return importlib.import_module("json")\n',
    "dunder_import": 'def load():\n    return __import__("json")\n',
    "function_import": "def load():\n    import json\n\n    return json\n",
}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _append_hash_mark(data: bytes) -> bytes:
    return data + b"#"


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _with_endings(ending: bytes) -> Callable[[bytes], bytes]:
    return lambda data: _lf(data).replace(b"\n", ending)


class _Package:
    """A throwaway package holding one calc module and its helpers; the calc is imported once."""

    def __init__(self, root: Path, name: str, calc_src: str = _CALC) -> None:
        self.name = name
        self.root = root / name
        files = _FILES | {
            "helpers.py": textwrap.dedent(_HELPERS).format(pkg=name),
            "calcs/c.py": calc_src.format(pkg=name, kind=KIND),
        }
        for rel, text in files.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.module: Any = importlib.import_module(f"{name}.calcs.c")

    def path(self, rel: str) -> Path:
        return self.root / rel

    @property
    def definition(self) -> CalcDef:
        found: CalcDef = self.module.run
        return found

    @property
    def kinds(self) -> KindRegistry:
        return NEUTRAL_KINDS.extend({KIND: self.module.Out})

    def hash(self, definition: CalcDef | None = None, kinds: KindRegistry | None = None) -> str:
        return content_hash(definition or self.definition, kinds or self.kinds, package=self.name)

    def edit(self, rel: str, transform: Callable[[bytes], bytes]) -> None:
        path = self.path(rel)
        path.write_bytes(transform(path.read_bytes()))


@pytest.fixture
def make_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., _Package]]:
    monkeypatch.syspath_prepend(str(tmp_path))
    created: list[str] = []

    def make(calc_src: str = _CALC) -> _Package:
        name = f"hashpkg{len(created)}"
        created.append(name)
        return _Package(tmp_path, name, calc_src)

    yield make
    for name in list(sys.modules):
        if any(name == c or name.startswith(c + ".") for c in created):
            del sys.modules[name]


def test_hash_covers_helpers_and_metadata(
    make_package: Callable[..., _Package], monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg = make_package()
    base = pkg.hash()
    assert len(base) == 64
    assert pkg.hash() == base

    # The modules object: the calc module and every helper, transitively, including typing-only and lazy imports.
    modules = module_hashes(pkg.module.__name__, package=pkg.name)
    assert modules.keys() == {
        pkg.name,
        f"{pkg.name}.calcs.c",
        f"{pkg.name}.helpers",
        f"{pkg.name}.deep",
        f"{pkg.name}.typing_only",
        f"{pkg.name}.late",
    }
    assert modules[f"{pkg.name}.deep"] == _digest("def twice(x: float) -> float:\n    return x * 2\n")

    # One byte in the calc module, a direct helper, a transitive helper, a typing-only and a lazily imported module.
    for rel in ("calcs/c.py", "helpers.py", "deep.py", "typing_only.py", "late.py"):
        original = pkg.path(rel).read_bytes()
        pkg.edit(rel, _append_hash_mark)
        assert pkg.hash() != base, rel
        pkg.path(rel).write_bytes(original)
        assert pkg.hash() == base, rel

    # A module the calc does not import is not hashed.
    pkg.edit("unrelated.py", _append_hash_mark)
    assert pkg.hash() == base

    # Line endings do not matter (CRLF and CR to LF).
    for ending in (b"\r\n", b"\r"):
        pkg.edit("deep.py", _with_endings(ending))
        assert pkg.path("deep.py").read_bytes().count(ending) == 2
        assert pkg.hash() == base
    pkg.edit("deep.py", _lf)

    definition = pkg.definition
    changes: list[dict[str, Any]] = [
        {"title": "other"},
        {"method_source": "other"},
        {"verification": "verified"},
        {"version": 2},
    ]
    for change in changes:
        assert pkg.hash(dataclasses.replace(definition, **change)) != base, change

    wider_in = create_model("WiderIn", __base__=pkg.module.In, y=(int, 0))
    assert pkg.hash(dataclasses.replace(definition, input_type=wider_in)) != base

    class Out(BaseModel):
        value: float
        extra: int = 0

    assert pkg.hash(kinds=NEUTRAL_KINDS.extend({KIND: Out})) != base

    monkeypatch.setattr(eng_contract, "__version__", "9.9.9")
    assert pkg.hash() != base


def test_framework_modules_are_in_the_default_closure() -> None:
    modules = module_hashes("eng_harness.calc")
    assert {"eng_harness.calc", "eng_harness.errors"} <= modules.keys()
    assert all(name.split(".")[0] == "eng_harness" for name in modules)


@pytest.mark.parametrize("variant", sorted(_DYNAMIC))
def test_unhashable_calc_refused(make_package: Callable[..., _Package], variant: str) -> None:
    pkg = make_package(_CALC + "\n" + _DYNAMIC[variant])
    with pytest.raises(CalcRegistryError) as caught:
        pkg.hash()
    assert caught.value.rule == "hash"
    with pytest.raises(CalcRegistryError) as registered:
        CalcRegistry(pkg.kinds, [pkg.definition])
    assert registered.value.rule == "hash"


def test_unhashable_helper_under_calcs_refused(make_package: Callable[..., _Package]) -> None:
    pkg = make_package()
    pkg.path("calcs/helper.py").write_text(_DYNAMIC["function_import"], encoding="utf-8")
    pkg.edit("calcs/c.py", lambda data: data.replace(b"from typing", b"from .helper import load\nfrom typing", 1))
    with pytest.raises(CalcRegistryError) as caught:
        pkg.hash()
    assert caught.value.rule == "hash"


def test_source_not_available_refused(make_package: Callable[..., _Package]) -> None:
    helper_gone = make_package()
    helper_gone.path("deep.py").unlink()
    with pytest.raises(CalcRegistryError) as first:
        helper_gone.hash()
    assert first.value.rule == "hash"

    calc_gone = make_package()
    calc_gone.path("calcs/c.py").unlink()
    with pytest.raises(CalcRegistryError) as second:
        calc_gone.hash()
    assert second.value.rule == "hash"


def test_calc_module_must_be_a_loaded_module() -> None:
    with pytest.raises(CalcRegistryError) as caught:
        module_hashes("eng_harness.no_such_module")
    assert caught.value.rule == "hash"
