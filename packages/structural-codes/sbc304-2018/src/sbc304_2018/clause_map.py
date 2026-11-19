"""SBC 304-2018 clause map for all registered ACI footing and column checks.

Source: docs/clauses/sbc304_2018/clause-map.md §3. Clause chains identify the ACI source to compare.
Each SBC clause and source is pending owner confirmation.
"""

from sbc304_2018._overlay import MapRow, MapStatus

__all__ = ["CLAUSE_MAP"]

CLAUSE_MAP: tuple[MapRow, ...] = (
    MapRow(
        base_check_id="aci318_14.13_3_1_1.bearing_pressure_service",
        status=MapStatus.UNCONFIRMED,
        sbc_clause=None,
        sbc_source=None,
        gap_id="G-1",
        base_clauses=("13.3.1.1",),
        confirm=(
            "The SBC rule for sizing the base area from service loads and the allowable soil pressure, and "
            "whether the allowable pressure comes from the geotechnical report as in the base spec"
        ),
    ),
    MapRow(
        base_check_id="aci318_14.22_5_5_1.one_way_shear",
        status=MapStatus.UNCONFIRMED,
        sbc_clause=None,
        sbc_source=None,
        gap_id="G-2",
        base_clauses=("22.5.5.1", "22.5.1.1", "22.5.3.1", "13.3.3.1", "13.2.7.2", "21.2.1", "19.2.1.1", "19.2.4.2"),
        confirm=(
            "The one-way shear strength expression, the shear strength reduction factor, the location of the "
            "critical section and the concrete strength limits"
        ),
    ),
    MapRow(
        base_check_id="aci318_14.22_6_5_2.punching_shear",
        status=MapStatus.UNCONFIRMED,
        sbc_clause=None,
        sbc_source=None,
        gap_id="G-3",
        base_clauses=(
            "22.6.5.2",
            "22.6.1",
            "22.6.4.1",
            "22.6.5.3",
            "22.6.3.1",
            "13.3.3.1",
            "21.2.1",
            "19.2.1.1",
            "19.2.4.2",
        ),
        confirm=(
            "The three two-way shear stress expressions and their location factor, the critical perimeter, "
            "the strength reduction factor and the concrete strength limits; and the SBC counterpart of "
            "8.4.4.2 (shear from moment transfer), which the base check leaves as its gap G-4"
        ),
    ),
    MapRow(
        base_check_id="aci318_14.13_2_7_1.flexure_at_column_face",
        status=MapStatus.UNCONFIRMED,
        sbc_clause=None,
        sbc_source=None,
        gap_id="G-4",
        base_clauses=(
            "13.2.7.1",
            "13.3.3.1",
            "22.3.1.1",
            "22.2.2.1",
            "22.2.2.4.1",
            "22.2.2.4.3",
            "21.2.1",
            "21.2.2",
            "20.2.2.4",
            "19.2.1.1",
        ),
        confirm=(
            "The moment section, the stress-block assumptions and factor table, the strength reduction "
            "factors and their strain limits, and the steel strength limit"
        ),
    ),
    MapRow(
        base_check_id="aci318_14.8_6_1_1.min_flexural_reinforcement",
        status=MapStatus.UNCONFIRMED,
        sbc_clause=None,
        sbc_source=None,
        gap_id="G-5",
        base_clauses=("8.6.1.1", "13.3.3.1", "20.2.2.4"),
        confirm=("The minimum flexural reinforcement rows and the referral from footings to the two-way slab minimum"),
    ),
    MapRow(
        base_check_id="aci318_14.25_4_2_3.development_length_bottom_bars",
        status=MapStatus.UNCONFIRMED,
        sbc_clause=None,
        sbc_source=None,
        gap_id="G-6",
        base_clauses=("25.4.2.3", "25.4.2.1", "25.4.2.4", "25.4.1.4", "13.2.7.1", "19.2.1.1", "19.2.4.2", "20.2.2.4"),
        confirm=(
            "The development length expression, its modification factors and their limits, the limit on the "
            "square root of concrete strength and the minimum length"
        ),
    ),
    MapRow(
        base_check_id="aci318_14.22_4_2_1.max_axial_strength",
        status=MapStatus.UNCONFIRMED,
        sbc_clause=None,
        sbc_source=None,
        gap_id="G-7",
        base_clauses=(
            "22.4.2.1",
            "22.4.2.2",
            "10.5.1.1",
            "21.2.1",
            "21.2.2",
            "6.2.5",
            "6.2.5.1",
            "19.2.1.1",
            "20.2.2.4",
        ),
        confirm=(
            "The nominal axial strength expression, the maximum axial strength factors, the strength "
            "reduction factor and the slenderness limit"
        ),
    ),
    MapRow(
        base_check_id="aci318_14.22_4_1_1.axial_flexure_uniaxial",
        status=MapStatus.UNCONFIRMED,
        sbc_clause=None,
        sbc_source=None,
        gap_id="G-8",
        base_clauses=(
            "22.4.1.1",
            "10.5.1.1",
            "10.5.2.1",
            "22.2.1",
            "22.2.2.1",
            "22.2.2.2",
            "22.2.2.4.1",
            "22.2.2.4.3",
            "20.2.2.1",
            "20.2.2.2",
            "21.2.1",
            "21.2.2",
            "21.2.2.1",
            "22.4.2.1",
            "22.4.2.2",
            "6.2.5",
            "6.2.5.1",
            "19.2.1.1",
            "20.2.2.4",
        ),
        confirm=(
            "The strain-compatibility assumptions, the strength reduction factor transition, the axial cap "
            "and the slenderness limit"
        ),
    ),
    MapRow(
        base_check_id="aci318_14.10_6_1_1.longitudinal_reinforcement_limits",
        status=MapStatus.UNCONFIRMED,
        sbc_clause=None,
        sbc_source=None,
        gap_id="G-9",
        base_clauses=("10.6.1.1", "10.3.1.2"),
        confirm=("The minimum and maximum longitudinal reinforcement ratios for columns"),
    ),
)
