"""Decision points, state field rules, size limit and lock check (plan 0005 T2; spec 0005 AC1 to AC4, section 4.2)."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import pytest
from eng_contract.quantity import Quantity
from eng_contract.refs import Ref
from pydantic import BaseModel, ConfigDict, Field

from eng_harness.block import LockFinding
from eng_harness.decisions import _points
from eng_harness.decisions._points import (
    DecisionPoint,
    PointRegistry,
    Refs,
    check_lock,
    check_state_size,
    decision_point,
    discover,
    load_lock,
    main,
    write_lock,
)
from eng_harness.decisions._policy import DecisionSettings
from eng_harness.decisions.types import DecisionDefinitionError, Label
from eng_harness.errors import BlockRuleViolation

_STRICT = ConfigDict(frozen=True, extra="forbid")


class Action(StrEnum):
    ENLARGE = "enlarge"
    REBAR = "rebar"


class Mode(StrEnum):
    YES = "yes"
    NO = "no"


class State(BaseModel):
    model_config = _STRICT
    ratio: Annotated[float, Field(allow_inf_nan=False)]
    count: int


class RefState(BaseModel):
    model_config = _STRICT
    labels: tuple[Label, ...]


def _point(**over: Any) -> DecisionPoint:
    args: dict[str, Any] = {
        "name": "footing_fix",
        "version": 1,
        "title": "Footing fix",
        "options": Action,
        "state": State,
    }
    args.update(over)
    settings = args.pop("settings", None)
    if settings is None:
        return decision_point(**args)(type("Marker", (), {}))
    return decision_point(settings=settings, **args)(type("Marker", (), {}))


def test_definition_rules() -> None:
    point = _point()
    assert (point.name, point.version, point.title, point.options, point.state) == (
        "footing_fix",
        1,
        "Footing fix",
        Action,
        State,
    )
    assert point.yes_no is None
    assert len(point.schema_sha256) == 64
    assert _point(name="abc").name == "abc"
    assert _point(name="a" + "b_1" * 21).name == "a" + "b_1" * 21  # 64 characters
    assert _point(version=9999).version == 9999
    assert _point(options=Refs(labels_field="labels"), state=RefState).options == Refs(labels_field="labels")
    assert _point(options=Mode, yes_no=("yes", "no")).yes_no == ("yes", "no")

    class Empty(StrEnum):
        pass

    class Many(StrEnum):
        A = "a"
        B = "b"
        C = "c"

    class BadValue(StrEnum):
        A = "Upper"

    class Unfrozen(BaseModel):
        model_config = ConfigDict(extra="forbid")
        count: int

    class Lax(BaseModel):
        model_config = ConfigDict(frozen=True)
        count: int

    bad: list[tuple[dict[str, Any], str]] = [
        ({"name": "ab"}, "name"),
        ({"name": "Footing"}, "name"),
        ({"name": "1abc"}, "name"),
        ({"name": "a" * 65}, "name"),
        ({"name": "ab-c"}, "name"),
        ({"version": 0}, "version"),
        ({"version": 10000}, "version"),
        ({"version": True}, "version"),
        ({"version": "1"}, "version"),
        ({"options": Empty}, "options"),
        ({"options": Many, "settings": DecisionSettings(max_options=2)}, "options"),
        ({"options": BadValue}, "options"),
        ({"options": int}, "options"),
        ({"options": Refs(labels_field="missing"), "state": RefState}, "labels_field"),
        ({"options": Refs(labels_field="count")}, "labels_field"),
        ({"options": Many, "yes_no": ("a", "b")}, "yes_no"),
        ({"options": Mode, "yes_no": ("yes", "maybe")}, "yes_no"),
        ({"state": Unfrozen}, "state"),
        ({"state": Lax}, "state"),
        ({"state": dict}, "state"),
        ({"title": "a/b"}, "title"),
        ({"title": ""}, "title"),
    ]
    for over, rule in bad:
        with pytest.raises(DecisionDefinitionError, match=rule):
            _point(**over)


def test_registry_unique_names_and_immutable() -> None:
    first, second = _point(name="bbb"), _point(name="aaa")
    registry = PointRegistry([first, second])
    assert [p.name for p in registry.points] == ["aaa", "bbb"]
    assert registry.get("aaa") is second
    assert registry.get("zzz") is None
    bigger = registry.with_(_point(name="ccc"))
    assert len(registry.points) == 2
    assert [p.name for p in bigger.points] == ["aaa", "bbb", "ccc"]
    with pytest.raises(DecisionDefinitionError, match="duplicate"):
        PointRegistry([first, _point(name="bbb", version=2)])


def _state_with(annotation: Any) -> type[BaseModel]:
    class Holder(BaseModel):
        model_config = _STRICT
        field: annotation  # type: ignore[valid-type]  # B-166: dynamic annotation under test

    return Holder


def test_state_field_types() -> None:
    class Inner(BaseModel):
        model_config = _STRICT
        flag: bool

    class LooseInner(BaseModel):
        model_config = ConfigDict(extra="forbid")
        flag: bool

    allowed: list[Any] = [
        bool,
        int,
        Annotated[float, Field(allow_inf_nan=False)],
        Mode,
        Label,
        Quantity,
        Ref,
        tuple[int, ...],
        tuple[Label, ...],
        tuple[Quantity, ...],
        tuple[tuple[int, ...], ...],
        Inner,
        tuple[Inner, ...],
    ]
    for annotation in allowed:
        assert _point(state=_state_with(annotation)).state is not None

    refused: list[Any] = [
        str,
        bytes,
        Path,
        dict[str, int],
        Any,
        float,  # may be infinite or NaN
        list[int],
        set[int],
        int | None,
        tuple[str, ...],
        object,
        LooseInner,
        tuple[Any, ...],
    ]
    for annotation in refused:
        with pytest.raises(DecisionDefinitionError, match="field"):
            _point(state=_state_with(annotation))

    class Finite(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
        value: float

    assert _point(state=Finite).state is Finite


def test_state_size_limit() -> None:
    state = State(ratio=0.5, count=3)
    check_state_size("footing_fix", state, 4096)
    exact = len(b'{"count":3,"ratio":0.5}')
    check_state_size("footing_fix", state, exact)
    with pytest.raises(BlockRuleViolation, match="footing_fix"):
        check_state_size("footing_fix", state, exact - 1)

    class Many(BaseModel):
        model_config = _STRICT
        labels: tuple[Label, ...]

    big = Many(labels=tuple(f"label {i}" for i in range(2000)))
    with pytest.raises(BlockRuleViolation, match="max_state_bytes"):
        check_state_size("footing_fix", big, DecisionSettings().max_state_bytes)


def test_check_lock() -> None:
    point = _point()
    lock = [{"name": "footing_fix", "version": 1, "schema_sha256": point.schema_sha256}]
    registry = PointRegistry([point])
    assert check_lock(registry, lock) == ()

    class Changed(StrEnum):
        ENLARGE = "enlarge"
        REBAR = "rebar"
        SHIFT = "shift"

    same_version = _point(options=Changed)
    assert same_version.schema_sha256 != point.schema_sha256
    assert check_lock(PointRegistry([same_version]), lock) == (LockFinding("footing_fix", "VERSION_BUMP_REQUIRED"),)

    class State2(BaseModel):
        model_config = _STRICT
        count: int

    state_changed = _point(state=State2)
    assert [f.code for f in check_lock(PointRegistry([state_changed]), lock)] == ["VERSION_BUMP_REQUIRED"]
    # A new version, new points and removed points are stale, not a missing bump.
    assert check_lock(PointRegistry([_point(version=2)]), lock) == (LockFinding("footing_fix", "LOCK_STALE"),)
    assert check_lock(PointRegistry([point, _point(name="other")]), lock) == (LockFinding("other", "LOCK_STALE"),)
    assert check_lock(PointRegistry([]), lock) == (LockFinding("footing_fix", "LOCK_STALE"),)


def test_schema_hash_depends_only_on_options_and_state() -> None:
    assert _point().schema_sha256 == _point(title="Other title", version=3).schema_sha256
    assert _point().schema_sha256 != _point(options=Mode).schema_sha256
    assert _point(options=Refs(labels_field="labels"), state=RefState).schema_sha256 != _point().schema_sha256


def test_write_lock_roundtrip_and_refusal(tmp_path: Path) -> None:
    path = tmp_path / "decisions.lock.json"
    point = _point()
    write_lock(PointRegistry([point]), path)
    assert load_lock(path) == [{"name": "footing_fix", "version": 1, "schema_sha256": point.schema_sha256}]

    class Changed(StrEnum):
        ONLY = "only"

    with pytest.raises(DecisionDefinitionError, match="VERSION_BUMP_REQUIRED"):
        write_lock(PointRegistry([_point(options=Changed)]), path)
    assert load_lock(path)[0]["schema_sha256"] == point.schema_sha256  # unchanged on refusal
    write_lock(PointRegistry([_point(options=Changed, version=2)]), path)
    assert load_lock(path)[0]["version"] == 2

    path.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(DecisionDefinitionError, match="lock"):
        load_lock(path)


def test_main_requires_write_lock_flag_and_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "out.lock.json"
    monkeypatch.setattr(_points, "LOCK_PATH", target)
    assert main(["--write-lock"]) == 0
    assert load_lock(target) == []
    with pytest.raises(SystemExit):
        main([])


def test_discover_is_empty_without_workflows() -> None:
    assert discover().points == ()
