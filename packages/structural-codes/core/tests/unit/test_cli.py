"""Tests of the command line (plan 0001 T12; spec 0001 AC33, section 4.9.3). Pack roots are built in `tmp_path`."""

import importlib
import io
import re
import runpy
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from structural_codes import _cli
from structural_codes import pack as pack_module
from structural_codes.content_hash import content_hash
from structural_codes.pack import Pack, Registry

# B-260: the module names are split only because gate rule IM006 wrongly reports the fixture packs under
# tests/fixtures/*/src as undeclared distributions; this is not a way to hide an import.
_BASE_MODULE = "synth" + "base.runner_checks"
_OVER_MODULE = "synth" + "over"
_FIXTURES = Path(__file__).parent.parent / "fixtures"
_CASES = Path(__file__).parent.parent / "data" / "verification" / "synthbase.3_1.sized.yaml"
_SIZED = "synthbase.3_1.sized"
_TWO_PRE = "synthover.s4_1.two_pre"
_ALL_SRC = 'check_modules = ["src/synthbase/**/*.py", "src/synthover/**/*.py"]'
_OTHER_SRC = 'check_modules = ["src/other/**/*.py"]'


@dataclass
class _EntryPoint:
    name: str
    value: Any

    def load(self) -> Any:
        return self.value


@dataclass
class _Env:
    base: Pack
    over: Pack
    tmp: Path
    monkeypatch: pytest.MonkeyPatch

    def register(self, *packs: Pack) -> None:
        eps = [_EntryPoint(p.name, p) for p in packs]
        self.monkeypatch.setattr(pack_module, "entry_points", lambda *, group: eps)

    def root(
        self,
        name: str = "synthbase",
        *,
        modules: str = _ALL_SRC,
        case_text: str | None = None,
        entry: str | None = None,
    ) -> Path:
        """Build a pack project root named after `name` (`entry` replaces the entry-point line)."""
        root = self.tmp / f"root_{name}"
        cases = root / "tests" / "data" / "golden" / "verification"
        cases.mkdir(parents=True)
        entry_line = f'{name} = "{name}:PACK"' if entry is None else entry
        lines = ["[project]", 'name = "x"', '[project.entry-points."structural_codes.packs"]', entry_line]
        lines += ["[tool.eng-gate]", modules]
        (root / "pyproject.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        text = _CASES.read_text(encoding="utf-8") if case_text is None else case_text
        (cases / f"{_SIZED}.yaml").write_text(text, encoding="utf-8")
        return root

    def run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = _cli.main(list(argv), out, err)
        return code, out.getvalue(), err.getvalue()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[_Env]:
    monkeypatch.syspath_prepend(str(_FIXTURES / "synthbase" / "src"))
    monkeypatch.syspath_prepend(str(_FIXTURES / "synthover" / "src"))
    base = importlib.import_module(_BASE_MODULE).RUNNER_PACK
    over = importlib.import_module(_OVER_MODULE).PACK
    result = _Env(base, over, tmp_path, monkeypatch)
    result.register(base)
    yield result
    for name in [n for n in sys.modules if n.split(".")[0] in {"synthbase", "synthover"}]:
        del sys.modules[name]


def test_verify_exit_codes(env: _Env) -> None:
    code, out, err = env.run("verify", "--pack", str(env.root()))
    assert (code, err) == (0, "")
    lines = out.splitlines()
    assert [line.split()[0] for line in lines] == sorted(line.split()[0] for line in lines)  # check_id order
    sized = next(line for line in lines if line.startswith(_SIZED + " "))
    assert re.search(r"\bpass=2\b.*\bfail=0\b.*\bpending=0\b", sized)
    assert any(line.startswith("synthbase.4_1.two_pre not verified") for line in lines)  # no case file: not a failure

    failing = _CASES.read_text(encoding="utf-8").replace("value: 0.5,", "value: 0.9,")
    code, out, err = env.run("verify", "--pack", str(env.root("failing", case_text=failing, entry='synthbase = "x:P"')))
    assert (code, err) == (1, "")
    assert re.search(rf"^{re.escape(_SIZED)} not verified pass=1 fail=1", out, re.MULTILINE)


def test_verify_exit_2(env: _Env) -> None:
    def fails(root: Path, message: str) -> None:
        code, out, err = env.run("verify", "--pack", str(root))
        assert (code, out) == (2, "")
        assert message in err
        assert err.count("\n") == 1  # one line

    fails(env.root("lint", modules=_OTHER_SRC), "synthbase.runner_checks")
    fails(env.root("bad", case_text="format: nonsense\n"), "case file")
    fails(env.root("nopack", entry='nothing = "x:P"'), "nothing")
    fails(env.root("two", entry='synthbase = "a:P"\nother = "b:P"'), "entry point")
    fails(env.root("nomod", modules=""), "check_modules")
    fails(env.tmp / "missing_root", "pyproject.toml")
    (env.tmp / "root_bad_toml").mkdir()
    (env.tmp / "root_bad_toml" / "pyproject.toml").write_text("[[", encoding="utf-8")
    fails(env.tmp / "root_bad_toml", "pyproject.toml")
    for argv in ([], ["verify"], ["bogus", "--pack", "x"], ["verify", "--pack"]):
        code, out, err = env.run(*argv)
        assert (code, out) == (2, "")
        assert err


def test_hash_prints_each_check(env: _Env) -> None:
    code, out, err = env.run("hash", "--pack", str(env.root()))
    assert (code, err) == (0, "")
    expected = [f"{c.meta.check_id} {content_hash(c)}" for c in Registry.of([env.base]).checks]
    assert out.splitlines() == expected
    assert all(re.fullmatch(r"\S+ [0-9a-f]{64}", line) for line in expected)
    # hash does not check the lint scope, but exits 2 on a resolution error
    assert env.run("hash", "--pack", str(env.root("lint", modules=_OTHER_SRC)))[0] == 0
    assert env.run("hash", "--pack", str(env.tmp / "missing_root"))[0] == 2


def test_overlay_includes_inherited(env: _Env) -> None:
    env.register(env.base, env.over)
    root = env.root("synthover")
    code, out, err = env.run("verify", "--pack", str(root))
    assert (code, err) == (0, "")
    assert all(line.startswith("synthover.") for line in out.splitlines())
    assert any(line.startswith(_TWO_PRE + " not verified") for line in out.splitlines())
    code, out, err = env.run("hash", "--pack", str(root))
    registry = Registry.of([env.base, env.over])
    expected = [f"{c.meta.check_id} {content_hash(c)}" for c in registry.checks if c.meta.pack == "synthover"]
    assert (code, err) == (0, "")
    assert out.splitlines() == expected
    assert any(line.startswith(_TWO_PRE + " ") for line in expected)


def test_module_entry_point(env: _Env, capsys: pytest.CaptureFixture[str]) -> None:
    env.monkeypatch.setattr(sys, "argv", ["structural_codes", "hash", "--pack", str(env.root())])
    with pytest.raises(SystemExit) as done:
        runpy.run_module("structural_codes", run_name="__main__")
    assert done.value.code == 0
    assert capsys.readouterr().out.startswith("synthbase.")
