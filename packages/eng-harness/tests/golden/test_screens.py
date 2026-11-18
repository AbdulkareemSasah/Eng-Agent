"""The approval screens against the snapshots (plan 0006 T9; spec 0006 AC40, AC41)."""

import asyncio
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from eng_contract.canonical import payload_sha256
from eng_contract.envelope import Provenance
from eng_contract.refs import Ref
from helpers.engine_standin import SHA, EngineStandIn

from eng_harness._html import document
from eng_harness.ctx import Preview, PreviewItem
from eng_harness.journal import EventType, JournalReader
from eng_harness.pages import PageApprovalPort
from eng_harness.pages._css import STYLESHEET
from eng_harness.pages._screens_approval import approval_screens
from eng_harness.ports import ApprovalRequest, ModelBinding

SNAPSHOTS = Path(__file__).resolve().parents[1] / "data" / "snapshots" / "screens"
MODEL = "mdl_" + "0" * 26
PRODUCER = Provenance(tool="harness", tool_version="1", inputs={}, started_at="2026-01-01T00:00:00.000Z", duration_ms=0)
DIFF = Path(__file__).resolve().parents[1] / "data" / "kinds" / "calcs" / "model_diff.json"
BINDING = ModelBinding(model_key="m", model_id=MODEL, revision=3, fingerprint="fp-" + "1" * 20, file_sha256="c" * 64)


class Rig:
    """A stand-in engine (store and journal), the page ports with the T9 screens and a way to render a request."""

    def __init__(self, root: Path) -> None:
        self.engine = EngineStandIn(root)
        self.store = self.engine.store
        self.port = PageApprovalPort(builders=approval_screens(self.store, lambda: JournalReader(self.engine.run_dir)))

    def value(self, payload: Any) -> str:
        """Store `payload` as a value result and return its id."""
        return self.store.put("harness.run_input/1", {"value": payload}, PRODUCER).result_id

    def request(
        self, kind: str, items: list[PreviewItem], *, diff: str | None = None, shown: str | None = None
    ) -> ApprovalRequest:
        """Store a preview and build the request that quotes it (`shown` replaces the quoted hash)."""
        models = [{"model_key": "m", "model_id": MODEL, "revision": 3}]
        args = Preview.model_validate(
            {"items": items, "diff_ref": None if diff is None else Ref.model_validate({"$ref": diff}), "models": models}
        ).model_dump(mode="json", by_alias=True)
        stored = self.store.put("harness.approval_preview/1", args, PRODUCER)
        return ApprovalRequest(
            request_id="apr_one",
            run_id="run_standin",
            kind=kind,
            title="Apply <b>this</b>",
            preview_ref=stored.result_id,
            shown_sha256=shown or payload_sha256(args),
            binding=(BINDING,),
            items=tuple(i.id for i in items),
        )

    def render(self, request: ApprovalRequest) -> str:
        """The page of `request` as the browser gets it for the CSRF token `tok`."""
        asyncio.run(self.port.present(request))
        screen = self.port.hub.screen("request", request.request_id)
        assert screen is not None
        return document(screen.title, screen.render("tok"), STYLESHEET)


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Callable[[], Rig]]:
    made: list[Rig] = []

    def make() -> Rig:
        made.append(Rig(tmp_path / f"r{len(made)}"))
        return made[-1]

    yield make
    for each in made:
        each.engine.close()


def _snapshot(name: str, html: str) -> None:
    assert html == (SNAPSHOTS / name).read_text(encoding="utf-8")


def _item(item_id: str, label: str, *refs: str) -> PreviewItem:
    return PreviewItem(id=item_id, label=label, refs=tuple(Ref.model_validate({"$ref": r}) for r in refs))


def _change_set(rig: Rig) -> ApprovalRequest:
    diff = rig.store.put("harness.model_diff/1", json.loads(DIFF.read_text("utf-8")), PRODUCER)
    cover = rig.value({"value": 40, "unit": "mm"})
    note = rig.value("keep the <script>x</script> label")
    items = [
        _item("revision", "Save a new revision"),
        _item("i2", "Set the cover", cover + "#/value"),
        _item("i3", "Rename", note + "#/value"),
    ]
    return rig.request("change_set", items, diff=diff.result_id)


def test_change_set_screen(rig: Callable[[], Rig]) -> None:
    r = rig()
    html = r.render(_change_set(r))
    _snapshot("change_set.html", html)
    assert "<script>" not in html
    assert 'name="reject_i2"' in html
    assert 'name="reason_i2"' in html
    assert 'name="decision" value="approve"' in html
    assert 'name="decision" value="reject"' in html
    assert 'name="reason"' in html


def test_change_set_screen_refuses_a_damaged_preview(rig: Callable[[], Rig]) -> None:
    r = rig()
    html = r.render(r.request("change_set", [_item("i1", "x")], shown=SHA))
    assert "damaged" in html
    assert "<form" not in html
    assert "<button" not in html


def test_promotion_and_info_screens(rig: Callable[[], Rig]) -> None:
    r = rig()
    saved = {
        "model_key": "m",
        "model_id": MODEL,
        "revision": 1,
        "fingerprint": "f",
        "file_sha256": "d" * 64,
        "file_name": "work.edb",
        "role": "working_copy",
        "origin_sha256": "e" * 64,
        "origin_file_names": ["Plan.edb", "Plan.log"],
    }
    r.engine.journal(EventType.MODEL_SAVED, saved)
    promotion = r.render(r.request("promotion", [_item("m", "Plan.edb")]))
    _snapshot("promotion.html", promotion)
    assert "Plan.edb, Plan.log" in promotion
    info = r.render(r.request("info", [_item("t1", "Check the <i>units</i>")]))
    _snapshot("info.html", info)
    assert 'name="decision" value="approve"' in info
    assert "Acknowledge" in info


def test_promotion_without_a_saved_working_copy_shows_the_binding_only(rig: Callable[[], Rig]) -> None:
    r = rig()
    html = r.render(r.request("promotion", [_item("m", "Plan.edb")]))
    assert "No working copy is recorded" in html
    assert "c" * 12 in html


def test_the_builders_are_the_three_kinds_of_this_task(rig: Callable[[], Rig]) -> None:
    r = rig()
    assert set(approval_screens(r.store, lambda: JournalReader(r.engine.run_dir))) == {
        "change_set",
        "promotion",
        "info",
    }


@pytest.mark.parametrize("item_id", ["bad id", "has:colon", "x" * 58])
def test_change_set_with_an_id_that_is_no_field_name_is_a_refusal_screen(rig: Callable[[], Rig], item_id: str) -> None:
    r = rig()
    html = r.render(r.request("change_set", [_item(item_id, "x")]))
    assert "damaged" in html
    assert "<form" not in html
    ok = r.render(r.request("change_set", [_item("x" * 57, "x")]))  # the longest id a field name can take
    assert "<form" in ok
