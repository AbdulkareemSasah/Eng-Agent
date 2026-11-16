"""Choice screens: the engineer turn, batched decisions, the engine's own requests and the read-only input screen
(plan 0006 T10; spec 0006 AC43 to AC46, AC49)."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path

from eng_contract.ids import FixedClock, SeededIdSource
from helpers.engine_standin import EngineStandIn, Wired, in_thread, until
from helpers.page_client import PageClient

from eng_harness.engine._inputs import Evidence, Kind, Question, build_request, choice_schema, data_schema
from eng_harness.pages import PageApprovalPort, PageInputPort, PageServer
from eng_harness.pages._answers import CHOICE
from eng_harness.pages._screens_choice import choice_screens
from eng_harness.ports import InputRequest

IDS = SeededIdSource(b"choice", FixedClock(1_767_225_600_000, 1))


@contextmanager
def rig(root: Path) -> Iterator[Wired]:
    """The page ports with the T10 screens, the stand-in engine feeding the sink, and a client."""
    builders, checks = choice_screens()
    approvals = PageApprovalPort(builders=builders, checks=checks, wait_timeout_s=0.5)
    engine = EngineStandIn(root, approvals.hub.emit)
    with PageServer(approvals.hub) as server:
        client = PageClient(server)
        client.open()
        try:
            yield Wired(approvals, PageInputPort(approvals), engine, client)
        finally:
            engine.close()


def ask(rid: str, kind: Kind, questions: list[Question], evidence: list[Evidence] | None = None) -> InputRequest:
    schema = choice_schema(questions, evidence or [])
    return build_request(IDS, rid, kind, "Choose <b>now</b>", schema, ())


def post(w: Wired, request: InputRequest, **fields: str) -> HTTPStatus:
    form = w.form(request, **fields)
    del form["decision"]
    return HTTPStatus(w.client.post(f"/answer/{request.request_id}", form).status)


def shown(w: Wired, request: InputRequest) -> str:
    until(lambda: w.approvals.hub.screen("request", request.request_id) is not None)
    return w.client.get(f"/request/{request.request_id}").body


def test_engineer_turn_three_options(tmp_path: Path) -> None:
    turn = ask(
        "dec_turn",
        "engine.decision",
        [Question(name="next", prompt="Next", options=("accept", "more_edits", "hand_edit"))],
    )
    with rig(tmp_path) as w:
        future = in_thread(w.engine.ask(w.inputs, turn))
        body = shown(w, turn)
        assert body.count("<button") == 3
        pressed = re.findall(r'<button [^>]*name="choice_next"[^>]*value="(\w+)"', body)
        assert pressed == ["accept", "more_edits", "hand_edit"]
        assert "Accept this revision" in body
        assert "Ask for more edits" in body
        assert "save the model in the host program first" in body  # the hand_edit label
        assert "<b>now</b>" not in body  # the title is data: escaped
        assert post(w, turn, **{CHOICE + "next": "hand_edit"}) == HTTPStatus.OK
        answered = future.result(5)
    assert answered is not None
    assert dict(answered.choices or {}) == {"next": "hand_edit"}  # one press, one option id and nothing else
    assert answered.values is None


def test_batched_decisions_one_submit(tmp_path: Path) -> None:
    questions = [Question(name=f"q{n}", prompt=f"Prompt {n}", options=("a", "b")) for n in (0, 1)]
    batch = ask(
        "dec_batch", "engine.decision", questions, [Evidence(name="e0", label="Why <i>q0", text="because <u>x</u>")]
    )
    with rig(tmp_path) as w:
        future = in_thread(w.engine.ask(w.inputs, batch))
        body = shown(w, batch)
        assert body.count("<form") == 1
        assert body.count('type="submit"') == 1
        assert body.count('type="radio"') == 4
        assert "Prompt 0" in body
        assert "Prompt 1" in body
        assert "because &lt;u&gt;x&lt;/u&gt;" in body  # the evidence, labeled, read-only and escaped
        assert "Why &lt;i&gt;q0" in body
        assert 'name="choice_e0"' not in body  # evidence is no field
        assert post(w, batch, **{CHOICE + "q0": "a"}) == HTTPStatus.BAD_REQUEST  # a question left open
        assert post(w, batch, **{CHOICE + "q0": "a", CHOICE + "q1": "zzz"}) == HTTPStatus.BAD_REQUEST  # outside it
        assert post(w, batch, **{CHOICE + "q0": "a", CHOICE + "q1": "b", CHOICE + "e0": "x"}) == HTTPStatus.BAD_REQUEST
        assert post(w, batch, **{CHOICE + "q0": "a", CHOICE + "q1": "b"}) == HTTPStatus.OK
        answered = future.result(5)
    assert answered is not None
    assert dict(answered.choices or {}) == {"q0": "a", "q1": "b"}


def test_engine_requests_choices(tmp_path: Path) -> None:
    kinds: dict[Kind, tuple[str, ...]] = {
        "engine.in_flight": ("applied", "not_applied", "abandon"),
        "engine.host_state": ("accept", "restore", "abandon"),
        "engine.escalation": ("abandon",),
    }
    with rig(tmp_path) as w:
        for kind, options in kinds.items():
            why = Evidence(name="why", label="Why the run stopped", text=f"reason of {kind}")
            request = ask(
                f"eng_{kind[7:]}", kind, [Question(name="next", prompt="How to go on", options=options)], [why]
            )
            future = in_thread(w.engine.ask(w.inputs, request))
            body = shown(w, request)
            assert f"reason of {kind}" in body
            assert body.count("<button") == len(options)
            assert re.findall(r'<button [^>]*value="(\w+)"', body) == list(options)
            assert "Abandon the run" in body
            assert post(w, request, **{CHOICE + "next": options[0]}) == HTTPStatus.OK
            assert future.result(5) is not None


def test_a_property_that_is_no_token_gives_a_refusal_screen(tmp_path: Path) -> None:
    bad = ask("dec_bad", "engine.decision", [Question(name="not a token", prompt="P", options=("a",))])
    odd = ask("dec_odd", "engine.decision", [Question(name="q", prompt="P", options=("a b",))])
    with rig(tmp_path) as w:
        for request in (bad, odd):
            future = in_thread(w.engine.ask(w.inputs, request))
            body = shown(w, request)
            assert "<form" not in body
            assert "<button" not in body
            assert "Choose &lt;b&gt;now&lt;/b&gt;" in body  # the error text is untrusted and escaped
            assert future.result(5) is None


def test_data_request_is_read_only(tmp_path: Path) -> None:
    schema = data_schema(
        {
            "type": "object",
            "properties": {
                "depth": {"type": "number", "unit": "mm", "minimum": 100, "maximum": 900.5},
                "name": {"type": "string", "maxLength": 20},
            },
        }
    )
    request = build_request(IDS, "inp_data", "block", "Values", schema, ())
    with rig(tmp_path) as w:
        future = in_thread(w.engine.ask(w.inputs, request))
        body = shown(w, request)
        assert "<form" not in body
        assert "<button" not in body
        assert "<input" not in body
        assert "provide the answers with" in body
        assert "resume --answers FILE" in body
        for cell in ("depth", "number", "mm", "minimum=100", "maximum=900.5", "name", "string", "maxLength=20"):
            assert cell in body
        refused = w.client.post("/answer/inp_data", {"shown_sha256": request.fields_schema_sha256, "by": "ada"})
        assert refused.status >= HTTPStatus.BAD_REQUEST  # no form, no token: nothing answers
        assert future.result(5) is None
