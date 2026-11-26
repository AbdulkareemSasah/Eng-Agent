"""No generated secret survives the guard (plan 0015 T2, property; spec 0015 §4.4)."""

import hashlib
import json
import string
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import TypeAdapter

from eng_harness.tasklog._guard import GuardRefusal, guard_record
from eng_harness.tasklog._records import OwnerWords, Redaction, RunFact, TaskRecord

_VECTORS_PATH = Path(__file__).resolve().parents[1] / "data" / "tasklog" / "secret_vectors.json"
_TASK_ID = "task_01KDVDNA00EEHMW00B9ZA4ZDSH"
_NEED_ID = "need_01KDVDNA00EEHMW00B9ZA4ZDSH_1"
_RUN_ID = "run_01KDVDNA01NEDC4EXH1ZACT2K2"
_AT = "2026-11-14T10:00:00Z"
_ZERO_SHA = "0" * 64
_AGENT = "agent:test-tool"
_RECORDS = TypeAdapter(TaskRecord)
_ALNUM = string.ascii_letters + string.digits
_PAD = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=0, max_size=8)
_AGENT_FIELDS = (
    "narration:text_en",
    "searched:for_en",
    "searched:detail_en",
    "not_found:need_en",
    "did_instead:text_en",
    "problem:text_en",
    "handoff:done_en",
    "task_closed:summary_en",
    "owner_words:gloss_en",
)


def _load_rules() -> tuple[str, ...]:
    """The rule ids of the vector file: the property covers every rule the vectors pin (AC7)."""
    raw: Any = json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    vectors = raw["vectors"]
    assert isinstance(vectors, list)
    rules = {vector["rule"] for vector in vectors}
    assert all(isinstance(rule, str) for rule in rules)
    assert len(rules) == 9
    return tuple(sorted(rules))


_RULES = _load_rules()
assert "github-token" in _RULES
_CASES = (
    [("owner", rule, "") for rule in _RULES]
    + [("harness", rule, "") for rule in _RULES]
    + [("agent", "github-token", field) for field in _AGENT_FIELDS]
)
_CASE_IDS = [f"{kind}-{field or rule}" for kind, rule, field in _CASES]


def _common(kind: str, by: str) -> dict[str, Any]:
    """The common record fields of spec 0015 §4.3."""
    return {
        "schema": "harness.tasklog_record/1",
        "task_id": _TASK_ID,
        "seq": 1,
        "at": _AT,
        "kind": kind,
        "by": by,
        "policy": "full",
        "redactions": [],
        "prev_sha256": _ZERO_SHA,
    }


def _searched(known: dict[str, Any]) -> dict[str, Any]:
    """A searched payload with the fixed fields plus `known`."""
    base: dict[str, Any] = {
        "for_en": "clean search",
        "where": "specs",
        "result": "found",
        "detail_en": "clean detail",
        "refs": [],
        "catalog": "available",
    }
    return _common("searched", _AGENT) | base | known


_CLEAN_AGENT: dict[str, dict[str, Any]] = {
    "narration:text_en": _common("narration", _AGENT) | {"text_en": "clean narration"},
    "searched:for_en": _searched({}),
    "searched:detail_en": _searched({}),
    "not_found:need_en": _common("not_found", _AGENT)
    | {
        "need_id": _NEED_ID,
        "category": "no_workflow",
        "need_en": "clean need",
        "evidence": ["#1"],
        "blocking": False,
    },
    "did_instead:text_en": _common("did_instead", _AGENT) | {"way": "nothing", "text_en": "clean instead", "refs": []},
    "problem:text_en": _common("problem", _AGENT) | {"text_en": "clean problem", "evidence": ["#1"]},
    "handoff:done_en": _common("handoff", _AGENT)
    | {"to": "owner", "done_en": "clean done", "left_en": "clean left", "why_en": "clean why"},
    "task_closed:summary_en": _common("task_closed", _AGENT)
    | {"status": "DONE", "summary_en": "clean summary", "open_needs": []},
    "owner_words:gloss_en": _common("owner_words", _AGENT)
    | {
        "role": "request",
        "lang": "en",
        "text": "clean owner words",
        "text_sha256": hashlib.sha256(b"clean owner words").hexdigest(),
    },
}


def _agent_record(field: str, dirty: str) -> TaskRecord:
    """An agent-written record with `dirty` in the `kind:attr` field (spec 0015 §4.3: agent `*_en`)."""
    payload = dict(_CLEAN_AGENT[field])
    payload[field.split(":")[1]] = dirty
    return _RECORDS.validate_python(payload)


def _owner_record(text: str) -> OwnerWords:
    """An owner_words record whose text_sha256 is the SHA-256 of the input bytes (spec 0015 §4.3)."""
    payload = _common("owner_words", _AGENT) | {
        "role": "request",
        "lang": "ar",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    record = _RECORDS.validate_python(payload)
    assert isinstance(record, OwnerWords)
    return record


def _harness_record(summary: str) -> RunFact:
    """A harness-written run_fact record carrying `summary` (spec 0015 §4.3: harness text is withheld)."""
    payload = _common("run_fact", "harness") | {
        "run_id": _RUN_ID,
        "journal_seq": 3,
        "event": "step_failed",
        "summary_en": summary,
    }
    record = _RECORDS.validate_python(payload)
    assert isinstance(record, RunFact)
    return record


def _marker(rule: str, span: str) -> str:
    """The expected marker: the rule and the 12-digit fingerprint of the span (spec 0015 §4.4)."""
    return f"<withheld:{rule}:{hashlib.sha256(span.encode('utf-8')).hexdigest()[:12]}>"


def _build_secret(rule: str, data: st.DataObject) -> tuple[str, str]:
    """A generated (secret, span) pair for `rule`: every shape the gate rules match (spec 0015 §4.4)."""
    if rule == "github-token":
        body = data.draw(st.text(alphabet=_ALNUM, min_size=36, max_size=36))
        secret = f"ghp_{body}"
        return secret, secret
    if rule == "github-fine-grained-token":
        body = data.draw(st.text(alphabet=_ALNUM + "_", min_size=4, max_size=16))
        secret = f"github_pat_{body}"
        return secret, secret
    if rule == "aws-access-key-id":
        body = data.draw(st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=16, max_size=16))
        secret = f"AKIA{body}"
        return secret, secret
    if rule == "google-api-key":
        body = data.draw(st.text(alphabet=_ALNUM + "_-", min_size=35, max_size=35))
        secret = f"AIza{body}"
        return secret, secret
    if rule == "slack-token":
        letter = data.draw(st.sampled_from("abprs"))
        body = data.draw(st.text(alphabet=_ALNUM + "-", min_size=4, max_size=16))
        secret = f"xox{letter}-{body}"
        return secret, secret
    if rule == "anthropic-key":
        body = data.draw(st.text(alphabet=_ALNUM + "_-", min_size=4, max_size=16))
        secret = f"sk-ant-{body}"
        return secret, secret
    if rule == "private-key":
        middle = data.draw(st.sampled_from(["", "RSA ", "EC ", "OPENSSH "]))
        secret = f"-----BEGIN {middle}PRIVATE KEY-----"
        return secret, secret
    if rule == "credential-assignment":
        name = data.draw(st.sampled_from(["password", "secret", "token", "api_key", "my_password", "secret2"]))
        eq = data.draw(st.sampled_from([" = ", "=", ": ", ":"]))
        quote = data.draw(st.sampled_from(["'", '"']))
        body = data.draw(st.text(alphabet=_ALNUM, min_size=8, max_size=24))
        secret = f"{name}{eq}{quote}{body}{quote}"
        return secret, secret
    if rule == "personal-path":
        user = data.draw(st.text(alphabet=_ALNUM + "._-", min_size=2, max_size=12))
        flavor = data.draw(st.sampled_from(["posix", "mac", "windows"]))
        if flavor == "posix":
            return f"/home/{user}/proj", f"/home/{user}/"
        if flavor == "mac":
            return f"/Users/{user}/work", f"/Users/{user}/"
        return f"C:\\Users\\{user}\\Docs", f"C:\\Users\\{user}"
    raise AssertionError(f"no generator for rule: {rule}")


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
@given(data=st.data(), pad_before=_PAD, pad_after=_PAD)
@settings(derandomize=True, max_examples=25, deadline=None)
def test_guard_never_leaks(case: tuple[str, str, str], data: st.DataObject, pad_before: str, pad_after: str) -> None:
    """No generated secret survives: owner and harness spans are withheld, agent fields refused (spec 0015 §4.4)."""
    kind, rule, field = case
    secret, span = _build_secret(rule, data)
    assert secret.startswith(span)
    if kind == "owner":
        before = f"نفذ {pad_before} "
        after = f" {pad_after} شكرا"
        text = f"{before}{secret}{after}"
        guarded = guard_record(_owner_record(text))
        assert isinstance(guarded, OwnerWords)
        start = len(before)
        end = start + len(secret)
        assert text[start:end] == secret
        rest = secret.removeprefix(span)
        span_end = start + len(span)
        span_sha = hashlib.sha256(span.encode("utf-8")).hexdigest()
        assert guarded.text == f"{before}{_marker(rule, span)}{rest}{after}"
        assert guarded.text_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert guarded.redactions == [
            Redaction(field="text", rule=rule, start=start, end=span_end, span_sha256=span_sha)
        ]
    elif kind == "harness":
        before = f"failed {pad_before} "
        after = f" {pad_after} retry"
        text = f"{before}{secret}{after}"
        guarded = guard_record(_harness_record(text))
        assert isinstance(guarded, RunFact)
        start = len(before)
        end = start + len(secret)
        assert text[start:end] == secret
        rest = secret.removeprefix(span)
        span_end = start + len(span)
        span_sha = hashlib.sha256(span.encode("utf-8")).hexdigest()
        assert guarded.summary_en == f"{before}{_marker(rule, span)}{rest}{after}"
        assert guarded.redactions == [
            Redaction(field="summary_en", rule=rule, start=start, end=span_end, span_sha256=span_sha)
        ]
    else:
        assert kind == "agent"
        attr = field.split(":")[1]
        text = f"noted {pad_before} {secret} {pad_after} today"
        with pytest.raises(GuardRefusal) as caught:
            guard_record(_agent_record(field, text))
        assert caught.value.field == attr
        assert caught.value.rule == rule
        assert secret not in str(caught.value)
        assert text not in str(caught.value)
