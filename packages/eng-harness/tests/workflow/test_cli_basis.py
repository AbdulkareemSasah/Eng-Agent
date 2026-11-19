"""Basis confirmation screen, setup log and step 3 of `run` (plan 0006 T15; spec 0006 AC47, 4.2.2, 4.4.7)."""

import contextlib
import json
import re
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any

from eng_contract.cited import Cited
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.store import LocationClass, ResultStore, Workspace
from helpers.cli_deps import FakeInput, FakeOutput, Rig, client_for

from eng_harness._kinds import HARNESS_KINDS
from eng_harness.basis import FieldSpec
from eng_harness.block import Registry, workflow
from eng_harness.cli import ExitCode
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
        "    unit: \"1\"\n"
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
    assert record["at"] == "2026-01-01T00:00:00.000Z"
    assert set(record["confirmed_sections"]) == {"materials", "limits", "modeling"}
    assert len(record["draft_sha256"]) == 64
    log_text = raw_log.decode("utf-8")
    assert "35" not in log_text
    assert "0.95" not in log_text
    assert "ملاحظة" not in log_text

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
    assert fields["materials.concrete_fc_MPa"]["confirmed"] is True
    assert fields["materials.concrete_fc_MPa"]["source"] == "engineer:Ada@2026-01-01T00:00:00.000Z"


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
