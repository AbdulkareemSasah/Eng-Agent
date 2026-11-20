"""Build check of a server (plan 0002 T6b; spec 0002 AC9, section 4.3.4)."""

import copy
import hashlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from mcp import types

from eng_harness.servers import BuildPin
from eng_harness.servers._buildcheck import BuildExpectation, Observed, check_build, tool_list_fingerprint

COMMIT = "a" * 40
OTHER_COMMIT = "c" * 40
EXE = "b" * 64
SCHEMAS: dict[str, Any] = {
    "csi_beta": {
        "type": "object",
        "title": "Beta",
        "description": "Describes beta.",
        "properties": {
            "description": {"type": "string", "description": "A property that is named description."},
            "count": {"type": "integer", "title": "Count", "minimum": 1},
        },
    },
    "csi_alpha": {"type": "object", "properties": {}, "additionalProperties": False},
}
# What the spec defines, written out by hand: tools sorted by name, `description` and `title` members that hold a
# string removed except the members of a `properties` object, canonical JSON (RFC 8785), SHA-256.
HAND_WRITTEN = (
    '[{"input_schema":{"additionalProperties":false,"properties":{},"type":"object"},"name":"csi_alpha"},'
    '{"input_schema":{"properties":{"count":{"minimum":1,"type":"integer"},'
    '"description":{"type":"string"}},"type":"object"},"name":"csi_beta"}]'
)


def test_fingerprint_definition() -> None:
    assert tool_list_fingerprint(SCHEMAS) == hashlib.sha256(HAND_WRITTEN.encode()).hexdigest()


def test_fingerprint_ignores_order_and_descriptions_only() -> None:
    base = tool_list_fingerprint(SCHEMAS)
    assert tool_list_fingerprint(dict(reversed(SCHEMAS.items()))) == base
    reworded = copy.deepcopy(SCHEMAS)
    reworded["csi_beta"]["description"] = "Another text."
    reworded["csi_beta"]["properties"]["count"]["title"] = "Number"
    assert tool_list_fingerprint(reworded) == base
    changes: list[Callable[[dict[str, Any]], object]] = [
        lambda s: s["csi_beta"]["properties"]["count"].update(minimum=2),
        lambda s: s["csi_beta"]["properties"].update(extra={"type": "string"}),
        lambda s: s["csi_beta"]["properties"].pop("description"),
        lambda s: s.pop("csi_alpha"),
    ]
    for change in changes:
        changed = copy.deepcopy(SCHEMAS)
        change(changed)
        assert tool_list_fingerprint(changed) != base


def test_non_string_description_is_kept() -> None:
    plain = {"t": {"type": "object", "properties": {"x": {"type": "string"}}}}
    odd = {"t": {"type": "object", "description": {"x": 1}, "properties": {"x": {"type": "string"}}}}
    assert tool_list_fingerprint(odd) != tool_list_fingerprint(plain)


PIN = BuildPin(sasaah_commit=COMMIT, exe_sha256=EXE)
EXPECTED = BuildExpectation(
    sasaah_commit=COMMIT,
    also_tested_commits=(OTHER_COMMIT,),
    tool_fingerprint=tool_list_fingerprint(SCHEMAS),
    tool_names=frozenset(SCHEMAS),
    product="ETABS",
)


def _observed(**changes: Any) -> Observed:
    base = Observed(
        exe_sha256=EXE,
        server_info=types.Implementation(name="srv", version="1.0"),
        tools={**copy.deepcopy(SCHEMAS), "csi_db_tables_apply": {"type": "object"}, "csi_other": {"type": "object"}},
        status={"read_only": False, "script_enabled": False},
    )
    return replace(base, **changes)


def _tools_with(**extra: Any) -> dict[str, Any]:
    return {**copy.deepcopy(SCHEMAS), **extra}


def test_matching_build_is_ok() -> None:
    check = check_build("csi", PIN, EXPECTED, _observed(), COMMIT, product="ETABS")
    assert check.ok is True
    assert check.reason is None
    assert check.server == "csi"
    assert check.build == f"{COMMIT[:12]}+{EXE[:12]}"
    assert check.min_build == COMMIT
    assert check.fingerprint == check.expected_fingerprint == EXPECTED.tool_fingerprint


def test_other_tested_commit_satisfies_the_minimum() -> None:
    assert check_build("csi", PIN, EXPECTED, _observed(), OTHER_COMMIT, product="ETABS").ok is True


def test_no_minimum_is_not_checked() -> None:
    assert check_build("csi", PIN, EXPECTED, _observed(), product="ETABS").ok is True


@pytest.mark.parametrize(
    ("what", "keyword"),
    [
        ("exe", "executable"),
        ("info_version", "serverinfo"),
        ("info_missing", "serverinfo"),
        ("pin_commit", "commit"),
        ("minimum", "minimum"),
        ("fingerprint", "fingerprint"),
        ("missing_tool", "csi_beta"),
        ("run_script", "csi_run_script"),
        ("invoke", "csi_invoke"),
        ("object_add", "csi_object_add"),
        ("read_only", "read_only"),
        ("script_enabled", "script_enabled"),
        ("script_unreported", "script_enabled"),
    ],
)
def test_each_mismatch(what: str, keyword: str) -> None:
    pin, minimum, observed = PIN, COMMIT, _observed()
    pinned = BuildPin(sasaah_commit=COMMIT, exe_sha256=EXE, server_info_version="1.0")
    match what:
        case "exe":
            observed = _observed(exe_sha256="d" * 64)
        case "info_version":
            pin, observed = pinned.model_copy(update={"server_info_version": "2.0"}), _observed()
        case "info_missing":
            pin, observed = pinned, _observed(server_info=None)
        case "pin_commit":
            pin = BuildPin(sasaah_commit=OTHER_COMMIT, exe_sha256=EXE)
            minimum = OTHER_COMMIT
        case "minimum":
            minimum = "e" * 40
        case "fingerprint":
            changed = _tools_with(csi_alpha={"type": "object", "properties": {"x": {"type": "string"}}})
            observed = _observed(tools=changed)
        case "missing_tool":
            observed = _observed(tools={"csi_alpha": SCHEMAS["csi_alpha"]})
        case "run_script" | "invoke" | "object_add":
            name = {"run_script": "csi_run_script", "invoke": "csi_invoke", "object_add": "csi_object_add"}[what]
            observed = _observed(tools=_tools_with(**{name: {"type": "object"}}))
        case "read_only":
            observed = _observed(status={"read_only": True, "script_enabled": False})
        case "script_enabled":
            observed = _observed(status={"read_only": False, "script_enabled": True})
        case "script_unreported":
            observed = _observed(status={"read_only": False})
    check = check_build("csi", pin, EXPECTED, observed, minimum, product="ETABS")
    assert check.ok is False
    assert check.reason is not None
    assert keyword in check.reason.lower()


def test_db_tables_apply_is_tolerated_when_listed() -> None:
    observed = _observed(tools=_tools_with(csi_db_tables_apply={"type": "object"}))
    assert check_build("csi", PIN, EXPECTED, observed, COMMIT, product="ETABS").ok is True


def test_fingerprint_per_product() -> None:
    """AC4: each product is checked against the fingerprint of its own tools; a wrong product never passes."""
    etabs = BuildExpectation(
        sasaah_commit=COMMIT,
        also_tested_commits=(),
        tool_fingerprint=tool_list_fingerprint({"csi_alpha": SCHEMAS["csi_alpha"]}),
        tool_names=frozenset({"csi_alpha"}),
        product="ETABS",
    )
    safe = replace(
        etabs, tool_fingerprint=tool_list_fingerprint(SCHEMAS), tool_names=frozenset(SCHEMAS), product="SAFE"
    )
    assert etabs.tool_fingerprint != safe.tool_fingerprint
    for want, server in ((etabs, "csi"), (safe, "csi_safe")):
        check = check_build(server, PIN, want, _observed(), product=want.product)
        assert (check.ok, check.reason) == (True, None)
        assert check.fingerprint == check.expected_fingerprint == want.tool_fingerprint
    # A tool only the other product lists does not move this product's fingerprint (adding SAFE leaves ETABS as it was).
    grown = _observed(tools={**_observed().tools, "csi_safe_only": {"type": "object"}})
    assert check_build("csi", PIN, etabs, grown, product="ETABS").ok is True
    # The expectation of one product is refused for a server of the other.
    wrong = check_build("csi_safe", PIN, etabs, _observed(), product="SAFE")
    assert wrong.ok is False
    assert wrong.reason is not None
    assert "ETABS" in wrong.reason
    assert "SAFE" in wrong.reason


def test_addin_hashes(tmp_path: Any) -> None:
    addin1 = tmp_path / "addin1.dll"
    addin2 = tmp_path / "addin2.dll"
    addin1.write_bytes(b"addin-one")
    addin2.write_bytes(b"addin-two")
    d1 = hashlib.sha256(b"addin-one").hexdigest()
    d2 = hashlib.sha256(b"addin-two").hexdigest()
    pin = BuildPin(sasaah_commit=COMMIT, exe_sha256=EXE, addin_paths=(str(addin1), str(addin2)), addin_sha256=(d1, d2))
    assert check_build("csi", pin, EXPECTED, _observed(), product="ETABS").ok
    addin2.write_bytes(b"changed")
    result = check_build("csi", pin, EXPECTED, _observed(), product="ETABS")
    assert not result.ok
    assert result.reason is not None
    assert "add-in" in result.reason
    addin2.write_bytes(b"addin-two")
    addin1.unlink()
    missing = check_build("csi", pin, EXPECTED, _observed(), product="ETABS")
    assert not missing.ok
    assert missing.reason is not None
    assert "add-in" in missing.reason


def test_fingerprint_three_products() -> None:
    """AC3: each of ETABS, SAFE and SAP2000 is checked against its own fingerprint; a wrong product never passes."""
    from eng_harness.adapters.csi import csi_allowlist

    # The packaged allowlist must pin three distinct product fingerprints (fails until SAP2000 is added).
    pinned = csi_allowlist().fingerprint
    assert set(pinned) == {"ETABS", "SAFE", "SAP2000"}
    assert pinned["ETABS"] == "67e0f08ace144fdc41f43882b6671c4296899b36bbfb122433ef879c2e2ebdd1"
    assert pinned["SAFE"] == "ccdab3c9461b60387569af2ec7acc214c0803bd7953a5d66ca380e1c87c38025"
    assert len(set(pinned.values())) == 3

    etabs = BuildExpectation(
        sasaah_commit=COMMIT,
        also_tested_commits=(),
        tool_fingerprint=tool_list_fingerprint({"csi_alpha": SCHEMAS["csi_alpha"]}),
        tool_names=frozenset({"csi_alpha"}),
        product="ETABS",
    )
    safe = replace(
        etabs, tool_fingerprint=tool_list_fingerprint(SCHEMAS), tool_names=frozenset(SCHEMAS), product="SAFE"
    )
    sap = replace(
        etabs,
        tool_fingerprint=tool_list_fingerprint({"csi_beta": SCHEMAS["csi_beta"]}),
        tool_names=frozenset({"csi_beta"}),
        product="SAP2000",
    )
    assert len({etabs.tool_fingerprint, safe.tool_fingerprint, sap.tool_fingerprint}) == 3
    for want, server in ((etabs, "csi"), (safe, "csi_safe"), (sap, "csi_sap2000")):
        check = check_build(server, PIN, want, _observed(), product=want.product)
        assert (check.ok, check.reason) == (True, None)
        assert check.fingerprint == check.expected_fingerprint == want.tool_fingerprint
    grown = _observed(tools={**_observed().tools, "csi_sap2000_only": {"type": "object"}})
    assert check_build("csi", PIN, etabs, grown, product="ETABS").ok is True
    wrong = check_build("csi_sap2000", PIN, etabs, _observed(), product="SAP2000")
    assert wrong.ok is False
    assert wrong.reason is not None
    assert "ETABS" in wrong.reason
    assert "SAP2000" in wrong.reason
