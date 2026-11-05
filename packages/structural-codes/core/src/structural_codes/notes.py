"""Calculation notes: one self-contained HTML5 document per `verdicts.set/1` payload (spec 0001 section 4.10).

Purpose: show per trace the inputs, constants, steps and verdicts so that an engineer can check the calculation.
Units: values are shown with the unit of the payload; numbers use the shortest round-trip `repr`, never rounded (Q8).
Errors: `ContractError` (`NOT_FOUND`) when a trace names a check the registry does not hold.
"""

import json
from collections.abc import Sequence
from html import escape

from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.quantity import Quantity
from eng_contract.trace import Trace
from eng_contract.verdicts import Subject, Verdict

from structural_codes._labels import arabic_span, label
from structural_codes.pack import Registry

_CSS = (
    "body{font-family:sans-serif;margin:2em}table{border-collapse:collapse;margin:.5em 0}"
    "td,th{border:1px solid #888;padding:.2em .5em;text-align:left}"
    ".watermark{position:fixed;top:40%;left:20%;font-size:6em;color:#ddd;transform:rotate(-30deg);z-index:-1}"
)


def _e(text: object) -> str:
    return escape(str(text), quote=True)


def _num(value: object) -> str:
    """Show a payload value: numbers by `repr`, strings as written, structures as sorted JSON."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float):
        return repr(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _qty(quantity: Quantity | None) -> str:
    return "" if quantity is None else _e(f"{_num(quantity.value)} {quantity.unit}")


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _subject(subject: Subject | None) -> str:
    if subject is None:
        return ""
    parts = [subject.kind.value, subject.id]
    if subject.station_mm is not None:
        parts.append(f"station {_num(subject.station_mm)} mm")
    if subject.case is not None:
        parts.append(f"case {subject.case}")
    return _e(" ".join(parts))


def _verdicts(verdicts: Sequence[Verdict]) -> str:
    rows = [
        [
            label(v.status.value),
            _qty(v.demand),
            _qty(v.capacity),
            "" if v.ratio is None else _e(_num(v.ratio)),
            _e(_num(v.ratio_limit)),
            "yes" if v.governing else "no",
            _e("; ".join(v.assumptions)),
        ]
        for v in verdicts
    ]
    headers = [label(k) for k in ("Status", "Demand", "Capacity", "Ratio")]
    return _table([*headers, "Ratio limit", "Governing", label("Assumptions")], rows)


def _trace_section(trace: Trace, verdicts: Sequence[Verdict], registry: Registry) -> str:
    meta = registry.get(trace.calc_id).meta
    subject = trace.subject or (verdicts[0].subject if verdicts else None)
    title_ar = f' <span lang="ar" dir="rtl">{_e(meta.title_ar)}</span>' if meta.title_ar else ""
    parts = [
        f"<section><h2>{_e(meta.title)}{title_ar}</h2>",
        f"<p>{_e(trace.calc_id)} · {_e(meta.code)} {_e(meta.edition)} · {label('Clause')} "
        f"{_e(', '.join(meta.clauses))} · {label('Subject')} {_subject(subject)}</p>",
        f"<h3>{label('Inputs')}</h3>",
        _table(
            ["Name", "Value", "Unit", "Reference"],
            [[_e(i.name), _e(_num(i.value)), _e(i.unit or ""), _e(i.ref or "")] for i in trace.inputs],
        ),
        f"<h3>{label('Constants')}</h3>",
        _table(
            ["Name", "Value", "Unit", label("Source")],
            [[_e(c.name), _e(_num(c.cited.value)), _e(c.cited.unit), _e(c.cited.source)] for c in trace.constants],
        ),
        f"<h3>{label('Calculation steps')}</h3>",
        _table(
            ["Name", "Value", "Unit", "Formula", label("Source"), "Uses"],
            [
                [_e(s.name), _e(_num(s.value)), _e(s.unit or ""), _e(s.formula), _e(s.source), _e(", ".join(s.uses))]
                for s in trace.steps
            ],
        ),
        f"<h3>{label('Verdicts')}</h3>",
        _verdicts(verdicts),
        "".join(f"<p>{_e(m)}</p>" for m in trace.messages),
        "</section>",
    ]
    return "".join(parts)


def render_html(payload: VerdictSet, *, registry: Registry, result_id: str | None = None) -> str:
    """Render a calculation note as one HTML5 document (inline CSS, no script, no external resource).

    Every engineering value comes from `payload`; `registry` supplies titles and clause numbers. Text is escaped with
    `html.escape(quote=True)`. A `DRAFT` watermark is shown when `payload.draft` is true. The output is deterministic.

    Args:
        payload: the `verdicts.set/1` payload, with its traces.
        registry: holds the checks that the traces name.
        result_id: the id of the result record, shown in the heading when given.

    Raises:
        ContractError: code `NOT_FOUND` when a trace names a check that `registry` does not hold.
    """
    sections = [
        _trace_section(trace, [v for v in payload.verdicts if v.trace_ref == f"#/traces/{index}"], registry)
        for index, trace in enumerate(payload.traces)
    ]
    loose = [v for v in payload.verdicts if v.trace_ref is None]
    if loose:
        sections.append(f"<section><h3>{label('Verdicts')}</h3>{_verdicts(loose)}</section>")
    mark = f'<div class="watermark">DRAFT {arabic_span("Draft")}</div>' if payload.draft else ""
    heading = f"<h1>Calculation note{'' if result_id is None else ' ' + _e(result_id)}</h1>"
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><title>Calculation note</title>'
        f"<style>{_CSS}</style></head><body>{mark}{heading}{''.join(sections)}</body></html>\n"
    )
