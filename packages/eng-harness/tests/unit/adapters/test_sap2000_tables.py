"""SAP2000 table field-map data (plan 0012 T4; spec 0012 AC10, section 4.4).

Every SAP2000 table entry is `unknown` until a recording (L4) sets its keys. Host table names are those named in
spec 0012 section 12 L4 (`Analysis Messages`) or left unknown; no key is taken from the ETABS or SAFE references
(spec 0012 section 4.4).
"""

from __future__ import annotations

import pytest

from eng_harness.adapters.csi._tables import load_field_map, map_rows
from eng_harness.errors import HarnessCode, NotImplementedGap


def _sap2000_map():
    from importlib.resources import files

    text = files("eng_harness.adapters.csi.products").joinpath("_sap2000_tables.toml").read_text(encoding="utf-8")
    return load_field_map(text)


def test_unknown_tables_are_gaps() -> None:
    """AC10: every SAP2000 field-map entry is unknown; map_rows raises NotImplementedGap (SP-4), nothing is guessed."""
    field_map = _sap2000_map()
    assert field_map.tables, "spec 0012 section 4.4: the packaged SAP2000 field map has unknown entries"
    assert all(entry.status == "unknown" for entry in field_map.tables.values())
    # Spec 0012 section 12 L4 names Analysis Messages among the tables a reader needs.
    assert "Analysis Messages" in field_map.tables
    with pytest.raises(NotImplementedGap) as caught:
        map_rows("Analysis Messages", [{"Text": "ok"}], field_map=field_map)
    assert caught.value.code is HarnessCode.NOT_IMPLEMENTED
    assert "Analysis Messages" in caught.value.message
    assert any("Analysis Messages" in item or "SP-4" in item for item in caught.value.evidence)
