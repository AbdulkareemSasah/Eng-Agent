"""Tests of the spec and plan front matter (spec section 5; AC13)."""

from __future__ import annotations

import pytest
from eng_dev_gate.frontmatter import (
    FrontMatterError,
    parse_plan,
    parse_spec,
    safe_relative_path,
    uncovered_criteria,
)
from support.pullrequest import plan_text, spec_text

CAP = 400


def _task(task_id: str, **fields: str) -> str:
    values = {
        "title": "t",
        "files": '["a/**"]',
        "max_changed_lines": "100",
        "max_sessions": "2",
        "tests_first": "[]",
        "covers": "[AC1]",
        "depends_on": "[]",
        **fields,
    }
    return f"  - id: {task_id}\n" + "".join(f"    {k}: {v}\n" for k, v in values.items())


def _plan(tasks: str, **header: str) -> str:
    values = {
        "id": "p",
        "issue": '"B-1"',
        "spec": "a/docs/specs/s.md",
        "status": "draft",
        "size": "small",
        "risk": "r1",
    }
    values.update(header)
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in values.items()) + "tasks:\n" + tasks + "---\n\nbody\n"


def test_valid_plan_and_spec() -> None:
    """A plan and a spec parse; risk is one class or a list; issue may be a number or a string."""
    plan = parse_plan(plan_text(), CAP)
    assert [t.id for t in plan.tasks] == ["T1", "T2"]
    assert plan.tasks[0].files == ["pkg/src/**"]
    assert plan.tasks[0].max_changed_lines == 10
    assert (plan.status, plan.risk, plan.spec) == ("approved", ["r1"], "pkg/docs/specs/0001-x.md")
    assert parse_plan(_plan(_task("T2a"), risk="[r1, r3]", issue="42"), CAP).risk == ["r1", "r3"]
    spec = parse_spec(spec_text("draft"))
    assert (spec.status, spec.size, spec.risk) == ("draft", "small", ["r1"])


@pytest.mark.parametrize(
    "text",
    [
        "no front matter\n",
        "---\nid: x\n",  # not closed
        "---\n- a\n- b\n---\n",  # not a mapping
        "---\nid: [unclosed\n---\n",  # not YAML
        "",
    ],
)
def test_front_matter_must_be_a_yaml_mapping_between_dashes(text: str) -> None:
    """A document without a closed YAML mapping at its start is invalid."""
    with pytest.raises(FrontMatterError):
        parse_spec(text)
    with pytest.raises(FrontMatterError):
        parse_plan(text, CAP)


def test_crlf_front_matter() -> None:
    """Line endings are normalized: a CRLF file parses like an LF file."""
    assert parse_plan(plan_text().replace("\n", "\r\n"), CAP).id == "plan-1"


def test_plan_front_matter_rules() -> None:
    """AC13: invalid fields, repeated task ids, unknown or cyclic depends_on and an oversized task are rejected."""
    bad_header = [
        {"status": "maybe"},
        {"size": "huge"},
        {"risk": "r4"},
        {"risk": "[]"},
        {"id": '""'},
        {"spec": "../escape.md"},
        {"spec": "/abs/spec.md"},
    ]
    for header in bad_header:
        with pytest.raises(FrontMatterError):
            parse_plan(_plan(_task("T1"), **header), CAP)
    bad_task = [
        {"files": "[]"},
        {"files": '[""]'},
        {"max_changed_lines": "0"},
        {"max_changed_lines": '"12"'},
        {"max_sessions": "-1"},
        {"max_sessions": "true"},
        {"covers": "[X1]"},
        {"depends_on": "[T"},
        {"title": '""'},
        {"surprise": "1"},
    ]
    for fields in bad_task:
        with pytest.raises(FrontMatterError):
            parse_plan(_plan(_task("T1", **fields)), CAP)
    with pytest.raises(FrontMatterError, match="id"):
        parse_plan(_plan(_task("task-1")), CAP)
    with pytest.raises(FrontMatterError):
        parse_plan(_plan(""), CAP)
    with pytest.raises(FrontMatterError, match="T1"):
        parse_plan(_plan(_task("T1") + _task("T1")), CAP)
    with pytest.raises(FrontMatterError, match="T9"):
        parse_plan(_plan(_task("T1", depends_on="[T9]")), CAP)
    with pytest.raises(FrontMatterError, match="cycl"):
        parse_plan(
            _plan(_task("T1", depends_on="[T2]") + _task("T2", depends_on="[T3]") + _task("T3", depends_on="[T1]")), CAP
        )
    with pytest.raises(FrontMatterError, match="cycl"):
        parse_plan(_plan(_task("T1", depends_on="[T1]")), CAP)
    with pytest.raises(FrontMatterError, match="400"):
        parse_plan(_plan(_task("T1", max_changed_lines="401")), CAP)
    ok = _plan(
        _task("T1", max_changed_lines="400") + _task("T2", depends_on="[T1]") + _task("T3", depends_on="[T1, T2]")
    )
    assert len(parse_plan(ok, CAP).tasks) == 3


def test_spec_front_matter_rules() -> None:
    """A spec needs id, issue, status, size and risk with valid values."""
    for broken in (
        spec_text().replace("status: approved", "status: done"),
        spec_text().replace("size: small\n", ""),
        spec_text().replace("risk: r1", "risk: r9"),
    ):
        with pytest.raises(FrontMatterError):
            parse_spec(broken)


def test_uncovered_criteria() -> None:
    """AC13 (GC016): acceptance criteria of the spec (`AC<n>.` lines, including AC5a) missing from every `covers`."""
    spec = (
        "---\nx: 1\n---\n- AC1. Given a\n- AC2. Given b\n- AC5a. Given c\nAC7. bare line\n"
        "| AC9. in a table |\nAC10 no dot\n"
    )
    plan = parse_plan(_plan(_task("T1", covers="[AC1, AC7]") + _task("T2", covers="[AC5a]")), CAP)
    assert uncovered_criteria(plan, spec) == ["AC2"]
    full = parse_plan(_plan(_task("T1", covers="[AC1, AC2, AC5a, AC7]")), CAP)
    assert uncovered_criteria(full, spec) == []


@pytest.mark.parametrize(
    ("path", "ok"),
    [
        ("a/docs/plans/x.md", True),
        ("x.md", True),
        ("../x.md", False),
        ("a/../x.md", False),
        ("/x.md", False),
        ("a\\x.md", False),
        ("", False),
        ("./x.md", False),
        ("a//x.md", False),
    ],
)
def test_safe_relative_path(path: str, ok: bool) -> None:
    """Plan and spec paths are workspace-relative POSIX paths without `..`, absolute or backslash forms."""
    assert safe_relative_path(path) is ok
