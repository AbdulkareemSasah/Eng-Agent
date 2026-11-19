"""Basis confirmation screen, setup log and step 3 of `run` (plan 0006 T15; spec 0006 AC47, 4.2.2, 4.4.7)."""

import contextlib
import json
import os
import re
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest
from eng_contract.cited import Cited
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from helpers.cli_deps import FakeInput, FakeOutput, Rig, client_for
from helpers.page_client import PageClient

from eng_harness._html import document
from eng_harness._kinds import HARNESS_KINDS
from eng_harness.basis import (
    BasisDraft,
    BasisSetupAnswer,
    BasisSetupView,
    DraftTemplate,
    DraftWarning,
    FieldSpec,
    SetupRow,
    SetupSection,
    build_draft,
    build_setup_view,
)
from eng_harness.block import Registry, workflow
from eng_harness.cli import ExitCode
from eng_harness.pages import PageApprovalPort, PageBasisSetupPort, PageServer
from eng_harness.pages._answers import REASON_MAX, AnswerError
from eng_harness.pages._css import STYLESHEET
from eng_harness.pages._screens_basis import CONFIRM, append_setup_log, basis_screen, parse_setup
from eng_harness.pages._security import CSRF_FIELD

_DRAFT_SHA = re.compile(r'<input type="hidden" name="draft_sha256" value="([0-9a-f]{64})">')
_SETUP_LINK = re.compile(r'href="(/setup/[0-9A-HJKMNP-TV-Z]{26})"')

BASIS_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        path="materials.concrete_fc_MPa",
        kind="quantity",
        label="Concrete fc",
        required=True,
        unit="MPa",
        min=Cited(value=20, unit="MPa", source="ACI 318-14 19.2.1"),
        max=Cited(value=80, unit="MPa", source="ACI 318-14 19.2.1"),
    ),
    FieldSpec(
        path="limits.ratio_limit_ratio",
        kind="quantity",
        label="Ratio limit",
        required=True,
        unit="1",
    ),
    FieldSpec(
        path="modeling.note",
        kind="text",
        label="Modeling note",
        required=False,
    ),
)

BASIS_FLOW = "basis_flow"


@workflow(
    name=BASIS_FLOW,
    version=1,
    description="A workflow that requires design basis confirmation.",
    basis_fields=BASIS_FIELDS,
)
async def basis_flow(ctx: Any, inp: FakeInput) -> FakeOutput:
    """The body is never run: the fake engine stands in."""
    return FakeOutput()


BASIS_REGISTRY = Registry([basis_flow])


def _basis_file(root: Path, *, note: str = "ملاحظة <b>x</b>") -> Path:
    path = root / "values.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "name: Engineer A\n"
        "values:\n"
        "  materials.concrete_fc_MPa:\n"
        "    value: 35\n"
        "    unit: MPa\n"
        "  limits.ratio_limit_ratio:\n"
        "    value: 0.95\n"
        '    unit: "1"\n'
        "  modeling.note:\n"
        f"    value: {json.dumps(note, ensure_ascii=False)}\n"
        "    unit: null\n"
    )
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _setup_path(client: Any) -> str:
    end = time.monotonic() + 10
    while time.monotonic() < end:
        found = _SETUP_LINK.search(client.get("/").body)
        if found is not None:
            return found.group(1)
        time.sleep(0.01)
    raise AssertionError("no setup link appeared on /")


def _threaded(action: Callable[[Any], None]) -> Callable[[str], bool]:
    def opener(address: str) -> bool:
        def run() -> None:
            with contextlib.suppress(Exception):
                client = client_for(address)
                client.open()
                action(client)

        threading.Thread(target=run, daemon=True).start()
        return True

    return opener


def test_basis_confirmation_flow(tmp_path: Path) -> None:
    basis_path = _basis_file(tmp_path)
    rig = Rig(tmp_path, keep_basis_ref=True)
    seen_pages: dict[str, str] = {}
    post_statuses: list[int] = []

    def interact(client: Any) -> None:
        setup_path = _setup_path(client)
        page = client.get(setup_path)
        seen_pages["setup"] = page.body
        draft_match = _DRAFT_SHA.search(page.body)
        assert draft_match is not None
        form = {
            CSRF_FIELD: client.token(setup_path),
            "draft_sha256": draft_match.group(1),
            "by": "Ada",
            "decision": "confirm",
            "confirm_materials": "on",
            "confirm_limits": "on",
            "confirm_modeling": "on",
        }
        post_statuses.append(client.post(setup_path, form).status)

    rig.open_with = _threaded(interact)
    code = rig.main(
        "run",
        BASIS_FLOW,
        "--template",
        "blank@0.1.0",
        "--basis",
        str(basis_path),
        "--progress",
        "off",
        workflow_registry=BASIS_REGISTRY,
        basis_fields_of=lambda w: w.basis_fields,
    )
    assert code == ExitCode.OK
    assert post_statuses == [HTTPStatus.OK]
    html = seen_pages["setup"]
    assert "draft_template" in html
    assert "blank@0.1.0" in html
    assert "Concrete fc" in html
    assert "35" in html
    assert "MPa" in html
    assert "provided" in html
    assert "min 20 MPa (ACI 318-14 19.2.1)" in html
    assert "max 80 MPa (ACI 318-14 19.2.1)" in html
    assert "<b>x</b>" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert '<bdi dir="auto">' in html
    assert 'name="confirm_materials"' in html
    assert 'name="confirm_limits"' in html
    assert 'name="confirm_modeling"' in html
    assert 'name="by"' in html
    assert 'name="by" value=' not in html

    setup_logs = list((rig.workspace / "setups").glob("*.json"))
    assert len(setup_logs) == 1
    raw_log = setup_logs[0].read_bytes()
    assert not raw_log.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw_log
    records = json.loads(raw_log.decode("utf-8"))
    assert len(records) == 1
    record = records[0]
    assert record["by"] == "Ada"
    assert record["at"] == "2026-01-01T00:00:00.001Z"
    assert set(record["confirmed_sections"]) == {"materials", "limits", "modeling"}
    assert len(record["draft_sha256"]) == 64
    assert set(record) == {"setup_id", "draft_sha256", "confirmed_sections", "by", "at", "rejected"}
    assert "values" not in record
    assert "ملاحظة" not in raw_log.decode("utf-8")

    request = rig.engines[0].run_request
    assert request is not None
    clock = FixedClock(1_767_225_600_000, 1)
    store = ResultStore(
        Workspace(root=rig.workspace, classification=LocationClass.LOCAL),
        HARNESS_KINDS,
        SeededIdSource(b"r", clock),
        clock,
    )
    stored = store.payload(request.basis_ref)
    fields = stored["fields"]
    assert isinstance(fields, dict)
    fc = fields["materials.concrete_fc_MPa"]
    assert isinstance(fc, dict)
    assert fc["confirmed"] is True
    assert fc["source"] == "engineer:Ada@2026-01-01T00:00:00.001Z"


def test_reject_leaves_no_run(tmp_path: Path) -> None:
    basis_path = _basis_file(tmp_path)
    rig = Rig(tmp_path)
    post_statuses: list[int] = []

    def interact(client: Any) -> None:
        setup_path = _setup_path(client)
        page = client.get(setup_path)
        draft_match = _DRAFT_SHA.search(page.body)
        assert draft_match is not None
        form = {
            CSRF_FIELD: client.token(setup_path),
            "draft_sha256": draft_match.group(1),
            "decision": "reject",
            "reason": "fc too low",
        }
        post_statuses.append(client.post(setup_path, form).status)

    rig.open_with = _threaded(interact)
    code = rig.main(
        "run",
        BASIS_FLOW,
        "--basis",
        str(basis_path),
        "--progress",
        "off",
        workflow_registry=BASIS_REGISTRY,
        basis_fields_of=lambda w: w.basis_fields,
    )
    assert code == ExitCode.REFUSED
    assert post_statuses == [HTTPStatus.OK]
    assert rig.run_ids() == []
    assert not rig.runs.exists()
    assert not (rig.workspace / "results").exists()
    assert rig.engines == []
    setup_logs = list((rig.workspace / "setups").glob("*.json"))
    assert len(setup_logs) == 1
    records = json.loads(setup_logs[0].read_text(encoding="utf-8"))
    assert records[0]["rejected"] == "fc too low"


def test_stale_draft_hash_refused(tmp_path: Path) -> None:
    basis_path = _basis_file(tmp_path)
    rig = Rig(tmp_path)
    statuses: list[int] = []

    def interact(client: Any) -> None:
        setup_path = _setup_path(client)
        page = client.get(setup_path)
        draft_match = _DRAFT_SHA.search(page.body)
        assert draft_match is not None
        current_sha = draft_match.group(1)
        stale_form = {
            CSRF_FIELD: client.token(setup_path),
            "draft_sha256": "0" * 64,
            "by": "Ada",
            "decision": "confirm",
            "confirm_materials": "on",
            "confirm_limits": "on",
            "confirm_modeling": "on",
        }
        statuses.append(client.post(setup_path, stale_form).status)
        fresh_form = stale_form | {CSRF_FIELD: client.token(setup_path), "draft_sha256": current_sha}
        statuses.append(client.post(setup_path, fresh_form).status)

    rig.open_with = _threaded(interact)
    code = rig.main(
        "run",
        BASIS_FLOW,
        "--basis",
        str(basis_path),
        "--no-report",
        "--progress",
        "off",
        workflow_registry=BASIS_REGISTRY,
        basis_fields_of=lambda w: w.basis_fields,
    )
    assert code == ExitCode.OK
    assert statuses == [HTTPStatus.CONFLICT, HTTPStatus.OK]


def test_no_wait_basis_exits_10_nothing_stored(tmp_path: Path) -> None:
    basis_path = _basis_file(tmp_path)
    rig = Rig(tmp_path)
    code = rig.main(
        "run",
        BASIS_FLOW,
        "--basis",
        str(basis_path),
        "--no-wait",
        "--progress",
        "off",
        workflow_registry=BASIS_REGISTRY,
        basis_fields_of=lambda w: w.basis_fields,
    )
    assert code == ExitCode.AWAITING_ENGINEER
    assert "without `--no-wait`" in rig.err.getvalue()
    assert rig.opened == []
    assert not rig.runs.exists()
    assert not (rig.workspace / "setups").exists()
    assert not (rig.workspace / "results").exists()
    assert rig.engines == []


def test_basis_screen_renders_warnings_unused_and_unconfirmable_sections() -> None:
    setup_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    sha = "b" * 64
    hub = PageApprovalPort(engineer="Grace").hub
    view = BasisSetupView(
        setup_id=setup_id,
        draft_sha256=sha,
        workflow="edit_cycle",
        template=DraftTemplate(
            name="synthetic-test",
            version="0.1.0",
            sha256="c" * 64,
            chain=("synthetic-test@0.1.0",),
            status="draft",
            synthetic=True,
        ),
        banners=("draft_template", "synthetic_template"),
        sections=(
            SetupSection(
                name="materials",
                confirmable=True,
                rows=(
                    SetupRow(
                        path="materials.concrete_fc_MPa",
                        label="Concrete fc",
                        value=35.0,
                        unit="MPa",
                        source="template:synthetic-test@0.1.0",
                        citation="ACI 318-14 19.2.1",
                        state="detected",
                        required=True,
                        min=Cited(value=20.0, unit="MPa", source="ACI 318-14 19.2.1"),
                        max=None,
                    ),
                ),
            ),
            SetupSection(
                name="limits",
                confirmable=False,
                rows=(
                    SetupRow(
                        path="limits.ratio_limit_ratio",
                        label="Ratio limit",
                        value=None,
                        unit="1",
                        source=None,
                        citation=None,
                        state="missing",
                        required=True,
                        min=None,
                        max=None,
                    ),
                ),
            ),
        ),
        warnings=(
            DraftWarning(kind="detected_differs", path="materials.concrete_fc_MPa", detected=35.0, template=28.0),
        ),
        unused=("other.unused_mm",),
    )
    screen = basis_screen(hub, view)
    html = document(screen.title, screen.render("tok"), STYLESHEET)
    assert "draft_template" in html
    assert "synthetic_template" in html
    assert "synthetic-test@0.1.0 (draft)" in html
    assert "materials.concrete_fc_MPa: detected 35 vs template 28" in html
    assert "other.unused_mm" in html
    assert "Engineer named in the settings" in html
    assert "Grace" in html
    assert f'name="{CONFIRM}materials"' in html
    assert f'name="{CONFIRM}limits"' not in html
    assert "Missing required rows" in html
    assert 'value="confirm"' not in html
    assert 'value="reject"' in html

    long_section = BasisSetupView(
        setup_id=setup_id,
        draft_sha256=sha,
        workflow="w",
        template=None,
        banners=(),
        sections=(SetupSection(name="s" * 58, confirmable=True, rows=()),),
        warnings=(),
        unused=(),
    )
    refused = basis_screen(hub, long_section)
    refused_html = document(refused.title, refused.render("tok"), STYLESHEET)
    assert "cannot be shown safely" in refused_html
    assert "<form" not in refused_html
    assert "<button" not in refused_html


def test_parse_setup_validation_and_boundaries() -> None:
    clock = FixedClock(1_767_225_600_000, 1)
    draft: BasisDraft = build_draft(
        BASIS_FIELDS,
        None,
        None,
        (),
    )
    assert draft.pending == ("materials.concrete_fc_MPa", "limits.ratio_limit_ratio")
    incomplete_view = build_setup_view(draft, workflow=BASIS_FLOW, setup_id="01ARZ3NDEKTSV4RRFFQ69G5FAV")
    complete_view = BasisSetupView(
        setup_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
        draft_sha256="a" * 64,
        workflow=BASIS_FLOW,
        template=None,
        banners=(),
        sections=(
            SetupSection(name="materials", confirmable=True, rows=()),
            SetupSection(name="limits", confirmable=True, rows=()),
        ),
        warnings=(),
        unused=(),
    )
    base = {"draft_sha256": complete_view.draft_sha256, "by": "Ada"}
    with pytest.raises(AnswerError) as conflict:
        parse_setup(complete_view, base | {"draft_sha256": "f" * 64, "decision": "confirm"}, clock)
    assert conflict.value.status == HTTPStatus.CONFLICT

    bad_cases = [
        ({"decision": "other"}, "choose confirm or reject"),
        ({}, "choose confirm or reject"),
        ({"decision": "reject", "reason": "   "}, "a rejection needs a reason of 1 to 500 characters"),
        ({"decision": "reject", "reason": "x" * (REASON_MAX + 1)}, "a reason has at most 500 characters"),
        ({"decision": "confirm", "reason": "x" * (REASON_MAX + 1)}, "a reason has at most 500 characters"),
        ({"decision": "confirm", "by": ""}, "the name has 1 to 100 characters"),
        ({"decision": "confirm", f"{CONFIRM}materials": "on"}, "confirm every section (missing: limits)"),
    ]
    for extra, msg in bad_cases:
        with pytest.raises(AnswerError, match=re.escape(msg)):
            parse_setup(complete_view, base | extra, clock)

    with pytest.raises(AnswerError, match="missing required values"):
        parse_setup(
            incomplete_view,
            {"draft_sha256": incomplete_view.draft_sha256, "by": "Ada", "decision": "confirm"},
            clock,
        )

    empty_view = complete_view.model_copy(update={"sections": ()})
    with pytest.raises(AnswerError, match="no sections"):
        parse_setup(empty_view, base | {"decision": "confirm"}, clock)

    edge_reject = parse_setup(
        complete_view,
        {"draft_sha256": complete_view.draft_sha256, "decision": "reject", "reason": f" {'x' * REASON_MAX} "},
        clock,
    )
    assert edge_reject.rejected == "x" * REASON_MAX
    ok = parse_setup(
        complete_view,
        base | {"decision": "confirm", f"{CONFIRM}materials": "on", f"{CONFIRM}limits": "on"},
        clock,
    )
    assert ok.confirmed_sections == ("materials", "limits")
    assert ok.by == "Ada"
    assert ok.at == "2026-01-01T00:00:00.000Z"


def test_setup_log_appends_atomically_and_rejects_bad_inputs(tmp_path: Path) -> None:
    setup_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    bad = BasisSetupAnswer(setup_id=setup_id, draft_sha256="a" * 64, rejected="مرفوض")
    with pytest.raises(ValueError, match="setup_id"):
        append_setup_log(tmp_path, bad.model_copy(update={"setup_id": "../escape"}), "2026-01-01T00:00:00.000Z")

    log_path = append_setup_log(tmp_path, bad, "2026-01-01T00:00:00.000Z")
    good = BasisSetupAnswer(
        setup_id=setup_id,
        draft_sha256="b" * 64,
        confirmed_sections=("materials",),
        by="مهندس علي",
        at="2026-01-01T00:00:01.000Z",
    )
    append_setup_log(tmp_path, good, "2026-01-01T00:00:01.000Z")
    raw = log_path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    entries = json.loads(raw.decode("utf-8"))
    assert [e["rejected"] for e in entries] == ["مرفوض", None]
    assert [e["by"] for e in entries] == [None, "مهندس علي"]
    assert list(tmp_path.iterdir()) == [log_path]

    bad_file = tmp_path / "01ARZ3NDEKTSV4RRFFQ69G5FAW.json"
    bad_file.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON array"):
        append_setup_log(tmp_path, good.model_copy(update={"setup_id": bad_file.stem}), "2026-01-01T00:00:01.000Z")


def test_setup_log_atomicity_on_replacement_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Interrupted or failed replacement keeps an existing log intact and exposes no partial target."""
    setup_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    first = BasisSetupAnswer(
        setup_id=setup_id,
        draft_sha256="a" * 64,
        confirmed_sections=("materials",),
        by="Ada",
        at="2026-01-01T00:00:00.000Z",
    )
    target = append_setup_log(tmp_path, first, "2026-01-01T00:00:00.000Z")
    original_bytes = target.read_bytes()
    assert target.is_file()

    def fail_replace(src: Any, dst: Any) -> None:
        raise OSError("simulated atomic rename failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    second = BasisSetupAnswer(
        setup_id=setup_id,
        draft_sha256="b" * 64,
        confirmed_sections=("materials", "geometry"),
        by="Grace",
        at="2026-01-01T00:00:05.000Z",
    )
    with pytest.raises(OSError, match="simulated atomic rename failure"):
        append_setup_log(tmp_path, second, "2026-01-01T00:00:05.000Z")

    # Existing log remains completely intact
    assert target.read_bytes() == original_bytes
    entries = json.loads(target.read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert entries[0]["by"] == "Ada"

    # When creating a new log, replacement failure exposes no partial target file
    fresh_dir = tmp_path / "fresh"
    fresh_target = fresh_dir / f"{setup_id}.json"
    with pytest.raises(OSError, match="simulated atomic rename failure"):
        append_setup_log(fresh_dir, first, "2026-01-01T00:00:00.000Z")
    assert not fresh_target.exists()


def test_page_basis_setup_port_standalone_and_wait_paths(tmp_path: Path) -> None:
    clock = FixedClock(1_767_225_600_000, 1)
    stop_flag = [False]
    port = PageBasisSetupPort(
        setups_dir=tmp_path / "setups",
        clock=clock,
        engineer="Ada",
        stop_requested=lambda: stop_flag[0],
        wait_timeout_s=0.05,
    )
    setup_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    view = BasisSetupView(
        setup_id=setup_id,
        draft_sha256="a" * 64,
        workflow=BASIS_FLOW,
        template=None,
        banners=(),
        sections=(SetupSection(name="materials", confirmable=True, rows=()),),
        warnings=(),
        unused=(),
    )
    assert port.answer("01ARZ3NDEKTSV4RRFFQ69G5FAW", wait=False) is None
    port.present(view)
    assert port.answer(setup_id, wait=False) is None
    assert port.answer(setup_id, wait=True) is None  # wait_timeout_s expires

    stop_flag[0] = True
    port_stop = PageBasisSetupPort(
        setups_dir=tmp_path / "setups",
        clock=clock,
        stop_requested=lambda: stop_flag[0],
        wait_timeout_s=5.0,
    )
    port_stop.present(view)
    assert port_stop.answer(setup_id, wait=True) is None

    with PageServer(port.hub) as server:
        client = PageClient(server)
        client.open()
        assert f"/setup/{setup_id}" in client.get("/").body
        token = client.token(f"/setup/{setup_id}")
        bad_post = client.post(
            f"/setup/{setup_id}",
            {CSRF_FIELD: token, "draft_sha256": view.draft_sha256, "decision": "reject", "reason": ""},
        )
        assert bad_post.status == HTTPStatus.BAD_REQUEST
        assert f'href="/setup/{setup_id}"' in bad_post.body
        good_post = client.post(
            f"/setup/{setup_id}",
            {
                CSRF_FIELD: client.token(f"/setup/{setup_id}"),
                "draft_sha256": view.draft_sha256,
                "by": "Grace",
                "decision": "confirm",
                f"{CONFIRM}materials": "on",
            },
        )
        assert good_post.status == HTTPStatus.OK
        assert port.hub.engineer == "Grace"
        assert f"/setup/{setup_id}" not in client.get("/").body
        assert client.get(f"/setup/{setup_id}").status == HTTPStatus.NOT_FOUND
        second_post = client.post(
            f"/setup/{setup_id}",
            {
                CSRF_FIELD: token,
                "draft_sha256": view.draft_sha256,
                "by": "Bob",
                "decision": "confirm",
                f"{CONFIRM}materials": "on",
            },
        )
        assert second_post.status == HTTPStatus.CONFLICT
        answer = port.answer(setup_id, wait=False)
        assert answer is not None
        assert answer.by == "Grace"


def test_basis_step_refusals_and_json_bom_values(tmp_path: Path) -> None:
    # 1. `--template NAME` without `@VERSION` exits 2 naming `NAME@VERSION`.
    rig = Rig(tmp_path / "no_version")
    assert (
        rig.main(
            "run",
            BASIS_FLOW,
            "--template",
            "blank",
            "--progress",
            "off",
            workflow_registry=BASIS_REGISTRY,
            basis_fields_of=lambda w: w.basis_fields,
        )
        == ExitCode.USAGE
    )
    assert "NAME@VERSION" in rig.err.getvalue()

    # 2. Missing template version exits 2.
    rig = Rig(tmp_path / "missing_tmpl")
    assert (
        rig.main(
            "run",
            BASIS_FLOW,
            "--template",
            "blank@9.9.9",
            "--progress",
            "off",
            workflow_registry=BASIS_REGISTRY,
            basis_fields_of=lambda w: w.basis_fields,
        )
        == ExitCode.USAGE
    )

    # 3. Missing or invalid `--basis` exits 2 naming the file.
    rig = Rig(tmp_path / "missing_basis")
    assert (
        rig.main(
            "run",
            BASIS_FLOW,
            "--basis",
            str(tmp_path / "missing.yaml"),
            "--progress",
            "off",
            workflow_registry=BASIS_REGISTRY,
            basis_fields_of=lambda w: w.basis_fields,
        )
        == ExitCode.USAGE
    )
    assert "missing.yaml" in rig.err.getvalue()

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("name: Ada\nconfirmed: true\nvalues: {}\n", encoding="utf-8")
    rig = Rig(tmp_path / "confirmed_basis")
    assert (
        rig.main(
            "run",
            BASIS_FLOW,
            "--basis",
            str(bad_yaml),
            "--progress",
            "off",
            workflow_registry=BASIS_REGISTRY,
            basis_fields_of=lambda w: w.basis_fields,
        )
        == ExitCode.USAGE
    )
    assert "bad.yaml" in rig.err.getvalue()

    # 4. Missing required basis fields exits 3 without serving a page.
    rig = Rig(tmp_path / "pending")
    assert (
        rig.main(
            "run",
            BASIS_FLOW,
            "--template",
            "blank@0.1.0",
            "--progress",
            "off",
            workflow_registry=BASIS_REGISTRY,
            basis_fields_of=lambda w: w.basis_fields,
        )
        == ExitCode.REFUSED
    )
    assert "materials.concrete_fc_MPa" in rig.err.getvalue()
    assert rig.opened == []

    # 5. `--wait-timeout 1` on basis screen exits 10 with nothing stored.
    basis_path = _basis_file(tmp_path)
    rig = Rig(tmp_path / "timeout", open_with=lambda _: False)
    assert (
        rig.main(
            "run",
            BASIS_FLOW,
            "--basis",
            str(basis_path),
            "--wait-timeout",
            "1",
            "--no-browser",
            "--progress",
            "off",
            workflow_registry=BASIS_REGISTRY,
            basis_fields_of=lambda w: w.basis_fields,
        )
        == ExitCode.AWAITING_ENGINEER
    )
    assert not (rig.workspace / "results").exists()

    # 6. JSON `--basis` file with UTF-8 BOM works end to end.
    json_basis = tmp_path / "values.json"
    payload = {
        "name": "Engineer B",
        "values": {
            "materials.concrete_fc_MPa": {"value": 35, "unit": "MPa"},
            "limits.ratio_limit_ratio": {"value": 0.95, "unit": "1"},
        },
    }
    json_basis.write_text(json.dumps(payload), encoding="utf-8-sig")
    rig = Rig(tmp_path / "json_bom")

    def confirm(client: Any) -> None:
        setup_path = _setup_path(client)
        sha = _DRAFT_SHA.search(client.get(setup_path).body)
        assert sha is not None
        client.post(
            setup_path,
            {
                CSRF_FIELD: client.token(setup_path),
                "draft_sha256": sha.group(1),
                "by": "Ada",
                "decision": "confirm",
                f"{CONFIRM}materials": "on",
                f"{CONFIRM}limits": "on",
                f"{CONFIRM}modeling": "on",
            },
        )

    rig.open_with = _threaded(confirm)
    assert (
        rig.main(
            "run",
            BASIS_FLOW,
            "--basis",
            str(json_basis),
            "--no-report",
            "--progress",
            "off",
            workflow_registry=BASIS_REGISTRY,
            basis_fields_of=lambda w: w.basis_fields,
        )
        == ExitCode.OK
    )

    # 7. Declaration mismatch exits 2.
    rig = Rig(tmp_path / "mismatch")
    assert (
        rig.main(
            "run",
            BASIS_FLOW,
            "--progress",
            "off",
            workflow_registry=BASIS_REGISTRY,
            basis_fields_of=lambda _w: (),
        )
        == ExitCode.USAGE
    )


def test_basis_confirmation_flow_real_engine(tmp_path: Path) -> None:
    """AC47 re-check with the real engine (plan 0006 T17c)."""
    raise AssertionError("T17c: real-engine re-check of AC47 not yet written")
