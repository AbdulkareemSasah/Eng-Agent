"""Tests of the pull-request body parser (spec 4.5 body table)."""

from __future__ import annotations

from eng_dev_gate.checks.gate_check import parse_body


def test_keys_start_the_line_and_are_case_sensitive() -> None:
    body = (
        "Plan-Task: a#T1\n  Plan-Task: b#T1\nplan-task: c#T1\nText Plan-Task: d#T1\n"
        "Work-Item: B-1\nCloses #5\nCloses #x\n"
    )
    fields = parse_body(body)
    assert fields.plan_task == [(1, "a#T1")]
    assert fields.work_item == [(5, "B-1")]
    assert fields.closes == [(6, "5")]


def test_fenced_code_and_comments_are_ignored() -> None:
    body = (
        "```\nPlan-Task: in-fence#T1\n```\nPlan-Task: after#T1\n"
        "~~~~\nPlan-Task: tilde#T1\n~~~\nPlan-Task: still-in-fence#T1\n~~~~\nPlan-Task: after2#T1\n"
        "<!-- Plan-Task: one-line#T1 -->\n<!--\nPlan-Task: multi#T1\n-->\nPlan-Task: after3#T1\n"
        "<!-- a --> Plan-Task: not-at-start#T1\n"
    )
    assert [v for _, v in parse_body(body).plan_task] == ["after#T1", "after2#T1", "after3#T1"]


def test_unterminated_fence_hides_the_rest_and_crlf_is_handled() -> None:
    assert parse_body("```\nPlan-Task: a#T1\n").plan_task == []
    assert parse_body("Plan-Task: a#T1\r\nWork-Item: B-2\r\n").work_item == [(2, "B-2")]
    assert parse_body("").plan_task == []
