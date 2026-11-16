"""The choice screens and the read-only input screen (spec 0006 4.4.6; AC43 to AC45, AC46 page half, AC49).

Purpose: render an `InputRequest` from its JSON Schema. A schema whose `x-eng-input` is `data` is shown read-only, its
answer coming from `resume --answers FILE`; every other schema (marker `choice` or none, fail-safe) is a choice: a
property with an `enum` is a question, a property marked `x-eng-evidence` is labeled read-only text. One question gives
one button per option (one press is the answer); several give a radio group each and one Submit. Option labels come
from the catalog `pages/_labels`, never from data, except that an option without a catalog entry (a batched
decision's option) shows its own id, escaped and token-checked; evidence named `<question>_...` is shown under that
question, any other evidence before the questions; a property name or option that cannot be an attribute token makes
the screen a refusal screen (no form, no button). Units: as the schema gives them. Errors: a refused answer is an
`AnswerError`.
"""

from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import JsonValue

from eng_harness import _html as h
from eng_harness._html import Element, Node, SafeToken, Tag, Text, el
from eng_harness.engine._inputs import MARKER
from eng_harness.pages import _labels as lb
from eng_harness.pages._answers import CHOICE, AnswerError, Request, bound_sha256
from eng_harness.pages._ports import FormCheck, PageHub, ScreenBuilder
from eng_harness.pages._routes import Screen
from eng_harness.pages._screens_approval import _inline, _row, _show, _table
from eng_harness.pages._security import CSRF_FIELD, Subject
from eng_harness.ports import InputRequest

_KINDS = ("block", "engine.in_flight", "engine.host_state", "engine.escalation", "engine.decision")
_BOUNDS = (
    "minimum",
    "exclusiveMinimum",
    "maximum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
)
type _Props = Mapping[str, Mapping[str, JsonValue]]


def _props(schema: Mapping[str, JsonValue]) -> _Props:
    props = schema.get("properties")
    return {n: p for n, p in props.items() if isinstance(p, dict)} if isinstance(props, dict) else {}


def _asked(props: _Props) -> dict[str, list[JsonValue]]:
    """The questions, by property name: the properties with an `enum`."""
    return {n: o for n, p in props.items() if isinstance(o := p.get("enum"), list)}


def _unsafe(asked: Mapping[str, list[JsonValue]]) -> str | None:
    """What cannot be a form attribute: no question, a field name that is no token, an option that is no token."""
    for name, options in asked.items():
        for text in (CHOICE + name, *options):
            try:
                SafeToken(cast(str, text))
            except h.HtmlError:
                return str(text)
    return None if asked else "(no question)"


def _text(prop: Mapping[str, JsonValue], key: str) -> str:
    value = prop.get(key)
    return value if isinstance(value, str) else ""


def _label(option: str) -> Node:
    return lb.OPTIONS.get(option) or _inline(option)


def _hidden(name: str, value: str) -> Element:
    return el(Tag.INPUT, type=SafeToken("hidden"), name=SafeToken(name), value=SafeToken(value))


def _evidence(prop: Mapping[str, JsonValue]) -> Element:
    return el(Tag.P, _inline(_text(prop, "title")), h.field(lb.EVIDENCE, _text(prop, "default")))


def _data_rows(props: _Props) -> list[Element]:
    rows = []
    for name, prop in props.items():
        kind = prop.get("type")
        bounds = ", ".join(f"{k}={_show(prop[k])}" for k in _BOUNDS if k in prop)
        rows.append(_row(name, kind if isinstance(kind, str) else "(see schema)", _text(prop, "unit"), bounds))
    return rows


def _screen(hub: PageHub, request: Request) -> Screen:
    request = cast(InputRequest, request)
    subject = Subject("choice", request.request_id, bound_sha256(request))
    title = el(Tag.H1, h.field(lb.TITLE, request.title))
    props = _props(request.fields_schema)
    back = el(Tag.P, el(Tag.A, lb.BACK, href=h.href()))
    if request.fields_schema.get(MARKER) == "data":
        shown = [title, el(Tag.P, lb.INPUT_NOTE), _table(lb.INPUT_FIELDS, _data_rows(props)), back]
        return Screen(lb.TITLE, subject, frozenset(), lambda _: shown)
    raw = _asked(props)
    if (problem := _unsafe(raw)) is not None:
        refused = [title, el(Tag.P, h.field(lb.NOT_SHOWN, problem)), back]
        return Screen(lb.TITLE, subject, frozenset(), lambda _: refused)
    asked = {n: [o for o in options if isinstance(o, str)] for n, options in raw.items()}  # all are, after `_unsafe`
    refs = [el(Tag.LI, _inline(ref)) for ref in request.evidence]
    fields = frozenset({"shown_sha256", "by", *(CHOICE + name for name in asked)})
    owned = {
        e: next((q for q in asked if e.startswith(q + "_")), None) for e, p in props.items() if p.get("x-eng-evidence")
    }

    def render(token: str) -> list[Node]:
        groups: list[Node] = [_evidence(props[e]) for e, owner in owned.items() if owner is None]
        for name, options in asked.items():
            pick = SafeToken(CHOICE + name)
            if len(asked) == 1:  # one question: one button for each option, and a press answers
                group = [
                    el(Tag.BUTTON, _label(o), type=SafeToken("submit"), name=pick, value=SafeToken(o)) for o in options
                ]
            else:
                group = [
                    el(Tag.LABEL, el(Tag.INPUT, type=SafeToken("radio"), name=pick, value=SafeToken(o)), _label(o))
                    for o in options
                ]
            shown = [_evidence(props[e]) for e, owner in owned.items() if owner == name]
            groups += [el(Tag.H2, _inline(_text(props[name], "title"))), *shown, el(Tag.P, *group)]
        action = h.href(SafeToken("answer"), SafeToken(request.request_id))
        who = h.field(lb.NAME_PROPOSED, hub.engineer) if hub.engineer is not None else Text("")
        name_box = el(Tag.LABEL, lb.NAME, el(Tag.INPUT, type=SafeToken("text"), name=SafeToken("by")))
        submit = [] if len(asked) == 1 else [el(Tag.BUTTON, lb.SUBMIT, type=SafeToken("submit"))]
        form = el(
            Tag.FORM, _hidden(CSRF_FIELD, token), _hidden("shown_sha256", bound_sha256(request)),
            el(Tag.P, who, name_box), *groups, *submit, method=SafeToken("post"), action=action,
        )  # fmt: skip
        return [title, *([el(Tag.H2, lb.REFERENCES), el(Tag.UL, *refs)] if refs else []), form]

    return Screen(lb.TITLE, subject, fields, render)


def _check(hub: PageHub, request: Request, form: Mapping[str, str]) -> None:
    """Every question answered with one of its own options (AC44); nothing else is taken."""
    asked = _asked(_props(cast(InputRequest, request).fields_schema))
    given = {k.removeprefix(CHOICE): v for k, v in form.items() if k.startswith(CHOICE)}
    if given.keys() != asked.keys() or any(v not in asked[q] for q, v in given.items()):
        raise AnswerError("answer each question with one of its own options")


def choice_screens() -> tuple[dict[str, ScreenBuilder], dict[str, FormCheck]]:
    """The builders of the input requests (the hub's `builders`) and the check of a posted choice (its `checks`)."""
    kinds: Sequence[str] = _KINDS
    return dict.fromkeys(kinds, _screen), dict.fromkeys(kinds, _check)
