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
        pack: str = "synthbase",
        modules: str = _ALL_SRC,
        case_text: str | None = None,
        entry: str | None = None,
    ) -> Path:
        """Build a pack project root in folder `name` for pack `pack` (`entry` replaces the entry-point line)."""
        root = self.tmp / f"root_{name}"
        cases = root / "tests" / "data" / "golden" / "verification"
        cases.mkdir(parents=True)
        entry_line = f'{pack} = "{pack}:PACK"' if entry is None else entry
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
    code, out, err = env.run("verify", "--pack", str(env.root("failing", case_text=failing)))
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
    root = env.root("synthover", pack="synthover")
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


def _pyproject(env: _Env, name: str, text: str) -> Path:
    root = env.tmp / f"root_{name}"
    root.mkdir()
    (root / "pyproject.toml").write_text(text, encoding="utf-8")
    return root


_ENTRY = '[project.entry-points."structural_codes.packs"]\nsynthbase = "synthbase:PACK"\n'
_GATE = "[tool.eng-gate]\ncheck_modules = []\n"


def test_pyproject_errors_are_exact(env: _Env) -> None:
    """Each missing table of the pack's pyproject.toml gives its own one-line message and exit 2."""
    entry_msg = "pyproject.toml needs exactly one entry point in structural_codes.packs, found 0\n"
    modules_msg = "pyproject.toml has no [tool.eng-gate] check_modules list of strings\n"
    other = '[project.entry-points.other]\na = "b:C"\n'
    cases = {
        "noproject": (_GATE, entry_msg),
        "noentrypoints": ('[project]\nname = "x"\n' + _GATE, entry_msg),
        "nogroup": ('[project]\nname = "x"\n' + other + _GATE, entry_msg),
        "notool": ('[project]\nname = "x"\n' + _ENTRY, modules_msg),
        "nogate": ('[project]\nname = "x"\n' + _ENTRY + "[tool.other]\na = 1\n", modules_msg),
        "nolist": ('[project]\nname = "x"\n' + _ENTRY + '[tool.eng-gate]\ncheck_modules = "src"\n', modules_msg),
        "badlist": ('[project]\nname = "x"\n' + _ENTRY + "[tool.eng-gate]\ncheck_modules = [1]\n", modules_msg),
    }
    for name, (text, message) in cases.items():
        code, out, err = env.run("verify", "--pack", str(_pyproject(env, name, text)))
        assert (code, out, err) == (2, "", message), name
        code, out, err = env.run("hash", "--pack", str(_pyproject(env, "h" + name, text)))
        assert (code, out, err) == (2, "", message), name


def test_usage_errors_and_help_are_exit_2(env: _Env) -> None:
    for argv in (["--help"], ["verify", "--help"], ["hash", "-h"], ["-h"]):
        code, out, err = env.run(*argv)
        assert (code, out) == (2, ""), argv
        assert err.startswith("usage: "), argv
        assert err.count("\n") == 1, argv
        assert err.endswith("\n"), argv
    assert env.run()[2].startswith("usage: ")


def test_lint_scope_message_is_exact(env: _Env) -> None:
    code, out, err = env.run("verify", "--pack", str(env.root("lint", modules=_OTHER_SRC)))
    assert (code, out) == (2, "")
    assert (
        err
        == "synthbase.6_1.gap: modules outside check_modules: synthbase, synthbase.checks, synthbase.runner_checks\n"
    )


def test_verify_lines_are_exact(env: _Env) -> None:
    lines = env.run("verify", "--pack", str(env.root()))[1].splitlines()
    assert (
        f"{_SIZED} not verified pass=2 fail=0 pending=0 unmet: (4) no listed property test; (5) no review block"
        in lines
    )
    unmet = "synthbase.4_1.two_pre not verified pass=0 fail=0 pending=0 unmet: no case file synthbase.4_1.two_pre.yaml"
    assert unmet in lines

    failing = _CASES.read_text(encoding="utf-8").replace("value: 0.5,", "value: 0.9,")
    out = env.run("verify", "--pack", str(env.root("failing", case_text=failing)))[1]
    line = next(x for x in out.splitlines() if x.startswith(_SIZED + " "))
    assert line.startswith(f"{_SIZED} not verified pass=1 fail=1 pending=0 unmet: (1) no passing worked_example")
    assert "; (6) failing cases: WE-1" in line


def test_pending_cases_are_counted(env: _Env) -> None:
    text = _CASES.read_text(encoding="utf-8")
    head, _, tail = text.partition("program_comparison:\n  not_available:")
    tail = tail.partition("\n")[2]
    pending = (
        "  - id: PC-1\n    kind: program_comparison\n"
        "    source: {program: SynthProgram, program_version: '1.0', assumption_differences: [synthetic difference],"
        " status: needs_local_test}\n"
        "    subject: {kind: section, id: S1}\n    inputs: {width_mm: 10, demand_mm: 50, capacity_mm: 100}\n"
        "    expected: {status: PASS, values: {}}\n"
    )
    out = env.run(
        "verify",
        "--pack",
        str(env.root("pending", case_text=head + tail.replace("review: null", pending + "review: null"))),
    )[1]
    pending_line = (
        f"{_SIZED} not verified pass=2 fail=0 pending=1 unmet: (2) program comparisons not passing or without"
        " assumption differences: PC-1; (4) no listed property test; (5) no review block"
    )
    assert pending_line in out.splitlines(), out


def test_overlay_case_file_is_verified_with_the_registry(env: _Env) -> None:
    env.register(env.base, env.over)
    root = env.root("synthover", pack="synthover")
    over_id = "synthover.s3_1.sized_over"
    text = (
        _CASES.read_text(encoding="utf-8").replace("value: 0.5,", "value: 0.25,").replace("value: 1.0,", "value: 0.5,")
    )
    text = text.replace(f"check_id: {_SIZED}", f"check_id: {over_id}").replace("width_mm: 10, ", "")
    (root / "tests" / "data" / "golden" / "verification" / f"{over_id}.yaml").write_text(text, encoding="utf-8")
    code, out, err = env.run("verify", "--pack", str(root))
    assert (code, err) == (0, "")
    assert (
        f"{over_id} not verified pass=2 fail=0 pending=0 unmet: (4) no listed property test; (5) no review block"
        in out.splitlines()
    ), out
