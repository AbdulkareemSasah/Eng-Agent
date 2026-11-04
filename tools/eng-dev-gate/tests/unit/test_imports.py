"""Tests of the imports check (spec 4.10, AC42 to AC45) on toy workspaces in temporary repositories."""

from __future__ import annotations

import json
from pathlib import Path

from eng_dev_gate.checks.imports import check_workspace
from eng_dev_gate.report import Finding
from support.repo import Repo
from support.toy import GATE_YML

PROFILES = {1: "contract", 2: "server", 3: "codes", 4: "harness", "tool": "tool"}


def _member(
    name: str,
    layer: int | str,
    deps: list[str] | None = None,
    public: list[str] | None = None,
    sources: dict[str, str] | None = None,
    group: list[str] | None = None,
) -> dict[str, str]:
    """Files of a toy member ``pkgs/<name>`` whose import name is ``<name>`` with ``-`` replaced by ``_``."""
    module = name.replace("-", "_")
    shown = f'"{layer}"' if isinstance(layer, str) else str(layer)
    quote = json.dumps
    text = (
        f'[project]\nname = "{name}"\nversion = "0.1.0"\nrequires-python = ">=3.14"\n'
        f"dependencies = {quote(deps or [])}\n[dependency-groups]\ndev = {quote(group or [])}\n"
        f'[tool.eng-gate]\nprofile = "{PROFILES[layer]}"\nlayer = {shown}\nimport_names = ["{module}"]\n'
        f"public_modules = {quote([module] if public is None else public)}\ncoverage_line = 95\ncoverage_branch = 90\n"
    )
    files = {f"pkgs/{name}/pyproject.toml": text, f"pkgs/{name}/src/{module}/__init__.py": ""}
    for relative, source in (sources or {}).items():
        files[f"pkgs/{name}/{relative}"] = source
    return files


def _workspace(repo: Repo, *members: dict[str, str]) -> Path:
    names = sorted({k.split("/")[1] for m in members for k in m})
    listed = ", ".join(f'"pkgs/{n}"' for n in names)
    files = {
        "pyproject.toml": f'[project]\nname = "r"\nversion = "0"\n[tool.uv.workspace]\nmembers = [{listed}]\n',
        ".gate/gate.yml": GATE_YML,
    }
    for member in members:
        files.update(member)
    repo.commit(files)
    return repo.root


def _codes(findings: list[Finding]) -> list[tuple[str, str | None]]:
    return [(f.code, f.path) for f in findings]


def test_layers(repo: Repo) -> None:
    """AC42: IM001 for the same or a higher layer, except between declared layer 3 packages."""
    root = _workspace(
        repo,
        _member("p-low", 2, sources={"src/p_low/a.py": "import p_high\n"}),  # layer 2 imports 3: higher
        _member("p-high", 3),
        _member("p-same", 2, ["p-low"], sources={"src/p_same/a.py": "import p_low\n"}),  # same layer
        _member("p-ok", 4, ["p-high"], sources={"src/p_ok/a.py": "import p_high\n"}),  # lower layer: fine
        _member("p-one", 1, ["p-ok"], sources={"src/p_one/a.py": "import p_ok\n"}),  # layer 1 imports nothing
        _member("p-tool", "tool", ["p-ok"], sources={"src/p_tool/a.py": "import p_ok\n"}),  # a tool imports none
        _member("p-user", 4, ["p-tool"], sources={"tests/test_a.py": "import p_tool\n"}),  # nothing imports a tool
        _member("p-lib-a", 3, ["p-lib-b"], sources={"src/p_lib_a/a.py": "import p_lib_b\n"}),  # overlay: allowed
        _member("p-lib-b", 3),
        _member("p-lib-c", 3, sources={"src/p_lib_c/a.py": "import p_lib_b\n"}),  # layer 3, not declared
    )
    found = {(f.code, f.path) for f in check_workspace(root)}
    base = "pkgs/{}/{}"
    for member, path in [
        ("p-low", "src/p_low/a.py"), ("p-same", "src/p_same/a.py"), ("p-one", "src/p_one/a.py"),
        ("p-tool", "src/p_tool/a.py"), ("p-user", "tests/test_a.py"),
    ]:  # fmt: skip
        assert ("IM001", base.format(member, path)) in found
    assert ("IM001", base.format("p-ok", "src/p_ok/a.py")) not in found
    assert ("IM001", base.format("p-lib-a", "src/p_lib_a/a.py")) not in found
    assert ("IM001", base.format("p-lib-c", "src/p_lib_c/a.py")) in found  # IM001 needs the overlay declared
    assert ("IM003", base.format("p-lib-c", "src/p_lib_c/a.py")) in found


def test_public_modules(repo: Repo) -> None:
    """AC43: IM002 for a module outside public_modules; a submodule named by from-import counts; _x is never public."""
    lib = _member(
        "p-lib", 1, public=["p_lib", "p_lib.api", "p_lib._hidden"],
        sources={"src/p_lib/api.py": "", "src/p_lib/secret.py": "", "src/p_lib/_hidden.py": ""},
    )  # fmt: skip
    use = _member(
        "p-use", 2, ["p-lib"],
        sources={
            "src/p_use/ok.py": "import p_lib\nimport p_lib.api\nfrom p_lib import api\nfrom p_lib import name\n",
            "src/p_use/bad1.py": "import p_lib.secret\n",
            "src/p_use/bad2.py": "from p_lib import secret\n",
            "src/p_use/bad3.py": "from p_lib import _hidden\n",
            "src/p_use/bad4.py": "from p_lib.secret import thing\n",
        },
    )  # fmt: skip
    found = _codes(check_workspace(_workspace(repo, lib, use)))
    assert [p for c, p in found if c == "IM002"] == [f"pkgs/p-use/src/p_use/bad{n}.py" for n in (1, 2, 3, 4)]
    assert not [1 for _, p in found if p and p.endswith("ok.py")]


def test_declared_and_sasaah_and_third_party(repo: Repo) -> None:
    """AC44: IM003 undeclared workspace import, IM004 sasaah names, IM006 undeclared third-party distribution."""
    lib = _member("p-lib", 1)
    use = _member(
        "p-use", 2,
        sources={
            "src/p_use/undeclared.py": "import p_lib\n",
            "src/p_use/sasaah.py": "import Sasaah_Core\nimport sasaah.x\n",
            "src/p_use/third.py": "import os\nimport pydantic\nimport pytest\nimport p_use.sibling\nimport helper\n",
            "src/p_use/dynamic.py": "import importlib\nimportlib.import_module('p_lib')\n__import__('pydantic')\n",
            "src/p_use/relative.py": "from . import sibling\n",
            "tests/helper.py": "",
        },
        group=["pytest>=9"],
    )  # fmt: skip
    found = [(f.code, f.path, f.line) for f in check_workspace(_workspace(repo, lib, use))]
    src = "pkgs/p-use/src/p_use/"
    assert ("IM003", src + "undeclared.py", 1) in found
    assert [c for c, p, _ in found if p == src + "sasaah.py"] == ["IM004", "IM004"]
    assert [(c, n) for c, p, n in found if p == src + "third.py"] == [("IM006", 2)]  # pydantic only
    assert ("IM003", src + "dynamic.py", 2) in found
    assert ("IM006", src + "dynamic.py", 3) in found
    assert not [1 for _, p, _ in found if p == src + "relative.py"]


def test_cycle(repo: Repo) -> None:
    """AC45: IM005 for a cycle of declared dependencies between packages, once per cycle."""
    root = _workspace(
        repo,
        _member("p-a", 3, ["p-b"]), _member("p-b", 3, ["p-c"]), _member("p-c", 3, ["p-a"]),
        _member("p-d", 4, ["p-a"]),
    )  # fmt: skip
    findings = [f for f in check_workspace(root) if f.code == "IM005"]
    assert len(findings) == 1
    assert all(name in findings[0].message for name in ("p-a", "p-b", "p-c"))
    assert "p-d" not in findings[0].message


def test_command_reports_and_selects_packages(repo: Repo) -> None:
    """The command exits 1 on a finding, 0 on a clean package, and --package limits the report to that member."""
    _workspace(
        repo, _member("p-lib", 1),
        _member("p-bad", 2, sources={"src/p_bad/a.py": "import p_lib\n"}), _member("p-good", 2),
    )  # fmt: skip
    assert repo.run(["imports", "--all"]).code == 1
    assert repo.run(["imports", "--package", "p-good"]).code == 0
    done = repo.run(["--format", "json", "imports", "--package", "p-bad"])
    assert done.code == 1
    assert {f["code"] for s in json.loads(done.out)["steps"] for f in s["findings"]} == {"IM003"}
    assert repo.run(["imports", "--package", "nope"]).code == 2
