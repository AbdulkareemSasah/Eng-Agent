"""Revit parameter role map load-time rules (plan 0011 T6; spec 0011 AC33, §4.8)."""

import pytest

from eng_harness.servers import ConfigError


def _family(
    *,
    section_b: dict[str, object] | None = None,
    section_h: dict[str, object] | None = None,
    extra: dict[str, dict[str, object]] | None = None,
) -> dict[str, dict[str, object]]:
    roles: dict[str, dict[str, object]] = {}
    if section_b is not None:
        roles["section_b"] = section_b
    if section_h is not None:
        roles["section_h"] = section_h
    if extra:
        roles.update(extra)
    return roles


def test_role_map_rules() -> None:
    """AC33: role map load rules; valid map loads; bad name/status/role/guid raise ConfigError."""
    from eng_harness.adapters.revit._parameters import ROLE_NAMES, load_role_map

    assert ROLE_NAMES == (
        "section_b",
        "section_h",
        "section_D",
        "material",
        "rotation",
        "etabs_link",
    )

    ok = {
        "Rectangular Column": _family(
            section_b={
                "name": "b",
                "guid": None,
                "builtin": "STRUCTURAL_SECTION_COMMON_WIDTH",
                "status": "candidate",
            },
            section_h={
                "name": "h",
                "guid": "11111111-1111-1111-1111-111111111111",
                "builtin": None,
                "status": "candidate",
            },
            extra={
                "rotation": {
                    "name": "Cross-Section Rotation",
                    "guid": None,
                    "builtin": None,
                    "status": "candidate",
                },
                "etabs_link": {
                    "name": "Sasaah_EtabsElementId",
                    "guid": None,
                    "builtin": None,
                    "status": "reference",
                },
            },
        )
    }
    loaded = load_role_map(ok)
    assert loaded["Rectangular Column"]["section_b"].name == "b"
    assert loaded["Rectangular Column"]["section_b"].status == "candidate"
    assert loaded["Rectangular Column"]["section_h"].guid == "11111111-1111-1111-1111-111111111111"
    assert loaded["Rectangular Column"]["etabs_link"].status == "reference"

    with pytest.raises(ConfigError, match="name") as missing_name:
        load_role_map(
            {
                "Rectangular Column": _family(
                    section_b={"guid": None, "builtin": None, "status": "candidate"},
                )
            }
        )
    assert "parameters" in missing_name.value.key

    with pytest.raises(ConfigError, match="status") as missing_status:
        load_role_map(
            {
                "Rectangular Column": _family(
                    section_b={"name": "b", "guid": None, "builtin": None},
                )
            }
        )
    assert "parameters" in missing_status.value.key

    with pytest.raises(ConfigError, match="status") as unknown_status:
        load_role_map(
            {
                "Rectangular Column": _family(
                    section_b={
                        "name": "b",
                        "guid": None,
                        "builtin": None,
                        "status": "approved",
                    },
                )
            }
        )
    assert "parameters" in unknown_status.value.key

    with pytest.raises(ConfigError, match="unknown parameter role") as unknown_role:
        load_role_map(
            {
                "Rectangular Column": _family(
                    extra={
                        "not_a_role": {
                            "name": "x",
                            "guid": None,
                            "builtin": None,
                            "status": "candidate",
                        },
                    },
                )
            }
        )
    assert "parameters" in unknown_role.value.key

    with pytest.raises(ConfigError, match="name") as empty_name:
        load_role_map(
            {
                "Rectangular Column": _family(
                    section_b={
                        "name": "",
                        "guid": None,
                        "builtin": None,
                        "status": "candidate",
                    },
                )
            }
        )
    assert "parameters" in empty_name.value.key

    with pytest.raises(ConfigError, match="guid") as empty_guid:
        load_role_map(
            {
                "Rectangular Column": _family(
                    section_b={
                        "name": "b",
                        "guid": "",
                        "builtin": None,
                        "status": "candidate",
                    },
                )
            }
        )
    assert "parameters" in empty_guid.value.key

    shared = "22222222-2222-2222-2222-222222222222"
    with pytest.raises(ConfigError, match="GUID") as dup_guid:
        load_role_map(
            {
                "Rectangular Column": _family(
                    section_b={
                        "name": "b",
                        "guid": shared,
                        "builtin": None,
                        "status": "candidate",
                    },
                    section_h={
                        "name": "h",
                        "guid": shared,
                        "builtin": None,
                        "status": "candidate",
                    },
                )
            }
        )
    assert "parameters" in dup_guid.value.key
