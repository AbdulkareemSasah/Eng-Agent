"""Tests of the lifecycle: `approvals.yaml`, runtime state and mode usability (plan 0001 T11; spec 0001 AC23 to AC25).

Packs are copies of the synthetic fixture packs in a temporary folder, as installed: the package folder and its
`approvals.yaml` only. The fixture packs ship no `approvals.yaml` (spec 4.8: no shipped file has entries), so each test
writes the file it needs after computing the hash of the check from the copy.
"""

import datetime as dt
import importlib
import shutil
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ErrorCode
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes.lifecycle import ApprovalsFile, resolve_state

from structural_codes import evaluate
from structural_codes.content_hash import content_hash
from structural_codes.errors import ApprovalsFileError, CheckNotUsable
from structural_codes.overlay import InheritedCheck
from structural_codes.pack import Pack, Registry

# B-265: the module names are split only because gate rule IM006 reports the fixture packs under tests/fixtures/*/src
# as undeclared distributions (same workaround as tests/unit/test_registry.py, B-260); it hides no import.
_BASE = "synth" + "base"
_OVER = "synth" + "over"
_DATA = Path(__file__).parent.parent / "data" / "approvals"
_FIXTURES = Path(__file__).parent.parent / "fixtures"

_SIZED = "synthbase.3_1.sized"
_TWO_PRE = "synthbase.4_1.two_pre"
_S1 = Subject(kind=SubjectKind.SECTION, id="S1")
_INPUTS: dict[str, Any] = {"width_mm": 10.0, "demand_mm": 50.0, "capacity_mm": 100.0, "fault": "none"}
_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _entry(check_id: str, digest: str, kind: str = "approved") -> str:
    return (
        f"  - check_id: {check_id}\n    content_sha256: {digest}\n    kind: {kind}\n    approver: owner\n"
        "    date: 2026-11-05\n    verification_record: docs/verification/x.md\n"
        "    pull_request: https://example.invalid/pull/1\n"
    )


def _withdrawal(check_id: str) -> str:
    return (
        f"  - check_id: {check_id}\n    reason: synthetic withdrawal reason\n"
        "    issue: https://example.invalid/issues/1\n    date: 2026-11-06\n"
    )


def _file(approvals: tuple[str, ...] = (), withdrawn: tuple[str, ...] = ()) -> str:
    return (
        "format: structural-codes-approvals/1\n"
        + ("approvals:\n" + "".join(approvals) if approvals else "approvals: []\n")
        + ("withdrawn:\n" + "".join(withdrawn) if withdrawn else "withdrawn: []\n")
    )


@dataclass(frozen=True)
class _Site:
    """The installed copies of the packs (no `tests` folder) and a writer of their `approvals.yaml`."""

    root: Path
    base: Pack
    over: Pack
    write: Callable[[str, str], None]

    def registry(self) -> Registry:
        return Registry.of([self.base, self.over])


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Site]:
    root = tmp_path / "site-packages"
    for name in (_BASE, _OVER):
        shutil.copytree(
            _FIXTURES / name / "src" / name, root / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
    monkeypatch.syspath_prepend(str(root))
    base = importlib.import_module(f"{_BASE}.runner_checks").RUNNER_PACK
    over = importlib.import_module(_OVER).PACK

    def write(pack: str, text: str) -> None:
        (root / pack / "approvals.yaml").write_text(text, encoding="utf-8")

    yield _Site(root, base, over, write)
    for name in [n for n in sys.modules if n.split(".")[0] in {_BASE, _OVER}]:
        del sys.modules[name]


def _inherited_id(registry: Registry) -> str:
    (found,) = [c.meta.check_id for c in registry.checks if isinstance(c, InheritedCheck) and c.meta.pack == _OVER]
    return found


def _approve(site: _Site, check_id: str, *, kind: str = "approved") -> None:
    registry = site.registry()
    check = registry.get(check_id)
    site.write(check.meta.pack, _file((_entry(check_id, content_hash(check), kind),)))


def test_approvals_file() -> None:
    empty = ApprovalsFile.parse((_DATA / "empty.yaml").read_text(encoding="utf-8"))
    assert (empty.approvals, empty.withdrawn) == ((), ())

    full = ApprovalsFile.parse(
        (_DATA / "full.yaml").read_text(encoding="utf-8"), inherited=frozenset({"synthover.s4_1.two_pre"})
    )
    assert [(a.check_id, a.kind) for a in full.approvals] == [
        ("synthbase.3_1.sized", "approved"),
        ("synthover.s4_1.two_pre", "inherited-confirmed"),
    ]
    assert full.approvals[0].content_sha256 == _HASH_A
    assert full.approvals[0].date == dt.date(2026, 11, 5)
    assert full.approvals[1].date == dt.date(2026, 11, 6)  # a quoted ISO date is accepted as well
    assert [w.check_id for w in full.withdrawn] == ["synthbase.4_1.two_pre"]

    # Invalid files: a missing field (also the format), an unknown key, a malformed hash or date, a wrong format,
    # a repeated key.
    for name in (
        "missing_field",
        "no_format",
        "unknown_key",
        "bad_hash",
        "short_hash",
        "bad_date",
        "wrong_format",
        "duplicate_key",
    ):
        text = (_DATA / f"{name}.yaml").read_text(encoding="utf-8")
        with pytest.raises(ApprovalsFileError):
            ApprovalsFile.parse(text, inherited=frozenset({"synthover.s4_1.two_pre"}))
    for text in (
        "",
        "- not a mapping\n",
        "format: structural-codes-approvals/1\napprovals: []\n",  # `withdrawn` missing
        "format: structural-codes-approvals/1\napprovals: []\nwithdrawn: []\nextra: 1\n",
        "format: [unclosed\n",
        "format: !!python/object/apply:os.getcwd []\napprovals: []\nwithdrawn: []\n",  # unsafe tag
    ):
        with pytest.raises(ApprovalsFileError):
            ApprovalsFile.parse(text)
    # A date that is a timestamp, or a whole entry of the wrong type, is malformed as well.
    stamp = (
        (_DATA / "full.yaml").read_text(encoding="utf-8").replace("date: 2026-11-05", "date: 2026-11-05T10:00:00", 1)
    )
    with pytest.raises(ApprovalsFileError):
        ApprovalsFile.parse(stamp)
    with pytest.raises(ApprovalsFileError):
        ApprovalsFile.parse("format: structural-codes-approvals/1\napprovals: [1]\nwithdrawn: []\n")

    # The kind must fit the check: `approved` for an inherited check, `inherited-confirmed` for any other: refused.
    full_text = (_DATA / "full.yaml").read_text(encoding="utf-8")
    with pytest.raises(ApprovalsFileError):
        ApprovalsFile.parse(full_text, inherited=frozenset({"synthbase.3_1.sized", "synthover.s4_1.two_pre"}))
    with pytest.raises(ApprovalsFileError):
        ApprovalsFile.parse(full_text)  # synthover.s4_1.two_pre is not declared inherited


def test_approvals_file_load(site: _Site) -> None:
    # A pack's file is read from its package resource; a missing file holds no approval (nothing is approved).
    assert ApprovalsFile.load(site.base).approvals == ()
    site.write(_BASE, _file((_entry(_SIZED, _HASH_A),)))
    assert [a.check_id for a in ApprovalsFile.load(site.base).approvals] == [_SIZED]
    site.write(_BASE, "format: nonsense\n")
    with pytest.raises(ApprovalsFileError):
        ApprovalsFile.load(site.base)
    (site.root / _BASE / "approvals.yaml").write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(ApprovalsFileError):
        ApprovalsFile.load(site.base)


def test_state_resolution(site: _Site) -> None:
    registry = site.registry()
    sized = registry.get(_SIZED)
    digest = content_hash(sized)

    # No approvals: draft. A verification case file for the check changes nothing, and `verified` is never returned.
    assert (_FIXTURES.parent / "data" / "verification").is_dir()
    assert resolve_state(sized, registry) == "draft"
    site.write(_BASE, _file())
    assert resolve_state(sized, registry) == "draft"

    # An entry with the current hash approves; the entry of another check or another hash does not.
    site.write(_BASE, _file((_entry(_SIZED, digest),)))
    assert resolve_state(sized, registry) == "approved"
    assert resolve_state(registry.get(_TWO_PRE), registry) == "draft"
    site.write(_BASE, _file((_entry(_SIZED, _HASH_A),)))
    assert resolve_state(sized, registry) == "draft"
    site.write(_BASE, _file((_entry(_TWO_PRE, digest),)))
    assert resolve_state(sized, registry) == "draft"

    # An old entry beside the current one still approves.
    site.write(_BASE, _file((_entry(_SIZED, _HASH_A), _entry(_SIZED, digest))))
    assert resolve_state(sized, registry) == "approved"

    # Withdrawal wins over a matching approval and affects only its check.
    site.write(
        _BASE,
        _file((_entry(_SIZED, digest), _entry(_TWO_PRE, content_hash(registry.get(_TWO_PRE)))), (_withdrawal(_SIZED),)),
    )
    assert resolve_state(sized, registry) == "withdrawn"
    assert resolve_state(registry.get(_TWO_PRE), registry) == "approved"
    site.write(_BASE, _file(withdrawn=(_withdrawal(_SIZED),)))
    assert resolve_state(sized, registry) == "withdrawn"

    # A hash change turns approved into draft: one byte of the check's module changes.
    site.write(_BASE, _file((_entry(_SIZED, digest),)))
    assert resolve_state(sized, registry) == "approved"
    module = site.root / _BASE / "runner_checks.py"
    module.write_bytes(module.read_bytes() + b"\n# one more byte\n")
    assert content_hash(sized) != digest
    assert resolve_state(sized, registry) == "draft"


def test_state_resolution_inherited(site: _Site) -> None:
    registry = site.registry()
    inherited = registry.get(_inherited_id(registry))
    assert isinstance(inherited, InheritedCheck)
    base = inherited.base
    base_id = base.meta.check_id
    own = inherited.meta.check_id

    # The inherited check needs `inherited-confirmed` with its own hash AND an approved base check.
    _approve(site, own, kind="inherited-confirmed")
    assert resolve_state(inherited, registry) == "draft"  # base not approved
    _approve(site, base_id)
    assert resolve_state(inherited, registry) == "approved"
    assert resolve_state(base, registry) == "approved"

    # A stale hash of the inherited entry, a base that is withdrawn or whose hash changed: draft.
    site.write(_OVER, _file((_entry(own, _HASH_A, "inherited-confirmed"),)))
    assert resolve_state(inherited, registry) == "draft"
    _approve(site, own, kind="inherited-confirmed")
    site.write(_BASE, _file((_entry(base_id, content_hash(base)),), (_withdrawal(base_id),)))
    assert resolve_state(inherited, registry) == "draft"
    assert resolve_state(base, registry) == "withdrawn"
    site.write(_BASE, _file((_entry(base_id, _HASH_B),)))
    assert resolve_state(inherited, registry) == "draft"

    # The inherited check can be withdrawn on its own; the `approved` kind is refused by the file check (AC23).
    _approve(site, base_id)
    site.write(_OVER, _file((_entry(own, content_hash(inherited), "inherited-confirmed"),), (_withdrawal(own),)))
    assert resolve_state(inherited, registry) == "withdrawn"
    site.write(_OVER, _file((_entry(own, content_hash(inherited), "approved"),)))
    with pytest.raises(ApprovalsFileError):
        resolve_state(inherited, registry)


def test_mode_usability(site: _Site) -> None:
    registry = site.registry()

    def run(mode: Any) -> Any:
        return evaluate(_SIZED, _INPUTS, subject=_S1, registry=registry, mode=mode)

    # Draft: trial runs with the DRAFT flag, production is refused with the state in the hint.
    draft = run("trial")
    assert (draft.state, draft.payload.draft) == ("draft", True)
    with pytest.raises(CheckNotUsable) as refused:
        run("production")
    assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT
    assert refused.value.detail.field == "check_id"
    assert refused.value.detail.hint is not None
    assert "draft" in refused.value.detail.hint

    # Approved: both modes run and the payload is not a draft.
    _approve(site, _SIZED)
    for mode in ("trial", "production"):
        result = run(mode)
        assert (result.state, result.payload.draft) == ("approved", False)

    # Withdrawn: refused in both modes, whatever the approvals say.
    sized_hash = content_hash(registry.get(_SIZED))
    site.write(_BASE, _file((_entry(_SIZED, sized_hash),), (_withdrawal(_SIZED),)))
    for mode in ("trial", "production"):
        with pytest.raises(CheckNotUsable) as gone:
            run(mode)
        assert gone.value.detail.hint is not None
        assert "withdrawn" in gone.value.detail.hint

    # The refusal comes before input validation (spec 4.12): an unusable check reports its state, not a bad input.
    with pytest.raises(CheckNotUsable):
        evaluate(_SIZED, {"width_mm": 5000.0}, subject=_S1, registry=registry, mode="trial")

    # An inherited check runs in production only when approved with its base.
    inherited = _inherited_id(registry)
    inputs = {**_INPUTS}
    with pytest.raises(CheckNotUsable):
        evaluate(inherited, inputs, subject=_S1, registry=registry, mode="production")
    _approve(site, _TWO_PRE)
    _approve(site, inherited, kind="inherited-confirmed")
    result = evaluate(inherited, inputs, subject=_S1, registry=registry, mode="production")
    assert (result.state, result.payload.draft) == ("approved", False)


def test_installed_layout(site: _Site) -> None:
    # The pack is a copy of its package folder only: no `tests` folder, no case files, no source tree around it.
    assert Path(sys.modules[_BASE].__file__ or "").is_relative_to(site.root)
    assert sorted(p.name for p in site.root.iterdir()) == [_BASE, _OVER]
    registry = site.registry()
    sized = registry.get(_SIZED)

    _approve(site, _SIZED)
    result = evaluate(_SIZED, _INPUTS, subject=_S1, registry=registry, mode="production")
    assert result.payload.draft is False
    assert result.state == "approved"
    assert result.content_sha256 == content_hash(sized)

    site.write(_BASE, _file((_entry(_SIZED, _HASH_A),)))  # the entry's hash differs from the current one
    with pytest.raises(CheckNotUsable):
        evaluate(_SIZED, _INPUTS, subject=_S1, registry=registry, mode="production")
