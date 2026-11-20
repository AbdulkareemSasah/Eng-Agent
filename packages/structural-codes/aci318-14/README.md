# structural-codes-aci318-14

ACI 318-14 pack of the structural-codes folder of the Eng-Agent platform (import name `aci318_14`). Footing checks
arrive task by task. Governing documents: `../docs/plans/0002-aci318-14-footing-checks.md` and the clause specs in
`../docs/clauses/aci318_14/`. Every check is `draft` until the owner adds an entry to `approvals.yaml`.

## Usage

```python
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes import evaluate

result = evaluate(
    "aci318_14.13_3_1_1.bearing_pressure_service",
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
print(result.payload.verdicts[0].status, result.state)  # PASS draft
```

The pack is found by `Registry.discover()` through its entry point. `python -m structural_codes verify --pack .`
reports every check as not verified (no worked example yet).
