"""Tests of packs and the registry (plan 0001 T6; spec 0001 AC16, section 4.6)."""

import importlib
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from eng_contract.errors import ContractError, ErrorCode

from structural_codes import pack as pack_module
from structural_codes.check import Check
from structural_codes.errors import CheckDefinitionError
from structural_codes.pack import ENTRY_POINT_GROUP, Pack, Registry

_PACK_MODULE = "synth" + "base"
_SRC = Path(__file__).parent.parent / "fixtures" / "synthbase" / "src"


@pytest.fixture
def synthbase(monkeypatch: pytest.MonkeyPatch) -> Iterator[Pack]:
    monkeypatch.syspath_prepend(str(_SRC))
    pack = importlib.import_module(_PACK_MODULE).PACK
    assert isinstance(pack, Pack)
    yield pack
    for name in [n for n in sys.modules if n == "synthbase" or n.startswith("synthbase.")]:
        del sys.modules[name]


@dataclass
class _EntryPoint:
    name: str
    value: Any

    def load(self) -> Any:
        return self.value


def _renamed(pack: Pack, name: str, checks: tuple[Check, ...] | None = None) -> Pack:
    return Pack(
        name=name,
        code=pack.code,
        edition=pack.edition,
        version=pack.version,
        checks=pack.checks if checks is None else checks,
        approvals=pack.approvals,
    )


def test_discovery_and_lookup(synthbase: Pack, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_entry_points(*, group: str) -> list[_EntryPoint]:
        seen.append(group)
        return [_EntryPoint("zz", _renamed(synthbase, "zz", ())), _EntryPoint("synthbase", synthbase)]

    monkeypatch.setattr(pack_module, "entry_points", fake_entry_points)
    registry = Registry.discover()
    assert seen == [ENTRY_POINT_GROUP] == ["structural_codes.packs"]
    assert [p.name for p in registry.packs] == ["synthbase", "zz"]
    assert [c.meta.check_id for c in registry.checks] == ["synthbase.1_1.plain", "synthbase.2_1.guarded"]
    assert registry.get("synthbase.2_1.guarded").meta.pack == "synthbase"
    with pytest.raises(ContractError) as unknown:
        registry.get("synthbase.9_9.nothing")
    assert unknown.value.detail.code == ErrorCode.NOT_FOUND
    assert unknown.value.detail.field == "check_id"


def test_sorted_regardless_of_input_order(synthbase: Pack) -> None:
    registry = Registry.of([synthbase, _renamed(synthbase, "aaa", ())])
    assert [p.name for p in registry.packs] == ["aaa", "synthbase"]


def test_duplicates_rejected(synthbase: Pack) -> None:
    with pytest.raises(CheckDefinitionError, match="duplicate pack"):
        Registry.of([synthbase, synthbase])
    twice = _renamed(synthbase, "synthbase", (synthbase.checks[0], synthbase.checks[0]))
    with pytest.raises(CheckDefinitionError, match="duplicate check_id"):
        Registry.of([twice])


def test_pack_rules(synthbase: Pack, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(CheckDefinitionError, match="belongs to pack"):
        _renamed(synthbase, "other")
    with pytest.raises(CheckDefinitionError, match="name"):
        _renamed(synthbase, "Bad-Name", ())
    monkeypatch.setattr(pack_module, "entry_points", lambda *, group: [_EntryPoint("x", object())])
    with pytest.raises(CheckDefinitionError, match="not a Pack"):
        Registry.discover()
