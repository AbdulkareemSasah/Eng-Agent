"""Label store, pending store, override and opt-in export (plan 0005 T6; spec 0005 AC35 to AC39, AC44, section 4.11)."""

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from pydantic import JsonValue

from eng_harness.decisions import (
    LabeledExample,
    LabelStore,
    OverriddenDecision,
    StoreWriteError,
)
from eng_harness.decisions._policy import DecisionSettings
from eng_harness.decisions._record import (
    DecisionScreen,
    ProviderOption,
    ScreenField,
    ScreenItem,
    Suggestion,
)
from eng_harness.decisions._redaction import check_state

START_MS = 1_767_225_600_000  # 2026-01-01T00:00:00.000Z
_STATE: dict[str, JsonValue] = {"cover_mm": 50, "action": "enlarge"}
_RES = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"


def _make(
    root: Path, *, export: bool = False, connect: Callable[[str], sqlite3.Connection] | None = None
) -> LabelStore:
    clock = FixedClock(START_MS, 1)
    settings = DecisionSettings(export_enabled=export)
    ids = SeededIdSource(b"labels", clock)
    if connect is None:
        return LabelStore(root, settings, clock, ids)
    return LabelStore(root, settings, clock, ids, connect=connect)


@pytest.fixture
def store(tmp_path: Path) -> LabelStore:
    return _make(tmp_path)


def _suggestion() -> Suggestion:
    return Suggestion(tier=1, by="rule:r1", outcome="accepted", choice="enlarge", latency_ms=0, shadow=False)


def _example(
    request_id: str = "req_1",
    *,
    point: str = "footing_fix",
    state: dict[str, JsonValue] | None = None,
    choice: str = "enlarge",
) -> LabeledExample:
    state = _STATE if state is None else state
    return LabeledExample(
        label_id=f"lbl_{request_id}",
        request_id=request_id,
        point=point,
        point_version=1,
        run_id="run_1",
        step_path="/a/b",
        options=("enlarge", "rebar"),
        state=state,
        state_sha256=payload_sha256(state),
        label=choice,
        engineer="Engineer One",
        suggestions=(_suggestion(),),
        source="engineer_decision",
        created_at="2026-01-01T00:00:00.000Z",
    )


def _screen(request_id: str = "req_1") -> DecisionScreen:
    item = ScreenItem(
        request_id=request_id,
        title="Footing fix",
        options=(ProviderOption(value="enlarge", label="Enlarge"), ProviderOption(value="rebar", label="Rebar")),
        fields=(ScreenField(label="Cover", value=50), ScreenField(label="Section", ref=_RES)),
        suggestions=(_suggestion(),),
    )
    return DecisionScreen(items=(item,))


def test_append_only(store: LabelStore, tmp_path: Path) -> None:
    store.append(_example("req_1"), ())
    [row] = store.read("footing_fix", 1)
    assert row.request_id == "req_1" and row.state == _STATE and row.suggestions == (_suggestion(),)
    assert row.state_sha256 == payload_sha256(_STATE)
    # a second insert with the same request_id is ignored, the first row stays
    store.append(_example("req_1", choice="rebar"), ())
    assert [r.label for r in store.read("footing_fix", 1)] == ["enlarge"]
    # UPDATE and DELETE fail at the database
    conn = sqlite3.connect(tmp_path / "decisions" / "decisions.sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE labels SET label = 'rebar'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM labels")
    conn.close()
    assert [r.label for r in store.read("footing_fix", 1)] == ["enlarge"]
    # other points and versions are not mixed in
    assert store.read("other_point", 1) == ()
    assert store.read("footing_fix", 2) == ()


def test_unredactable_state_hash_only(store: LabelStore) -> None:
    state: dict[str, JsonValue] = {"note": "see the Zeta Tower drawings", "cover_mm": 50}
    # the value is supplied only as a call's sensitive value: it is absent from the store's settings
    findings = check_state(state, ["zeta tower"])
    assert findings
    store.append(_example("req_2", state=state), findings)
    store.append(_example("req_3", state=_STATE), check_state(_STATE, ["zeta tower"]))
    rows = {r.request_id: r for r in store.read("footing_fix", 1)}
    assert rows["req_2"].state is None and rows["req_2"].state_sha256 == payload_sha256(state)
    assert rows["req_3"].state == _STATE


class _Flaky:
    """A connection whose INSERTs fail while ``armed``; everything else delegates."""

    def __init__(self, inner: sqlite3.Connection) -> None:
        self._inner = inner
        self.armed = False

    def execute(self, sql: str, *args: Any) -> sqlite3.Cursor:
        if self.armed and sql.lstrip().upper().startswith("INSERT"):
            raise sqlite3.OperationalError("disk I/O error")
        return self._inner.execute(sql, *args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def test_write_failure_is_loud(tmp_path: Path) -> None:
    made: list[_Flaky] = []

    def connect(path: str) -> sqlite3.Connection:
        flaky = _Flaky(sqlite3.connect(path, isolation_level=None))
        made.append(flaky)
        return flaky  # type: ignore[return-value]  # B-170: test double that delegates to a real connection

    store = _make(tmp_path, connect=connect)
    store.open_pending("req_9", "batch_1", _screen("req_9"), {})
    made[0].armed = True
    with pytest.raises(StoreWriteError) as caught:
        store.append(_example("req_9"), ())
    assert isinstance(caught.value, ContractError)
    assert caught.value.detail.code is ErrorCode.INTERNAL and caught.value.detail.incident_id
    made[0].armed = False
    pending = store.get_pending("req_9")
    assert pending is not None and pending.closed_at is None  # the request stays presented
    assert store.read("footing_fix", 1) == ()  # nothing half written


def test_override_label(store: LabelStore) -> None:
    decided = OverriddenDecision(
        point="footing_fix",
        point_version=1,
        run_id="run_1",
        step_path="/a/b",
        options=("enlarge", "rebar"),
        state_sha256=payload_sha256(_STATE),
    )
    store.record_override("req_5", "rebar", "Engineer Two", overridden=decided)
    [row] = store.read("footing_fix", 1)
    assert row.source == "engineer_override" and row.label == "rebar" and row.engineer == "Engineer Two"
    assert row.state is None and row.state_sha256 == payload_sha256(_STATE)  # always hash-only
    # a request the caller cannot resolve is NOT_FOUND
    with pytest.raises(ContractError) as unknown:
        store.record_override("req_404", "rebar", "Engineer Two")
    assert unknown.value.detail.code is ErrorCode.NOT_FOUND
    # a choice that is not an option is refused
    with pytest.raises(ContractError) as bad:
        store.record_override("req_6", "demolish", "Engineer Two", overridden=decided)
    assert bad.value.detail.code is ErrorCode.INVALID_ARGUMENT and bad.value.detail.field == "new_choice"


def test_export_is_opt_in(tmp_path: Path) -> None:
    closed = _make(tmp_path / "closed")
    closed.append(_example("req_1"), ())
    folder = tmp_path / "evals"
    with pytest.raises(ContractError) as refused:
        closed.export_labels("footing_fix", folder)
    assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT and refused.value.detail.field == "export_enabled"
    assert not folder.exists()

    opened = _make(tmp_path / "open", export=True)
    hashed: dict[str, JsonValue] = {"note": "Zeta Tower", "cover_mm": 40}
    opened.append(_example("req_1"), ())
    opened.append(_example("req_2", state=hashed), check_state(hashed, ["zeta tower"]))
    opened.append(_example("req_3", point="other_point"), ())
    out = opened.export_labels("footing_fix", folder)
    text = out.read_text(encoding="utf-8")
    lines = [json.loads(line) for line in text.splitlines()]
    assert len(lines) == 2
    for line in lines:
        assert not {"engineer", "run_id", "step_path"} & set(line)
        assert line["point"] == "footing_fix" and line["source"] == "engineer_decision"
    assert [line["state"] for line in lines] == [_STATE, None]
    assert "Zeta" not in text and "Engineer One" not in text


def test_pending_round_trip(store: LabelStore) -> None:
    outcomes: dict[str, JsonValue] = {"req_2": {"choice": "rebar", "by": "rule:r2"}, "req_3": None}
    screen = _screen()
    assert store.get_pending("req_1") is None
    store.open_pending("req_1", "batch_7", screen, outcomes)
    first = store.get_pending("req_1")
    assert first is not None
    assert first.screen == screen and first.batch_id == "batch_7" and first.outcomes == outcomes
    assert first.closed_at is None and first.created_at.endswith("Z")
    # a second open keeps the first row
    store.open_pending("req_1", "batch_8", _screen("req_other"), {})
    assert store.get_pending("req_1") == first
    # close changes only closed_at, and only once
    store.close_pending("req_1", "2026-01-02T00:00:00.000Z")
    closed = store.get_pending("req_1")
    assert closed is not None and closed.closed_at == "2026-01-02T00:00:00.000Z"
    assert closed.model_copy(update={"closed_at": None}) == first
    store.close_pending("req_1", "2026-01-03T00:00:00.000Z")
    again = store.get_pending("req_1")
    assert again is not None and again.closed_at == "2026-01-02T00:00:00.000Z"
    with pytest.raises(ContractError) as unknown:
        store.close_pending("req_404", "2026-01-02T00:00:00.000Z")
    assert unknown.value.detail.code is ErrorCode.NOT_FOUND
    # a single decide has no batch
    store.open_pending("req_solo", None, _screen("req_solo"), {})
    solo = store.get_pending("req_solo")
    assert solo is not None and solo.batch_id is None and solo.outcomes == {}
