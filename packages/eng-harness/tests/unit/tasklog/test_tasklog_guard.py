"""Guard over owner words, agent fields and the gate-pinned vectors (plan 0015 T2; spec 0015 AC4-AC7, §4.4)."""

import ast
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from eng_contract.canonical import canonical_json
from pydantic import TypeAdapter

from eng_harness.tasklog._guard import GuardRefusalError, guard_record
from eng_harness.tasklog._records import OwnerWords, Redaction, TaskRecord

_TESTS = Path(__file__).resolve().parents[2]  # packages/eng-harness/tests
_ROOT = Path(__file__).resolve().parents[5]  # the workspace root
_VECTORS_PATH = _TESTS / "data" / "tasklog" / "secret_vectors.json"
_GATE_SECRETS = _ROOT / "tools" / "eng-dev-gate" / "src" / "eng_dev_gate" / "checks" / "secrets.py"
_GATE_TESTS = _ROOT / "tools" / "eng-dev-gate" / "tests" / "unit" / "test_secrets.py"
_VECTORS_SHA256 = "721e15a3a004b2d1a2c5290493583be98dc5955a2c1006e59858f7d16b4883c7"
_TASK_ID = "task_01KDVDNA00EEHMW00B9ZA4ZDSH"
_AT = "2026-11-14T10:00:00Z"
_ZERO_SHA = "0" * 64
_AGENT = "agent:test-tool"
_RECORDS = TypeAdapter(TaskRecord)


def _read_gate(path: Path) -> ast.Module | None:
    """Parse the gate file at `path`; None when it is absent under MUTANT_UNDER_TEST (spec 0015 §9)."""
    if not path.is_file() and "MUTANT_UNDER_TEST" in os.environ:
        return None
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_assigns(tree: ast.Module) -> dict[str, ast.expr]:
    """The name-bound module-level assignments of `tree`, annotated or plain."""
    found: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            found[node.target.id] = node.value
    return found


def _const_str(node: ast.expr, names: dict[str, str]) -> str:
    """Evaluate a gate string expression: constants, known names, `+` and str-times-int (no code runs)."""
    if isinstance(node, ast.Constant):
        assert isinstance(node.value, str)
        return node.value
    if isinstance(node, ast.Name):
        return names[node.id]
    assert isinstance(node, ast.BinOp)
    if isinstance(node.op, ast.Add):
        return _const_str(node.left, names) + _const_str(node.right, names)
    assert isinstance(node.op, ast.Mult)
    assert isinstance(node.right, ast.Constant)
    assert isinstance(node.right.value, int)
    return _const_str(node.left, names) * node.right.value


def _gate_samples() -> dict[str, tuple[str, str]] | None:
    """The gate's secret samples by test id, or None when its file is absent under MUTANT_UNDER_TEST."""
    tree = _read_gate(_GATE_TESTS)
    if tree is None:
        return None
    assigns = _module_assigns(tree)
    token = _const_str(assigns["GITHUB_TOKEN"], {})
    samples = assigns["SAMPLES"]
    assert isinstance(samples, ast.Dict)
    out: dict[str, tuple[str, str]] = {}
    for key, value in zip(samples.keys, samples.values, strict=True):
        assert isinstance(key, ast.Constant)
        assert isinstance(key.value, str)
        assert isinstance(value, ast.Tuple)
        assert len(value.elts) == 2
        rule_node = value.elts[0]
        assert isinstance(rule_node, ast.Constant)
        assert isinstance(rule_node.value, str)
        out[key.value] = (rule_node.value, _const_str(value.elts[1], {"GITHUB_TOKEN": token}))
    return out


def _gate_rule_patterns() -> dict[str, re.Pattern[str]] | None:
    """The gate's compiled secret patterns by rule, or None when its file is absent under MUTANT_UNDER_TEST."""
    tree = _read_gate(_GATE_SECRETS)
    if tree is None:
        return None
    assigns = _module_assigns(tree)
    user_node = assigns["_NAME"]
    assert isinstance(user_node, ast.Constant)
    assert isinstance(user_node.value, str)
    user = user_node.value
    rules = assigns["RULES"]
    assert isinstance(rules, ast.Call)
    assert isinstance(rules.func, ast.Name)
    assert rules.func.id == "tuple"
    assert len(rules.args) == 1
    generated = rules.args[0]
    assert isinstance(generated, ast.GeneratorExp)
    assert len(generated.generators) == 1
    pairs = generated.generators[0].iter
    assert isinstance(pairs, ast.Tuple)
    outer = generated.elt
    assert isinstance(outer, ast.Tuple)
    assert len(outer.elts) == 2
    compile_call = outer.elts[1]
    assert isinstance(compile_call, ast.Call)
    assert len(compile_call.args) == 2
    flags_expr = compile_call.args[1]
    assert isinstance(flags_expr, ast.IfExp)
    test = flags_expr.test
    assert isinstance(test, ast.Compare)
    assert isinstance(test.left, ast.Name)
    assert len(test.ops) == 1
    assert isinstance(test.ops[0], ast.Eq)
    assert len(test.comparators) == 1
    comparator = test.comparators[0]
    assert isinstance(comparator, ast.Constant)
    assert isinstance(comparator.value, str)
    body = flags_expr.body
    assert isinstance(body, ast.Attribute)
    assert isinstance(body.value, ast.Name)
    assert body.value.id == "re"
    flag_on = getattr(re, body.attr)
    assert isinstance(flag_on, int)
    flag_off = flags_expr.orelse
    assert isinstance(flag_off, ast.Constant)
    assert isinstance(flag_off.value, int)
    out: dict[str, re.Pattern[str]] = {}
    for pair in pairs.elts:
        assert isinstance(pair, ast.Tuple)
        assert len(pair.elts) == 2
        rule_node = pair.elts[0]
        assert isinstance(rule_node, ast.Constant)
        assert isinstance(rule_node.value, str)
        rule = rule_node.value
        pattern_node = pair.elts[1]
        if isinstance(pattern_node, ast.Constant):
            assert isinstance(pattern_node.value, str)
            pattern = pattern_node.value
        else:
            assert isinstance(pattern_node, ast.JoinedStr)
            chunks: list[str] = []
            for part in pattern_node.values:
                if isinstance(part, ast.Constant):
                    assert isinstance(part.value, str)
                    chunks.append(part.value)
                else:
                    assert isinstance(part, ast.FormattedValue)
                    assert isinstance(part.value, ast.Name)
                    assert part.value.id == "_NAME"
                    assert part.conversion == -1
                    assert part.format_spec is None
                    chunks.append(user)
            pattern = "".join(chunks)
        flags = flag_on if rule == comparator.value else flag_off.value
        out[rule] = re.compile(pattern, flags)
    return out


def _load_vectors() -> list[dict[str, Any]]:
    """The guard's vector file: gate samples split into parts (joined at run time, never as literals)."""
    raw: Any = json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    vectors = raw["vectors"]
    assert isinstance(vectors, list)
    for vector in vectors:
        assert isinstance(vector, dict)
        assert isinstance(vector["id"], str)
        assert isinstance(vector["rule"], str)
        assert isinstance(vector["parts"], list)
        for part in vector["parts"]:
            assert isinstance(part, str)
    return vectors


_VECTORS = _load_vectors()


def _vector(vector_id: str) -> tuple[str, str]:
    """The (rule, joined sample) of one vector."""
    matches = [vector for vector in _VECTORS if vector["id"] == vector_id]
    assert len(matches) == 1
    found = matches[0]
    return found["rule"], "".join(found["parts"])


def _owner_words(text: str) -> OwnerWords:
    """An owner_words record whose text_sha256 is the SHA-256 of the input bytes (spec 0015 §4.3)."""
    payload: dict[str, Any] = {
        "schema": "harness.tasklog_record/1",
        "task_id": _TASK_ID,
        "seq": 1,
        "at": _AT,
        "kind": "owner_words",
        "by": _AGENT,
        "policy": "full",
        "redactions": [],
        "prev_sha256": _ZERO_SHA,
        "role": "request",
        "lang": "ar",
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    record = _RECORDS.validate_python(payload)
    assert isinstance(record, OwnerWords)
    return record


def _narration(text_en: str) -> TaskRecord:
    """A narration record carrying `text_en` (an agent field, refused on a hit; spec 0015 §4.4)."""
    return _RECORDS.validate_python(
        {
            "schema": "harness.tasklog_record/1",
            "task_id": _TASK_ID,
            "seq": 1,
            "at": _AT,
            "kind": "narration",
            "by": _AGENT,
            "policy": "full",
            "redactions": [],
            "prev_sha256": _ZERO_SHA,
            "text_en": text_en,
        }
    )


def _marker(rule: str, span: str) -> str:
    """The expected marker: the rule and the 12-digit fingerprint of the span (spec 0015 §4.4)."""
    return f"<withheld:{rule}:{hashlib.sha256(span.encode('utf-8')).hexdigest()[:12]}>"


def test_owner_secret_withheld_not_dropped() -> None:
    """AC4: a hard secret in owner words is withheld with a marker and entry; record and hash stay (spec 0015 §4.4)."""
    rule, secret = _vector("github-token")
    before = "من فضلك نفذ المطلوب هنا: "
    after = " وشكرا لك"
    text = f"{before}{secret}{after}"
    guarded = guard_record(_owner_words(text))
    assert isinstance(guarded, OwnerWords)
    start = len(before)
    end = start + len(secret)
    assert text[start:end] == secret
    assert guarded.text == f"{before}{_marker(rule, secret)}{after}"
    assert guarded.text_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert guarded.redactions == [
        Redaction(
            field="text",
            rule=rule,
            start=start,
            end=end,
            span_sha256=hashlib.sha256(secret.encode("utf-8")).hexdigest(),
        )
    ]


def test_owner_personal_path_withheld() -> None:
    """AC5: a personal path in owner words is withheld; the stored line passes the gate rule (spec 0015 §4.4, §4.2)."""
    patterns = _gate_rule_patterns()
    rests = {"posix-path": "work", "mac-path": "work", "windows-path": ""}
    paths = [vector for vector in _VECTORS if vector["rule"] == "personal-path"]
    assert len(paths) == 3
    for vector in paths:
        sample = "".join(vector["parts"])
        rest = rests[vector["id"]]
        span = sample.removesuffix(rest)
        before = "my project is in "
        after = " please use it"
        text = f"{before}{sample}{after}"
        guarded = guard_record(_owner_words(text))
        assert isinstance(guarded, OwnerWords)
        start = len(before)
        end = start + len(span)
        assert guarded.text == f"{before}{_marker('personal-path', span)}{rest}{after}"
        assert guarded.text_sha256 == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert guarded.redactions == [
            Redaction(
                field="text",
                rule="personal-path",
                start=start,
                end=end,
                span_sha256=hashlib.sha256(span.encode("utf-8")).hexdigest(),
            )
        ]
        line = canonical_json(_RECORDS.dump_python(guarded, mode="json")).decode("utf-8")
        assert sample not in line
        if patterns is not None:
            assert patterns["personal-path"].search(line) is None


def test_agent_secret_refused_no_echo() -> None:
    """AC6: a secret in an agent *_en field is refused naming field and rule, never the text (spec 0015 §4.4)."""
    rule, secret = _vector("github-token")
    text = f"noted {secret} today for the record"
    with pytest.raises(GuardRefusalError) as caught:
        guard_record(_narration(text))
    assert caught.value.field == "text_en"
    assert caught.value.rule == rule
    assert "text_en" in str(caught.value)
    assert rule in str(caught.value)
    assert secret not in str(caught.value)
    assert text not in str(caught.value)
    assert "noted" not in str(caught.value)


def test_guard_vectors_match_gate() -> None:
    """AC7: the vectors equal the gate samples, pinned by hash; the guard catches each both ways (§4.4, §2)."""
    gate = _gate_samples()
    joined = {vector["id"]: (vector["rule"], "".join(vector["parts"])) for vector in _VECTORS}
    assert len(joined) == len(_VECTORS)
    if gate is not None:
        assert joined == gate
    pinned = canonical_json(
        {"vectors": [{"id": vid, "rule": rule, "text": text} for vid, (rule, text) in joined.items()]}
    )
    assert hashlib.sha256(pinned).hexdigest() == _VECTORS_SHA256
    for vid, (rule, sample) in joined.items():
        owner_text = f"please handle {sample} now"
        guarded = guard_record(_owner_words(owner_text))
        assert isinstance(guarded, OwnerWords), vid
        assert f"<withheld:{rule}:" in guarded.text, vid
        assert guarded.text_sha256 == hashlib.sha256(owner_text.encode("utf-8")).hexdigest(), vid
        assert len(guarded.redactions) == 1, vid
        assert guarded.redactions[0].rule == rule, vid
        assert sample not in guarded.text, vid
        agent_text = f"noted {sample} today"
        with pytest.raises(GuardRefusalError) as caught:
            guard_record(_narration(agent_text))
        assert caught.value.rule == rule, vid
        assert caught.value.field == "text_en", vid
        assert sample not in str(caught.value), vid
