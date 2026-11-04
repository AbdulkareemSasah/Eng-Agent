"""References, JSON Pointer and resolution rules (plan T8; spec 4.6; AC23 to AC28).

Expected values come from RFC 6901 (pointer syntax and evaluation, sections 3, 4 and 5) and from the examples and
rules of spec 4.6, not from the implementation.
"""

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from eng_contract.errors import ContractError, ErrorCode
from eng_contract.ids import FixedClock, SeededIdSource
from eng_contract.records import ResultRecord
from eng_contract.refs import (
    JsonPointer,
    LocalTraceRef,
    Ref,
    RefRule,
    RefString,
    parse_ref,
    rebase_local_ref,
    resolve_ref,
)

RID = "res_01ARZ3NDEKTSV4RRFFQ69G5FAV"
MID = "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV"
TS = "2026-01-02T03:04:05.678Z"
MISSING = "res_01ARZ3NDEKTSV4RRFFQ69G5FAW"

PAYLOAD: dict[str, Any] = {
    "b_mm": 300,
    "h_mm": {"value": 500, "unit": "mm", "label": "depth"},
    "fc_MPa": {"value": 25, "unit": "kPa"},
    "plain": 7,
    "a/b": [10, {"x": 1}],
    "m~n": "tilde",
    "": "empty key",
    "name": "text",
    "loads": {"w_kN_m": [1.5, 2.5]},
    "members": [{"Fy_MPa": 420, "tag": 3}],
    "flag": True,
    "nothing": None,
}


def record(
    *, rid: str = RID, kind: str = "model.sections/1", payload: dict[str, Any] | None = PAYLOAD, host: int | None = None
) -> ResultRecord:
    producer: dict[str, Any] = {"tool": "harness", "tool_version": "1", "inputs": {}, "started_at": TS, "duration_ms": 0}
    if host is not None:
        producer["host"] = {"program": "ETABS", "version": "1", "model_id": MID, "model_revision": host}
    return ResultRecord.model_validate(
        {
            "contract": "eng-contract/1",
            "result_id": rid,
            "kind": kind,
            "created_at": TS,
            "units": "canonical/1",
            "complete": True,
            "producer": producer,
            "parents": [],
            "payload_sha256": "b" * 64,
            "payload": payload,
            "payload_file": None if payload is not None else f"{rid}.payload.json.gz",
        }
    )


class MemorySource:
    """In-memory `RecordSource`: a missing id raises `REF_NOT_FOUND`, as the store does (spec 4.5.3)."""

    def __init__(self, *records: ResultRecord, split: dict[str, Any] | None = None) -> None:
        self.records = {r.result_id: r for r in records}
        self.split = split

    def get(self, result_id: str) -> ResultRecord:
        if result_id not in self.records:
            raise ContractError(ErrorCode.REF_NOT_FOUND, f"no result {result_id}")
        return self.records[result_id]

    def payload(self, result_id: str) -> dict[str, Any]:
        assert self.split is not None
        return self.split


def untracked(_: str) -> int | None:
    return None


def resolve(
    text: str,
    rule: RefRule | None = None,
    source: MemorySource | None = None,
    revision: Callable[[str], int | None] = untracked,
) -> Any:
    return resolve_ref(
        text,
        rule or RefRule(),
        source or MemorySource(record()),
        revision,
        ids=SeededIdSource(b"t", FixedClock(1_700_000_000_000)),
    )


def code_of(exc: pytest.ExceptionInfo[ContractError]) -> ErrorCode:
    return exc.value.detail.code


def test_parse() -> None:
    assert parse_ref(RID) == (RID, ())
    assert parse_ref(RID + "#") == (RID, ())
    assert parse_ref(RID + "#/a~1b/0") == (RID, ("a/b", "0"))
    assert parse_ref(RID + "#/m~0n") == (RID, ("m~n",))
    assert parse_ref(RID + "#/~01") == (RID, ("~1",))  # ~01 is ~ then 1, not a slash (RFC 6901 section 4)
    assert parse_ref(RID + "#/") == (RID, ("",))
    assert parse_ref(RID + "#/a#b") == (RID, ("a#b",))  # no percent or fragment decoding
    assert parse_ref(RID + "#/%41") == (RID, ("%41",))
    for bad in ("res_bad", "", "mdl_01ARZ3NDEKTSV4RRFFQ69G5FAV", "res_bad#/a", " " + RID, RID + "x", "res_" + "8" * 26):
        with pytest.raises(ContractError) as err:
            parse_ref(bad)
        assert code_of(err) is ErrorCode.INVALID_ARGUMENT
    for bad_pointer in ("#a", "#/x~2", "#/x~", "#~0", "#x/y", "#/a/~"):
        with pytest.raises(ContractError) as err:
            parse_ref(RID + bad_pointer)
        assert code_of(err) is ErrorCode.REF_POINTER_INVALID
        assert err.value.detail.retryable is False
    with pytest.raises(ContractError) as err:
        parse_ref(RID + "#/" + "a" * 2000)
    assert code_of(err) is ErrorCode.INVALID_ARGUMENT


def test_parse_field_is_reported() -> None:
    with pytest.raises(ContractError) as err:
        parse_ref(RID + "#a", field="b_mm")
    assert err.value.detail.field == "b_mm"
    with pytest.raises(ContractError) as err:
        parse_ref("res_bad", field="b_mm")
    assert err.value.detail.field == "b_mm"


def test_json_pointer_format_and_rfc_examples() -> None:
    assert JsonPointer.format(("a/b", "m~n", "~1", "")) == "/a~1b/m~0n/~01/"
    assert JsonPointer.format(()) == ""
    assert JsonPointer.parse("") == ()
    assert JsonPointer.parse("/a~1b/m~0n") == ("a/b", "m~n")
    # RFC 6901 section 5 document and its evaluations.
    doc = {
        "foo": ["bar", "baz"],
        "": 0,
        "a/b": 1,
        "c%d": 2,
        "e^f": 3,
        "g|h": 4,
        "i\\j": 5,
        'k"l': 6,
        " ": 7,
        "m~n": 8,
    }
    expected = {
        "": doc,
        "/foo": ["bar", "baz"],
        "/foo/0": "bar",
        "/": 0,
        "/a~1b": 1,
        "/c%d": 2,
        "/e^f": 3,
        "/g|h": 4,
        "/i\\j": 5,
        '/k"l': 6,
        "/ ": 7,
        "/m~0n": 8,
    }
    for text, value in expected.items():
        assert JsonPointer.evaluate(doc, JsonPointer.parse(text)) == value


def test_ref_model() -> None:
    ref = Ref.model_validate({"$ref": RID + "#/a"})
    assert ref.ref == RID + "#/a"
    assert ref.model_dump() == {"$ref": RID + "#/a"}
    for bad in ({}, {"ref": RID}, {"$ref": RID, "x": 1}, {"$ref": "res_bad"}, {"$ref": 5}):
        with pytest.raises(ValidationError):
            Ref.model_validate(bad)
    adapter = TypeAdapter(RefString)
    assert adapter.validate_python(RID) == RID
    assert adapter.validate_python(RID + "#") == RID + "#"
    assert adapter.validate_python(RID + "#/a\nb") == RID + "#/a\nb"
    for bad_text in ("res_bad", RID + "x", "#/a", RID + "#" + "a" * 2000):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad_text)


def test_local_trace_ref() -> None:
    adapter = TypeAdapter(LocalTraceRef)
    assert adapter.validate_python("#/traces/0") == "#/traces/0"
    assert adapter.validate_python("#/traces/12") == "#/traces/12"
    for bad in ("#/traces/01", "#/traces/", "#/traces/-1", "#/trace/0", "/traces/0", "#/traces/0/x", RID + "#/traces/0"):
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)
    rebased = rebase_local_ref(RID, "#/traces/3")
    assert rebased == RID + "#/traces/3"
    assert parse_ref(rebased) == (RID, ("traces", "3"))
    with pytest.raises(ContractError) as err:
        rebase_local_ref("res_bad", "#/traces/3")
    assert code_of(err) is ErrorCode.INVALID_ARGUMENT
    with pytest.raises(ContractError) as err:
        rebase_local_ref(RID, "#/other/3")
    assert code_of(err) is ErrorCode.REF_POINTER_INVALID


def test_resolve_whole_payload_and_value() -> None:
    whole = resolve(RID)
    assert whole.value == PAYLOAD
    assert whole.ref == RID
    assert resolve(RID + "#").value == PAYLOAD
    got = resolve(RID + "#/a~1b/1/x")
    assert got.value == 1
    assert (got.result_id, got.record_kind, got.model_id, got.model_revision) == (RID, "model.sections/1", None, None)
    assert got.ref == RID + "#/a~1b/1/x"
    assert resolve(RID + "#/m~0n").value == "tilde"
    assert resolve(RID + "#/").value == "empty key"
    assert resolve(RID + "#/nothing").value is None
    assert resolve(RID + "#/flag").value is True
    assert resolve(RID + "#/a~1b/0").value == 10
    assert resolve(Ref.model_validate({"$ref": RID + "#/name"})).value == "text"


def test_pointer_failures() -> None:
    cases = {
        "#/missing": "missing",
        "#/a~1b/2": "2",  # index out of range
        "#/a~1b/01": "01",  # leading zero
        "#/a~1b/-": "-",  # the element after the last
        "#/a~1b/x": "x",  # not an index
        "#/a~1b/+1": "+1",
        "#/a~1b/١": "١",  # Arabic-Indic digit one is not an RFC 6901 digit
        "#/b_mm/x": "x",  # token applied to a number
        "#/name/0": "0",  # token applied to a string
        "#/flag/x": "x",
        "#/nothing/x": "x",
        "#/members/0/tag/x": "x",
    }
    for pointer, token in cases.items():
        with pytest.raises(ContractError) as err:
            resolve(RID + pointer, RefRule(field="b_mm"))
        detail = err.value.detail
        assert detail.code is ErrorCode.REF_POINTER_INVALID, pointer
        assert detail.retryable is False
        assert detail.field == "b_mm"
        assert detail.received == token
    with pytest.raises(ContractError) as err:
        resolve(RID + "#bad")
    assert code_of(err) is ErrorCode.REF_POINTER_INVALID


def test_pointer_reaches_payload_not_envelope() -> None:
    for pointer in ("#/payload", "#/kind", "#/result_id", "#/producer/tool"):
        with pytest.raises(ContractError) as err:
            resolve(RID + pointer)
        assert code_of(err) is ErrorCode.REF_POINTER_INVALID


def test_not_found() -> None:
    with pytest.raises(ContractError) as err:
        resolve(MISSING + "#/b_mm", RefRule(field="b_mm"))
    detail = err.value.detail
    assert detail.code is ErrorCode.REF_NOT_FOUND
    assert detail.retryable is False
    assert detail.field == "b_mm"
    assert detail.received == MISSING + "#/b_mm"
    with pytest.raises(ContractError) as err:
        resolve("res_bad")
    assert code_of(err) is ErrorCode.INVALID_ARGUMENT


def test_other_source_errors_propagate() -> None:
    class Broken(MemorySource):
        def get(self, result_id: str) -> ResultRecord:
            raise ContractError(ErrorCode.INTERNAL, "corrupt record", incident_id="inc-1")

    with pytest.raises(ContractError) as err:
        resolve(RID, source=Broken())
    assert err.value.detail.code is ErrorCode.INTERNAL
    assert err.value.detail.incident_id == "inc-1"


def test_split_payload_is_read_from_the_source() -> None:
    source = MemorySource(record(payload=None), split={"h": {"v": [4, 5]}})
    assert resolve(RID + "#/h/v/1", source=source).value == 5


def test_kind_mismatch() -> None:
    rule = RefRule(kinds=frozenset({"model.sections/1"}), field="section")
    assert resolve(RID, rule).value == PAYLOAD
    assert resolve(RID + "#/b_mm", rule).value == 300
    other = MemorySource(record(kind="forces.member_end/1"))
    for text in (RID, RID + "#/b_mm"):
        with pytest.raises(ContractError) as err:
            resolve(text, rule, other)
        detail = err.value.detail
        assert detail.code is ErrorCode.REF_KIND_MISMATCH
        assert detail.expected == {"kinds": ["model.sections/1"]}
        assert detail.field == "section"
        assert detail.retryable is False
    many = RefRule(kinds=frozenset({"model.sections/1", "forces.member_end/1"}))
    assert resolve(RID, many, other).record_kind == "forces.member_end/1"
    with pytest.raises(ContractError) as err:
        resolve(RID, RefRule(kinds=frozenset({"model.sections/2", "model.info/1"})))
    assert err.value.detail.expected == {"kinds": ["model.info/1", "model.sections/2"]}
    assert resolve(RID, RefRule(kinds=frozenset())).value == PAYLOAD  # empty means any kind
    # The kind is checked before the pointer is evaluated (first failure wins).
    with pytest.raises(ContractError) as err:
        resolve(RID + "#/missing", rule, other)
    assert code_of(err) is ErrorCode.REF_KIND_MISMATCH


def test_unit_mismatch() -> None:
    mm = RefRule(unit="mm", field="b_mm")
    assert resolve(RID + "#/b_mm", mm).value == 300  # bare number under a key with the unit's suffix
    assert resolve(RID + "#/h_mm", mm).value == PAYLOAD["h_mm"]  # quantity object with the exact unit
    assert resolve(RID + "#/h_mm/value", mm).value == 500  # nearest suffixed key is h_mm
    assert resolve(RID + "#/members/0/Fy_MPa", RefRule(unit="MPa")).value == {"Fy_MPa": 420, "tag": 3}["Fy_MPa"]
    assert resolve(RID + "#/loads/w_kN_m/1", RefRule(unit="kN/m")).value == 2.5  # index skipped, w_kN_m found
    assert resolve(RID + "#/name", mm).value == "text"  # other values are left to shape validation
    assert resolve(RID + "#/a~1b", mm).value == PAYLOAD["a/b"]
    assert resolve(RID + "#/flag", mm).value is True
    assert resolve(RID + "#/nothing", mm).value is None
    assert resolve(RID, mm).value == PAYLOAD
    assert resolve(RID + "#/plain", RefRule()).value == 7  # no unit on the rule: nothing to check
    cases = [
        (RID + "#/h_mm", RefRule(unit="m"), PAYLOAD["h_mm"]),  # wrong unit, same dimension
        (RID + "#/fc_MPa", RefRule(unit="MPa"), PAYLOAD["fc_MPa"]),  # kPa object for an MPa parameter
        (RID + "#/b_mm", RefRule(unit="m"), 300),  # bare number under _mm for a metre parameter
        (RID + "#/b_mm", RefRule(unit="MPa"), 300),  # different dimension
        (RID + "#/plain", mm, 7),  # bare number under no unit-suffixed key
        (RID + "#/members/0/tag", mm, 3),
        (RID + "#/a~1b/0", mm, 10),  # array element under a key with no suffix
        (RID + "#/loads/w_kN_m/0", RefRule(unit="kN/m3"), 1.5),  # _kN_m is not _kN_m3
    ]
    for text, rule, received in cases:
        with pytest.raises(ContractError) as err:
            resolve(text, rule.model_copy(update={"field": "b_mm"}))
        detail = err.value.detail
        assert detail.code is ErrorCode.REF_UNIT_MISMATCH, text
        assert detail.expected == {"unit": rule.unit}
        assert detail.received == received
        assert detail.field == "b_mm"
        assert detail.retryable is False


def test_dimensionless_unit() -> None:
    source = MemorySource(record(payload={"ratio_ratio": 0.5, "k": 2}))
    assert resolve(RID + "#/ratio_ratio", RefRule(unit="1"), source).value == 0.5
    with pytest.raises(ContractError) as err:
        resolve(RID + "#/k", RefRule(unit="1"), source)
    assert code_of(err) is ErrorCode.REF_UNIT_MISMATCH


def test_staleness_rule() -> None:
    source = MemorySource(record(host=4))
    strict = RefRule()
    ok = RefRule(stale_ok=True)
    # The model is at revision 5 while the result was produced at 4.
    with pytest.raises(ContractError) as err:
        resolve(RID + "#/b_mm", RefRule(field="b_mm"), source, lambda _m: 5)
    detail = err.value.detail
    assert detail.code is ErrorCode.REF_STALE
    assert detail.retryable is False
    assert detail.field == "b_mm"
    assert detail.received == {"model_id": MID, "record_revision": 4, "current_revision": 5}
    with pytest.raises(ContractError) as err:
        resolve(RID, strict, source, lambda _m: 5)
    assert code_of(err) is ErrorCode.REF_STALE
    got = resolve(RID + "#/b_mm", ok, source, lambda _m: 5)
    assert got.value == 300
    assert (got.model_id, got.model_revision) == (MID, 4)
    # Same revision, or a model the caller does not track: accepted.
    assert resolve(RID + "#/b_mm", strict, source, lambda _m: 4).value == 300
    assert resolve(RID + "#/b_mm", strict, source, lambda _m: None).value == 300
    # A result without a host is never stale by revision, and the function is not consulted.
    called: list[str] = []
    hostless = MemorySource(record())
    assert resolve(RID, strict, hostless, lambda m: called.append(m) or 99).value == PAYLOAD
    assert called == []
    seen: list[str] = []
    resolve(RID, strict, source, lambda m: seen.append(m) or 4)
    assert seen == [MID]


def test_revision_below_the_record_is_an_integrity_failure() -> None:
    source = MemorySource(record(host=4))
    for rule in (RefRule(), RefRule(stale_ok=True)):
        with pytest.raises(ContractError) as err:
            resolve(RID, rule, source, lambda _m: 3)
        detail = err.value.detail
        assert detail.code is ErrorCode.INTERNAL
        assert detail.incident_id is not None
        assert detail.retryable is False


def test_failure_order_first_failure_wins() -> None:
    both = MemorySource(record(kind="forces.member_end/1", host=1))
    rule = RefRule(kinds=frozenset({"model.sections/1"}), unit="m")
    with pytest.raises(ContractError) as err:
        resolve(RID + "#/missing", rule, both, lambda _m: 2)
    assert code_of(err) is ErrorCode.REF_KIND_MISMATCH
    rule = RefRule(unit="m")
    with pytest.raises(ContractError) as err:
        resolve(RID + "#/missing", rule, both, lambda _m: 2)
    assert code_of(err) is ErrorCode.REF_POINTER_INVALID
    with pytest.raises(ContractError) as err:
        resolve(RID + "#/b_mm", rule, both, lambda _m: 2)
    assert code_of(err) is ErrorCode.REF_UNIT_MISMATCH


def test_rule_model() -> None:
    rule = RefRule()
    assert (rule.kinds, rule.unit, rule.stale_ok, rule.field) == (frozenset(), None, False, None)
    for bad in ({"kinds": {"bad"}}, {"field": "1x"}, {"extra": 1}):
        with pytest.raises(ValidationError):
            RefRule.model_validate(bad)
