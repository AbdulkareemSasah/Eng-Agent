# structural-codes-sbc304-2018

SBC 304-2018 overlay pack of the structural-codes folder of the Eng-Agent platform (import name `sbc304_2018`). It
evaluates no SBC equation: every row of the clause map is unconfirmed and gives `NEEDS_ENGINEER`. Governing documents:
`../docs/plans/0003-sbc304-2018-footing-overlay.md` and `../docs/clauses/sbc304_2018/clause-map.md`. Every check is
`draft` until the owner adds an entry to `approvals.yaml`.

## Usage

Resolve overlay check ids with `check_id_for` (provisional while unconfirmed; do not hard-code them) and evaluate
through `structural_codes.evaluate`:

```python
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes import evaluate

from sbc304_2018 import check_id_for

result = evaluate(
    check_id_for("aci318_14.13_3_1_1.bearing_pressure_service"),
    {
        "FX_kN": 0,
        "FY_kN": 0,
        "FZ_kN": 1200,
        "MX_kNm": 0,
        "MY_kNm": 0,
        "Lx_mm": 2500,
        "Ly_mm": 2500,
        "reaction_height_mm": 0,
        "h_mm": 600,
        "soil_depth_mm": 1000,
        "gamma_c_kN_m3": 24,
        "gamma_s_kN_m3": 18,
        "surcharge_kPa": 0,
        "q_allow_kPa": 250,
        "allowable_kind": "gross",
    },
    subject=Subject(kind=SubjectKind.FOOTING, id="F1"),
)
print(result.payload.verdicts[0].status, result.state)  # NEEDS_ENGINEER draft
```

The pack is found by `Registry.discover()` through its entry point (`PACK.base` is `aci318_14`).
`python -m structural_codes verify --pack .` reports every check as not verified (no worked example yet, G-WE).
