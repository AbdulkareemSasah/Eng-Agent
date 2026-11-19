"""The basis confirmation screen and setup log (spec 0006 4.4.7; AC47, AC48, AC49, AC58, AC59).

Purpose: render a `BasisSetupView` as read-only sections with per-section confirmation boxes, validate a posted
confirmation or rejection against `draft_sha256`, and append a value-free record to `setups/<setup_id>.json`.
Units: as carried by each `SetupRow` and bound. Errors: a refused answer is an `AnswerError` (409 when `draft_sha256`
does not match the view currently shown, else 400).
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

from eng_contract.cited import Cited
from eng_contract.ids import Clock, Timestamp
from pydantic import BaseModel, ConfigDict

from eng_harness import _html as h
from eng_harness._html import Element, Node, SafeToken, Tag, Trusted, el, trusted
from eng_harness._text import format_number
from eng_harness.basis import BasisSetupAnswer, BasisSetupView, SetupRow
from eng_harness.basis._setup import Banner
from eng_harness.pages import _labels as lb
from eng_harness.pages._answers import REASON_MAX, AnswerError, engineer_name
from eng_harness.pages._routes import Screen
from eng_harness.pages._screens_approval import _inline, _row, _show, _table
from eng_harness.pages._security import CSRF_FIELD, Subject

if TYPE_CHECKING:
    from eng_harness.pages._ports import PageHub

CONFIRM = "confirm_"  # token-safe prefix (AC49) for per-section confirmation checkboxes
_SHORT = 12
_SETUP_ID = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_COLUMNS: tuple[Trusted, ...] = tuple(
    trusted(name) for name in ("Path", "Label", "Value", "Unit", "Source", "Citation", "State", "Bounds")
)
_BANNERS: Mapping[Banner, Trusted] = {
    "draft_template": trusted("Draft template (draft_template): values come from an unapproved template."),
    "synthetic_template": trusted("Synthetic template (synthetic_template): placeholder values for tests only."),
}


class SetupLogEntry(BaseModel):
    """One entry in `<workspace>/setups/<setup_id>.json` (AC47): never carries an engineering value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    setup_id: str
    draft_sha256: str
    confirmed_sections: tuple[str, ...]
    by: str | None
    at: Timestamp
    rejected: str | None = None


def _bound(tag: str, cited: Cited | None) -> str | None:
    if cited is None:
        return None
    val = format_number(cited.value) if isinstance(cited.value, float) else str(cited.value)
    return f"{tag} {val} {cited.unit} ({cited.source})"


def _bounds(row: SetupRow) -> str:
    return "; ".join(part for part in (_bound("min", row.min), _bound("max", row.max)) if part is not None)


def _row_cells(row: SetupRow) -> Element:
    shown_value = "" if row.state == "missing" else _show(row.value)
    return _row(
        row.path,
        row.label,
        shown_value,
        row.unit or "",
        row.source or "",
        row.citation or "",
        row.state,
        _bounds(row),
    )


def _unsafe(view: BasisSetupView) -> str | None:
    for text in (view.setup_id, view.draft_sha256, *(CONFIRM + s.name for s in view.sections)):
        try:
            SafeToken(text)
        except h.HtmlError:
            return text
    return None


def basis_screen(hub: PageHub, view: BasisSetupView) -> Screen:
    """Render `BasisSetupView` as a read-only basis confirmation screen (spec 0006 4.4.7)."""
    subject = Subject("setup", view.setup_id, view.draft_sha256)
    title = trusted("Basis confirmation")
    back = el(Tag.P, el(Tag.A, lb.BACK, href=h.href()))
    if (problem := _unsafe(view)) is not None:
        refused = [el(Tag.H1, title), el(Tag.P, h.field(lb.NOT_SHOWN, problem)), back]
        return Screen(title, subject, frozenset(), lambda _: refused)

    confirmable = [s for s in view.sections if s.confirmable]
    all_confirmable = bool(view.sections) and len(confirmable) == len(view.sections)
    fields = frozenset({"draft_sha256", "by", "decision", "reason", *(CONFIRM + s.name for s in confirmable)})

    top: list[Node] = [el(Tag.H1, title)]
    for banner in view.banners:
        top.append(el(Tag.P, _BANNERS[banner], class_=SafeToken("draft")))
    top.append(
        el(Tag.P, h.field(trusted("Workflow"), view.workflow), h.field(trusted("Draft"), view.draft_sha256[:_SHORT]))
    )
    if view.template is not None:
        tmpl = f"{view.template.name}@{view.template.version} ({view.template.status})"
        top.append(
            el(Tag.P, h.field(trusted("Template"), tmpl), h.field(trusted("Chain"), ", ".join(view.template.chain)))
        )
    if view.warnings:
        items = [
            el(
                Tag.LI,
                h.field(
                    trusted("Difference"),
                    f"{w.path}: detected {_show(w.detected)} vs template {_show(w.template)}",
                ),
            )
            for w in view.warnings
        ]
        top.extend([el(Tag.H2, trusted("Warnings")), el(Tag.UL, *items)])
    if view.unused:
        top.append(el(Tag.P, h.field(trusted("Unused template paths"), ", ".join(view.unused))))

    def render(token: str) -> list[Node]:
        sections_nodes: list[Node] = []
        for section in view.sections:
            sections_nodes.append(el(Tag.H2, h.field(trusted("Section"), section.name)))
            sections_nodes.append(_table(_COLUMNS, [_row_cells(row) for row in section.rows]))
            if section.confirmable:
                box = el(Tag.INPUT, type=SafeToken("checkbox"), name=SafeToken(CONFIRM + section.name))
                sections_nodes.append(el(Tag.P, el(Tag.LABEL, box, trusted(" Confirm "), _inline(section.name))))
            else:
                sections_nodes.append(el(Tag.P, trusted("Missing required rows: this section cannot be confirmed.")))

        hidden_csrf = el(Tag.INPUT, type=SafeToken("hidden"), name=SafeToken(CSRF_FIELD), value=SafeToken(token))
        hidden_sha = el(
            Tag.INPUT, type=SafeToken("hidden"), name=SafeToken("draft_sha256"), value=SafeToken(view.draft_sha256)
        )
        who = [el(Tag.P, h.field(lb.NAME_PROPOSED, hub.engineer))] if hub.engineer is not None else []
        by_box = el(Tag.P, el(Tag.LABEL, lb.NAME, el(Tag.INPUT, type=SafeToken("text"), name=SafeToken("by"))))
        reason_box = el(
            Tag.P, el(Tag.LABEL, lb.REASON, el(Tag.INPUT, type=SafeToken("text"), name=SafeToken("reason")))
        )
        buttons: list[Node] = []
        if all_confirmable:
            buttons.append(
                el(
                    Tag.BUTTON,
                    trusted("Confirm"),
                    type=SafeToken("submit"),
                    name=SafeToken("decision"),
                    value=SafeToken("confirm"),
                )
            )
        buttons.append(
            el(Tag.BUTTON, lb.REJECT, type=SafeToken("submit"), name=SafeToken("decision"), value=SafeToken("reject"))
        )
        form = el(
            Tag.FORM,
            hidden_csrf,
            hidden_sha,
            *sections_nodes,
            *who,
            by_box,
            reason_box,
            el(Tag.P, *buttons),
            method=SafeToken("post"),
            action=h.href(SafeToken("setup"), SafeToken(view.setup_id)),
        )
        return [*top, form]

    return Screen(title, subject, fields, render)


def parse_setup(view: BasisSetupView, form: Mapping[str, str], clock: Clock) -> BasisSetupAnswer:
    """Validate a posted setup form against `view` and build a `BasisSetupAnswer` (spec 0006 4.4.7).

    Raises:
        AnswerError: 409 when `draft_sha256` differs from `view.draft_sha256`; 400 on missing boxes, name or reason.
    """
    if form.get("draft_sha256") != view.draft_sha256:
        raise AnswerError("the page was shown for another version of this draft", HTTPStatus.CONFLICT)
    decision = form.get("decision")
    if decision not in ("confirm", "reject"):
        raise AnswerError("choose confirm or reject")
    reason = form.get("reason", "").strip()
    if len(reason) > REASON_MAX:
        raise AnswerError(f"a reason has at most {REASON_MAX} characters")
    if decision == "reject":
        if not reason:
            raise AnswerError(f"a rejection needs a reason of 1 to {REASON_MAX} characters")
        return BasisSetupAnswer(setup_id=view.setup_id, draft_sha256=view.draft_sha256, rejected=reason)
    by = engineer_name(form.get("by", ""))
    if not view.sections:
        raise AnswerError("no sections to confirm")
    if any(not section.confirmable for section in view.sections):
        raise AnswerError("a section with missing required values cannot be confirmed")
    if missing := [s.name for s in view.sections if CONFIRM + s.name not in form]:
        raise AnswerError(f"confirm every section (missing: {missing[0]})")
    return BasisSetupAnswer(
        setup_id=view.setup_id,
        draft_sha256=view.draft_sha256,
        confirmed_sections=tuple(s.name for s in view.sections),
        by=by,
        at=clock.now(),
    )


def append_setup_log(setups_dir: Path, answer: BasisSetupAnswer, at: Timestamp) -> Path:
    """Append a value-free record to `<setups_dir>/<setup_id>.json` atomically (spec 0006 4.4.7; AC47, AC59)."""
    if _SETUP_ID.fullmatch(answer.setup_id) is None:
        raise ValueError("invalid setup_id")
    setups_dir.mkdir(parents=True, exist_ok=True)
    target = setups_dir / f"{answer.setup_id}.json"
    records: list[dict[str, object]] = []
    if target.is_file():
        existing = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            raise ValueError("setup log must hold a JSON array")
        records = list(existing)
    entry = SetupLogEntry(
        setup_id=answer.setup_id,
        draft_sha256=answer.draft_sha256,
        confirmed_sections=answer.confirmed_sections or (),
        by=answer.by,
        at=answer.at if answer.at is not None else at,
        rejected=answer.rejected,
    )
    records.append(entry.model_dump(mode="json"))
    temporary = setups_dir / f"{answer.setup_id}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, target)
    return target
