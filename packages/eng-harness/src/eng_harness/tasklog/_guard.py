"""The task-log guard: no secret reaches a record (spec 0015 section 4.4).

Purpose: `guard_record` scans the free-text fields of a task record with the gate's secret rule names and
patterns (copied from the gate's secrets rules, which the harness must never import, spec 0015 §2); owner `text`
and harness-derived text are withheld with a `<withheld:rule:fp12>` marker and a `Redaction` entry, while agent
`*_en` fields are refused with `GuardRefusal`, which names the field and the rule but never the text.
Units: `start` and `end` are offsets in the original text; the marker carries the first 12 hex digits of the
span's SHA-256.
Errors: `GuardRefusal` for a hit in an agent field.
"""

import hashlib
import re
from typing import Any, assert_never

from eng_harness.tasklog._records import (
    DidInstead,
    Handoff,
    Narration,
    NotFound,
    OwnerWords,
    Problem,
    Redaction,
    RunAttached,
    RunFact,
    RunRefused,
    Searched,
    TaskClosed,
    TaskOpened,
    TaskRecord,
    WithheldAfter,
)

__all__ = ["GuardRefusal", "guard_record"]

FINGERPRINT_DIGITS = 12
"""Hex digits of the span SHA-256 in the marker (spec 0015 4.4; the gate's 12-digit fingerprint)."""

_HARNESS_BY = "harness"
"""The `by` value whose text is withheld rather than refused (spec 0015 4.3, 4.4)."""

_DETAIL_FIELD = "detail.message_en"
"""Field name of the nested `not_found.detail.message_en` in refusals and redactions."""

_USER_NAME = r"[A-Za-z0-9._-]+"
"""A real user name in a personal path (the gate's `_NAME`; a placeholder never matches)."""

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github-token", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("github-fine-grained-token", re.compile(r"github_pat_[A-Za-z0-9_]+")),
    ("aws-access-key-id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("slack-token", re.compile(r"xox[abprs]-[A-Za-z0-9-]+")),
    ("anthropic-key", re.compile(r"sk-ant-[A-Za-z0-9_-]+")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "credential-assignment",
        re.compile(r"\w*(?:password|secret|token|api_key)\w*[\"']?\s*[:=]\s*([\"'])[^\"'\r\n]{8,}\1", re.IGNORECASE),
    ),
    ("personal-path", re.compile(rf"[A-Za-z]:\\Users\\{_USER_NAME}|/home/{_USER_NAME}/|/Users/{_USER_NAME}/")),
)
"""The gate's secret rule names and patterns, copied (the harness never imports eng-dev-gate, spec 0015 §2, §4.4)."""


class GuardRefusal(Exception):  # noqa: N818  # B-625: the T2 tests pin the name GuardRefusal
    """A secret in an agent field; names the field and the rule, never the text (spec 0015 §4.4, §6)."""

    def __init__(self, field: str, rule: str) -> None:
        """Build the refusal naming `field` and `rule`."""
        super().__init__(f"{field}: {rule}")
        self.field = field
        self.rule = rule


def _first_hit(text: str) -> str | None:
    """The rule of the earliest match in `text` (ties take the gate's rule order), else None."""
    hit: str | None = None
    at: int | None = None
    for rule, pattern in _RULES:
        found = pattern.search(text)
        if found is None:
            continue
        if at is None or found.start() < at:
            hit = rule
            at = found.start()
    return hit


def _withhold(field: str, text: str) -> tuple[str, list[Redaction]]:
    """`text` with every matched span replaced by its marker, plus one `Redaction` per span (spec 0015 §4.4).

    Offsets are in the original text; a match overlapped by an earlier one is skipped.
    """
    spans = sorted((found.start(), found.end(), rule) for rule, pattern in _RULES for found in pattern.finditer(text))
    chunks: list[str] = []
    entries: list[Redaction] = []
    last: int | None = None
    for start, end, rule in spans:
        if last is not None and start < last:
            continue
        chunks.append(text[:start] if last is None else text[last:start])
        span = text[start:end]
        digest = hashlib.sha256(span.encode("utf-8")).hexdigest()
        chunks.append(f"<withheld:{rule}:{digest[:FINGERPRINT_DIGITS]}>")
        entries.append(Redaction(field=field, rule=rule, start=start, end=end, span_sha256=digest))
        last = end
    chunks.append(text if last is None else text[last:])
    return "".join(chunks), entries


def _texts(record: TaskRecord) -> tuple[tuple[str, str | None], ...]:
    """The (field, value) free-text pairs of `record` in check order (spec 0015 §4.3, §4.4)."""
    if isinstance(record, TaskOpened):
        return (("title_en", record.title_en),)
    if isinstance(record, OwnerWords):
        return (("gloss_en", record.gloss_en),)
    if isinstance(record, Narration):
        return (("text_en", record.text_en),)
    if isinstance(record, Searched):
        return (("for_en", record.for_en), ("detail_en", record.detail_en))
    if isinstance(record, NotFound):
        return (("need_en", record.need_en),)
    if isinstance(record, DidInstead):
        return (("text_en", record.text_en),)
    if isinstance(record, Problem):
        return (("text_en", record.text_en),)
    if isinstance(record, Handoff):
        return (("done_en", record.done_en), ("left_en", record.left_en), ("why_en", record.why_en))
    if isinstance(record, RunRefused):
        return (("message_en", record.message_en),)
    if isinstance(record, RunAttached):
        return ()
    if isinstance(record, RunFact):
        return (("summary_en", record.summary_en), ("reason", record.reason), ("owner_text", record.owner_text))
    if isinstance(record, TaskClosed):
        return (("summary_en", record.summary_en), ("next_en", record.next_en))
    if isinstance(record, WithheldAfter):
        return (("reason_en", record.reason_en),)
    assert_never(record)


def _detail_message(record: TaskRecord) -> str | None:
    """The nested `not_found.detail.message_en` of `record`, else None (spec 0015 §4.3, §4.4)."""
    if isinstance(record, NotFound) and record.detail is not None:
        return record.detail.message_en
    return None


def _guard_refuse(record: TaskRecord) -> TaskRecord:
    """`record` unchanged when clean, else `GuardRefusal` naming the first dirty field and rule."""
    for name, text in _texts(record):
        if text is None:
            continue
        hit = _first_hit(text)
        if hit is not None:
            raise GuardRefusal(name, hit)
    message = _detail_message(record)
    if message is not None:
        hit = _first_hit(message)
        if hit is not None:
            raise GuardRefusal(_DETAIL_FIELD, hit)
    return record


def _guard_withhold(record: TaskRecord) -> TaskRecord:
    """`record` with every secret span withheld and a `Redaction` per span; unchanged when clean."""
    update: dict[str, Any] = {}
    entries: list[Redaction] = []
    for name, text in _texts(record):
        if text is None:
            continue
        cleaned, found = _withhold(name, text)
        if found:
            update[name] = cleaned
            entries.extend(found)
    message = _detail_message(record)
    if message is not None and isinstance(record, NotFound) and record.detail is not None:
        cleaned, found = _withhold(_DETAIL_FIELD, message)
        if found:
            update["detail"] = record.detail.model_copy(update={"message_en": cleaned})
            entries.extend(found)
    if not update:
        return record
    update["redactions"] = [*record.redactions, *entries]
    return record.model_copy(update=update)


def _guard_owner_words(record: OwnerWords) -> OwnerWords:
    """Owner words: `gloss_en` refused like agent text, `text` withheld with the original's hash kept (§4.4)."""
    _guard_refuse(record)
    cleaned, found = _withhold("text", record.text)
    if not found:
        return record
    return record.model_copy(update={"text": cleaned, "redactions": [*record.redactions, *found]})


def guard_record(record: TaskRecord) -> TaskRecord:
    """Guard one record: owner and harness text is withheld, agent fields are refused (spec 0015 §4.4).

    Owner `text` and every free-text field of a harness record (`by == "harness"`) has its secret spans
    replaced by `<withheld:rule:fp12>` markers with one `Redaction` per span; a hit in any other free-text
    field raises `GuardRefusal` naming the field and the rule, never the text.
    """
    if isinstance(record, OwnerWords):
        return _guard_owner_words(record)
    if record.by == _HARNESS_BY:
        return _guard_withhold(record)
    return _guard_refuse(record)
