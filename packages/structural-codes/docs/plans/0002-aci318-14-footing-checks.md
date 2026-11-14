---
id: plan-b071-aci318-14-footing-checks
issue: "B-071"
spec: packages/structural-codes/docs/clauses/aci318_14/   # a directory on purpose: this plan's spec is the six clause specs of §1, one per check
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r3]           # binding for every pull request of this plan; r3 from T1 (pyproject.toml, uv.lock, .gate/)
tasks:
  - id: T1
    title: Pack skeleton, empty approvals file, workspace member, local-testing rows
    files:
      - "pyproject.toml"
      - "uv.lock"
      - "packages/structural-codes/.gate/agents.yml"
      - "packages/structural-codes/.gate/risk-map.yml"
      - "packages/structural-codes/AGENTS.md"
      - "packages/structural-codes/docs/local-testing.md"
      - "packages/structural-codes/aci318-14/pyproject.toml"
      - "packages/structural-codes/aci318-14/README.md"
      - "packages/structural-codes/aci318-14/CHANGELOG.md"
      - "packages/structural-codes/aci318-14/src/aci318_14/__init__.py"
      - "packages/structural-codes/aci318-14/src/aci318_14/py.typed"
      - "packages/structural-codes/aci318-14/src/aci318_14/approvals.yaml"
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/__init__.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_package.py"
    max_changed_lines: 200
    max_sessions: 2
    tests_first: ["packages/structural-codes/aci318-14/tests/unit/test_package.py::test_version_and_empty_approvals"]
    covers: [PK-AC1]
    depends_on: []
  - id: T2
    title: Shared footing statics, shared constants and preconditions
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/_footing.py"
      - "packages/structural-codes/aci318-14/src/aci318_14/_common.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_footing_statics.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_common.py"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/unit/test_footing_statics.py::test_s1_to_s5"
      - "packages/structural-codes/aci318-14/tests/unit/test_common.py::test_shared_preconditions"
    covers: [BP-AC5, PK-AC2]
    depends_on: [T1]
  - id: T2b
    title: "Regression tests: rectangular, asymmetric footing statics and integrals in both directions"
    # Amendment (B-421, documents only): the retroactive verification of T2 (B-271) found every statics and integral
    # case square, so X/Y swaps in S1, S2, the S5 modulus pairing or the _AXES table pass every test. The tests pass
    # against the merged code, so this is a test-only pull request (title type test: no non-test file, no
    # failing-first run; gate spec 4.7). Hand values: §2 T2b.
    files:
      - "packages/structural-codes/aci318-14/tests/unit/test_footing_statics.py"
    # Budget: the task statement of B-421 set 10; two cases (R1, R2) with about 25 hand-value assertions (PK-AC10)
    # do not fit, so the review of B-421 raised it to 60, pending the lead's confirmation.
    max_changed_lines: 60
    max_sessions: 1
    tests_first:
      - "packages/structural-codes/aci318-14/tests/unit/test_footing_statics.py::test_rectangular_statics"
      - "packages/structural-codes/aci318-14/tests/unit/test_footing_statics.py::test_rectangular_integrals"
    covers: [PK-AC10]
    depends_on: [T2]
  - id: T2c
    title: "Shared constants carry the clause specs' citation texts, asserted by test"
    # Amendment (B-421, documents only): fix of the same verification. The shared constants of _common.py take the
    # citation texts of §1.1 (c_half changes; sf_max gains its Cited.note), the module docstring cites §6 Q6 as
    # amended, and a test compares each shared constant with its rows in the clause specs §5.
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/_common.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_footing_statics.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_common.py"
    max_changed_lines: 30
    max_sessions: 1
    tests_first:
      - "packages/structural-codes/aci318-14/tests/unit/test_common.py::test_shared_sources_match_clause_specs"
    covers: [PK-AC11]
    depends_on: [T2]
  - id: T3
    title: Check bearing_pressure_service (13.3.1.1)
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/bearing_pressure.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_bearing.py"
      - "packages/structural-codes/aci318-14/tests/golden/test_bearing_cases.py"
      - "packages/structural-codes/aci318-14/tests/property/test_bearing_props.py"
      - "packages/structural-codes/aci318-14/tests/data/golden/verification/aci318_14.13_3_1_1.bearing_pressure_service.yaml"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/golden/test_bearing_cases.py::test_hand_checks"
      - "packages/structural-codes/aci318-14/tests/unit/test_bearing.py::test_preconditions"
      - "packages/structural-codes/aci318-14/tests/unit/test_bearing.py::test_allowable_from_basis"
      - "packages/structural-codes/aci318-14/tests/property/test_bearing_props.py::test_monotone_and_sign_free"
    covers: [BP-AC1, BP-AC2, BP-AC3, BP-AC4]
    depends_on: [T2]
  - id: T4
    title: Check one_way_shear (22.5.5.1)
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/one_way_shear.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_one_way_shear.py"
      - "packages/structural-codes/aci318-14/tests/golden/test_one_way_shear_cases.py"
      - "packages/structural-codes/aci318-14/tests/property/test_one_way_shear_props.py"
      - "packages/structural-codes/aci318-14/tests/data/golden/verification/aci318_14.22_5_5_1.one_way_shear.yaml"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/golden/test_one_way_shear_cases.py::test_hand_checks"
      - "packages/structural-codes/aci318-14/tests/unit/test_one_way_shear.py::test_preconditions"
      - "packages/structural-codes/aci318-14/tests/unit/test_one_way_shear.py::test_two_directions_and_governing"
      - "packages/structural-codes/aci318-14/tests/property/test_one_way_shear_props.py::test_monotone"
    covers: [OS-AC1, OS-AC2, OS-AC3, OS-AC4]
    depends_on: [T2]
  - id: T5
    title: Check punching_shear (22.6.5.2), concentric shear only
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/punching_shear.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_punching_shear.py"
      - "packages/structural-codes/aci318-14/tests/golden/test_punching_shear_cases.py"
      - "packages/structural-codes/aci318-14/tests/property/test_punching_shear_props.py"
      - "packages/structural-codes/aci318-14/tests/data/golden/verification/aci318_14.22_6_5_2.punching_shear.yaml"
    max_changed_lines: 220
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/golden/test_punching_shear_cases.py::test_hand_checks"
      - "packages/structural-codes/aci318-14/tests/unit/test_punching_shear.py::test_preconditions"
      - "packages/structural-codes/aci318-14/tests/unit/test_punching_shear.py::test_moment_transfer_gap"
      - "packages/structural-codes/aci318-14/tests/property/test_punching_shear_props.py::test_monotone_and_symmetric"
    covers: [PS-AC1, PS-AC2, PS-AC3, PS-AC4]
    depends_on: [T2]
  - id: T6
    title: Check flexure_at_column_face (13.2.7.1), tension-controlled only
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/flexure.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_flexure.py"
      - "packages/structural-codes/aci318-14/tests/golden/test_flexure_cases.py"
      - "packages/structural-codes/aci318-14/tests/property/test_flexure_props.py"
      - "packages/structural-codes/aci318-14/tests/data/golden/verification/aci318_14.13_2_7_1.flexure_at_column_face.yaml"
    max_changed_lines: 250
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/golden/test_flexure_cases.py::test_hand_checks"
      - "packages/structural-codes/aci318-14/tests/unit/test_flexure.py::test_beta1_rows"
      - "packages/structural-codes/aci318-14/tests/unit/test_flexure.py::test_gaps_and_preconditions"
      - "packages/structural-codes/aci318-14/tests/property/test_flexure_props.py::test_monotone"
    covers: [FL-AC1, FL-AC2, FL-AC3, FL-AC4]
    depends_on: [T2]
  - id: T7
    title: Check min_flexural_reinforcement (8.6.1.1)
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/min_reinforcement.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_min_reinforcement.py"
      - "packages/structural-codes/aci318-14/tests/golden/test_min_reinforcement_cases.py"
      - "packages/structural-codes/aci318-14/tests/property/test_min_reinforcement_props.py"
      - "packages/structural-codes/aci318-14/tests/data/golden/verification/aci318_14.8_6_1_1.min_flexural_reinforcement.yaml"
    max_changed_lines: 120
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/golden/test_min_reinforcement_cases.py::test_hand_checks"
      - "packages/structural-codes/aci318-14/tests/unit/test_min_reinforcement.py::test_rows_and_preconditions"
      - "packages/structural-codes/aci318-14/tests/property/test_min_reinforcement_props.py::test_monotone"
    covers: [MR-AC1, MR-AC2, MR-AC3]
    depends_on: [T2]
  - id: T8
    title: Check development_length_bottom_bars (25.4.2.3)
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/development_length.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_development_length.py"
      - "packages/structural-codes/aci318-14/tests/golden/test_development_length_cases.py"
      - "packages/structural-codes/aci318-14/tests/property/test_development_length_props.py"
      - "packages/structural-codes/aci318-14/tests/data/golden/verification/aci318_14.25_4_2_3.development_length_bottom_bars.yaml"
    max_changed_lines: 200
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/golden/test_development_length_cases.py::test_hand_checks"
      - "packages/structural-codes/aci318-14/tests/unit/test_development_length.py::test_preconditions"
      - "packages/structural-codes/aci318-14/tests/unit/test_development_length.py::test_psi_s_assumption"
      - "packages/structural-codes/aci318-14/tests/property/test_development_length_props.py::test_monotone"
    covers: [DL-AC1, DL-AC2, DL-AC3, DL-AC4]
    depends_on: [T2]
  - id: T9
    title: Pack assembly, registration, pack-level tests, README usage
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/__init__.py"
      - "packages/structural-codes/aci318-14/pyproject.toml"
      - "packages/structural-codes/aci318-14/README.md"
      - "packages/structural-codes/aci318-14/CHANGELOG.md"
      - "packages/structural-codes/aci318-14/tests/unit/test_pack.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_verify_cli.py"
      - "packages/structural-codes/aci318-14/tests/contract/test_pack_payloads.py"
      - "packages/structural-codes/aci318-14/tests/replay/test_pack_determinism.py"
    max_changed_lines: 150
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/unit/test_pack.py::test_registry_and_specs"
      - "packages/structural-codes/aci318-14/tests/unit/test_pack.py::test_lint_scope_and_citations"
      - "packages/structural-codes/aci318-14/tests/unit/test_pack.py::test_all_draft"
      - "packages/structural-codes/aci318-14/tests/contract/test_pack_payloads.py::test_all_checks_payload"
      - "packages/structural-codes/aci318-14/tests/replay/test_pack_determinism.py::test_identical_across_hash_seeds"
      - "packages/structural-codes/aci318-14/tests/unit/test_verify_cli.py::test_verify_reports_unverified"
    covers: [PK-AC3, PK-AC4, PK-AC5, PK-AC6, PK-AC7, PK-AC8, PK-AC9]
    depends_on: [T3, T4, T5, T6, T7, T8]
---

# Implementation plan: ACI 318-14 isolated-footing checks

Package: `structural-codes-aci318-14` (import package `aci318_14`), in `packages/structural-codes/aci318-14/`, layer 3
([10](../../../../design/docs/architecture/10-structural-codes.md) §2), on the core framework
([spec 0001](../specs/0001-core-framework.md), "CF §n"; [plan 0001](0001-core-framework.md)). File paths in the front
matter are relative to the workspace root; `max_changed_lines` counts non-test, non-generated lines
([process/04](../../../../design/process/04-implementation-rules.md) §4). Bootstrap mode
([ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4): this plan and its clause specs are
`draft`, every check ships `draft`, and `approvals.yaml` stays empty.

## 1. Approach

The scope is the isolated-footing list of 10 §9: six checks, each specified by one clause spec (the spec of this plan,
written from [process/templates/clause-spec.md](../../../../design/process/templates/clause-spec.md)):

| Check | Clause spec | Verdicts per footing |
|---|---|---|
| `aci318_14.13_3_1_1.bearing_pressure_service` | [bearing](../clauses/aci318_14/aci318_14.13_3_1_1.bearing_pressure_service.md) (also defines the shared footing statics S1 to S5) | 1 per service case |
| `aci318_14.22_5_5_1.one_way_shear` | [one-way shear](../clauses/aci318_14/aci318_14.22_5_5_1.one_way_shear.md) | 2 (X, Y) per factored case |
| `aci318_14.22_6_5_2.punching_shear` | [punching shear](../clauses/aci318_14/aci318_14.22_6_5_2.punching_shear.md) | 1 per factored case |
| `aci318_14.13_2_7_1.flexure_at_column_face` | [flexure](../clauses/aci318_14/aci318_14.13_2_7_1.flexure_at_column_face.md) | 2 (X, Y) per factored case |
| `aci318_14.8_6_1_1.min_flexural_reinforcement` | [minimum reinforcement](../clauses/aci318_14/aci318_14.8_6_1_1.min_flexural_reinforcement.md) | 2 (X, Y) |
| `aci318_14.25_4_2_3.development_length_bottom_bars` | [development length](../clauses/aci318_14/aci318_14.25_4_2_3.development_length_bottom_bars.md) | 2 (X, Y) |

Every equation uses the SI form; every constant is a `Cited` value whose source is the clause, table or equation of
its clause spec (or an SI prefix, mechanics or geometry identity, named as such). Each clause is the author's reading,
confirmed line by line at C3 ([process/10](../../../../design/process/10-engineering-verification.md) §3); where the
author was not certain, the check returns `NEEDS_ENGINEER` through a declared precondition or `NotImplementedGap`
(CF §4.4) and a test expects it. No value is guessed.

Inputs arrive as references (CF §4.3, EC §5): forces from a `forces.joint_reactions/1` row of the footing's support
joint, material and soil values from `basis.design_basis/1` fields, geometry from the footing block (B-075). The
harness calls the checks through `ctx.calc` in batch, one item per footing and case (10 §7, spec B-062); the checks
themselves are pure and touch no host.

Order: the shared statics and constants first (T2), because four checks use them and a mistake there would repeat in
all of them; then the six checks in parallel (disjoint files, each with its own test pack built by `Registry.of`), then
assembly (T9), which registers the pack and runs the pack-level tests. Each task is test-first: its first commit is
`test:` with the tests of `tests_first`, failing on `build/v1`
([process/05](../../../../design/process/05-testing-and-verification.md) §9).

Start condition: core plan 0001 tasks T1 (shared folder files), T6 (checks and registry), T8 (runner) and T14a (the
public modules declared, without which every import of `structural_codes` from the pack fails IM002; amendment B-385)
are merged before T2; T9 (verification) before T3 to T8 (their case files are run through `verify_check`); T11, T12 and T14b
(lifecycle, command line, and `structural_codes.lifecycle` in public_modules, without which
`tests/unit/test_pack.py::test_all_draft` fails IM002; amendment B-419) before T9. T1 needs core T1 only. T9 also needs the clause-spec folder settled (§6 Q12):
CF §4.1 and §4.2 amended to `docs/clauses/<pack>/`, or these clause specs moved to the folder the core resolves, so
that PK-AC3 finds every `CheckMeta.spec` file.

### 1.1 Shared constants (amendment B-421)

A constant of `aci318_14._common` is recorded once per trace under one `Cited`, and the same `Cited` enters the trace
of every check that uses it (the footing statics record `k_m`, `c_S` and `c_I` in the trace of each check whose
`COMPRESSION` runs them; one-way shear and flexure share `c_half` between the statics integrals and their own steps).
A trace constant must cite its spec's §5 (bearing BP-AC3), so per-spec citation texts would need one `Cited` per spec
for the same name in the same trace, which the recorder refuses (a name recorded twice). Decision: **one citation text
per shared constant**, the `Cited.source` below, written verbatim (plain text, no code formatting) in the Citation
cell of the constant's row in §5 of every clause spec that uses it. Where a text must cover several uses, it lists
them (`c_half`) or names every clause that sets the same value (`sf_max`); each spec's §4 says which use or clause
applies. A check whose constant is not the shared one keeps its own `Cited` and its own row text (development length's
`c_half`, recorded by that check alone; it never runs the statics). No value changes.

| Name | Value | Unit | `Cited.source` (and `Cited.note`) | Clause specs whose §5 cite it |
|---|---|---|---|---|
| `phi_v` | 0.75 | 1 | ACI 318-14 Table 21.2.1, row (b) shear | one-way, punching |
| `lambda_nw` | 1.0 | 1 | ACI 318-14 19.2.4.2 (normalweight concrete) | one-way, punching, development |
| `sf_max` | 8.3 | 1 | ACI 318-14 22.5.3.1, 22.6.3.1, 25.4.1.4 (limit on sqrt f'c); note: true unit MPa^0.5; stored as 1 because the eng-contract unit table has no MPa^0.5 (plan 0002 §6 Q6) | one-way, punching, development |
| `fc_min` | 17 | MPa | ACI 318-14 Table 19.2.1.1 (minimum f'c, general row) | one-way, punching, flexure, development, axial |
| `fy_max` | 550 | MPa | ACI 318-14 Table 20.2.2.4(a) (not special seismic) | flexure, minimum reinforcement, development, axial |
| `k_m` | 0.001 | 1 | SI prefix milli: m per mm (EC §4.7.3) | bearing, one-way, punching, flexure |
| `k_kN` | 0.001 | 1 | SI prefix kilo: kN per N (EC §4.7.3) | one-way, punching (trace name `k_kilo`), axial |
| `k_kNm` | 1.0e-6 | 1 | SI prefixes kilo and milli: kN.m per N.mm (EC §4.7.3) | flexure (trace name `k_kilo_milli`), axial |
| `c_S` | 6 | 1 | Mechanics of materials: section modulus of a rectangle, b*h^2/6 | bearing, one-way, punching, flexure |
| `c_I` | 12 | 1 | Mechanics of materials: second moment of a rectangle, b*h^3/12 | bearing, one-way, punching, flexure |
| `c_half` | 2 | 1 | Statics and geometry: factor 2 of a half or a pair (L/2 and c/2 of a centered footing and column, the midpoint xbar, the resultant at a/2, the integral Lp^2/2, mid-depth h/2, the bisection midpoint, two side bars per inner layer) | one-way, flexure, axial (plan 0004 T1 moves the column constants into `_common.py`) |
| `c_third` | 3 | 1 | Statics: integral of u^2 du over a cantilever, Lp^3/3 | flexure |

Every text except `c_half` is the source merged in T2 (B-271), so only `c_half` and the `sf_max` note change in code
(T2c). The texts start with the prefixes of PK-AC4.

Constants that become shared later fall under the same rule. Plan 0004 T1 moves the stress-block and `φ` constants of
the flexure module (`phi_tc`, `eps_tc`, `eps_cu`, `alpha_1`, `beta1_hi`, `beta1_slope`, `beta1_step`, `fc_beta_lo`,
`fc_beta_hi`, `beta1_lo`) into `_common.py`, and they then become keys of `CITED` that the T2c test checks. Their rows
in the flexure and axial-flexure specs §5 are therefore already aligned (B-421) to one plain-text Citation cell equal
to the source merged in `checks/flexure.py` (B-275), with the values of the flexure spec; plan 0004 T1 moves the
`Cited` objects unchanged and needs no clause spec change.

## 2. Tasks

**T1 Skeleton.** Creates `packages/structural-codes/aci318-14/` as a uv workspace member (D-10):
`name = "structural-codes-aci318-14"`, `version = "0.1.0.dev0"`, `requires-python = ">=3.14,<3.15"`, dependencies
`structural-codes-core` and `eng-contract` (workspace sources); `[tool.eng-gate]` with `profile = "codes"`,
`layer = 3`, `import_names = ["aci318_14"]`, `check_modules = ["src/aci318_14/**/*.py"]` (CF §4.5: the whole pack
source), `r1_modules` = every module under `src/aci318_14/`, thresholds line 95, branch 90, mutation 80 (process/05
§2); `approvals.yaml` as package data with `approvals: []` and `withdrawn: []` (CF §4.8). Adds the pack's paths to
the shared `.gate/risk-map.yml` as `r1`, renders the shared `AGENTS.md` again, and adds the rows of §4 to
`docs/local-testing.md`. `__init__.py` holds `__version__` only; the empty `checks/` package exists so T3 to T8 never
touch a shared file.

**T2 Shared statics and constants.** `_footing.py`: FS S1 to S5 of the bearing spec as functions that record their
steps on the caller's `TraceRecorder` (so every intermediate appears in each check's trace) and the two exact
integrals of the one-way shear and flexure specs. `_common.py`: the `Cited` constants used by more than one check
(`phi_v`, `lambda_nw`, `sf_max`, `fc_min`, `fy_max`, SI prefixes, mechanics identities) and the shared preconditions
`NORMALWEIGHT`, `FC_MIN`, `FY_MAX`, `COMPRESSION`, `FULL_CONTACT` with their clauses. `FC_MIN` uses the general row
of Table 19.2.1.1 and carries the recorded SDC assumption of the clause specs (§6 Q16). R1 module; reviewed with the
source-check lens.

**T2b Rectangular statics tests** (amendment B-421, test-only). Adds to `tests/unit/test_footing_statics.py` cases with
`Lx ≠ Ly`, `cx ≠ cy`, `d_x ≠ d_y` and a moment about each axis, asserting both directions, so that swapping X and Y
in S1, S2, the S5 modulus pairing or the `_AXES` table fails a test. Hand values (strength form, `N = FZ`), derived
from the bearing spec §4.1, the one-way spec §4 steps 2 and 3 and the flexure spec §4 steps 2 and 3; synthetic inputs,
no project values:

- Case R1: `Lx = 2000`, `Ly = 3000`, `cx = 400`, `cy = 600`, `d_x = 450`, `d_y = 500` (mm), `FZ = 1500 kN`,
  `MX = −100 kN.m`, `MY = −150 kN.m`, `FX = FY = 0`, `reaction_height = 0`.
  S1: `A = 2000·3000 = 6.0e6 mm2`; `Sx = 2000·3000²/6 = 3.0e9 mm3`; `Sy = 3000·2000²/6 = 2.0e9 mm3`;
  `Ix = 2000·3000³/12 = 4.5e12 mm4`; `Iy = 3000·2000³/12 = 2.0e12 mm4`. S2: `Mbx = −(−100) = 100 kN.m`,
  `Mby = −(−150) = 150 kN.m`. S5: `q_avg = 1500/6.0 = 250 kPa`; `q_bend = 100/3.0 + 150/2.0 = 108.333333 kPa`;
  `q_max = 358.333333 kPa`, `q_min = 141.666667 kPa` (the swapped pairing `100/2.0 + 150/3.0` gives 100 kPa).
  One-way X (span `Lx`, width `Ly`, `Mby`, `Iy`): `Lc_x = 1000 − 200 − 450 = 350 mm`;
  `x̄_x = (200 + 450 + 1000)/2 = 825 mm`; `Vu_x = 3.0·0.35·(250 + 150·0.825/2.0) = 1.05·311.875 = 327.46875 kN`
  (pairing `Mbx`, `Ix` instead would give 281.75 kN).
  One-way Y (span `Ly`, width `Lx`, `Mbx`, `Ix`): `Lc_y = 1500 − 300 − 500 = 700 mm`;
  `x̄_y = (300 + 500 + 1500)/2 = 1150 mm`; `Vu_y = 2.0·0.7·(250 + 100·1.15/4.5) = 350 + 35.777778 = 385.777778 kN`.
  Flexure X: `Lp_x = 1000 − 200 = 800 mm`, `a = 0.2 m`, `|Mby|/Iy = 75 kPa/m`;
  `Mu_x = 3.0·[250·0.8²/2 + 75·(0.8³/3 + 0.2·0.8²/2)] = 3.0·[80 + 75·0.234667] = 3.0·97.6 = 292.8 kN.m`.
  Flexure Y: `Lp_y = 1500 − 300 = 1200 mm`, `a = 0.3 m`, `|Mbx|/Ix = 100/4.5 kPa/m`;
  `Mu_y = 2.0·[250·1.2²/2 + (100/4.5)·(1.2³/3 + 0.3·1.2²/2)] = 2.0·[180 + (100/4.5)·0.792] = 2.0·197.6 = 395.2 kN.m`.
- Case R2 (S2 pairing): R1 geometry with `MX = MY = 0`, `FX = 200 kN`, `FY = −100 kN`, `reaction_height = 500 mm`.
  S2: `Mbx = 0 + 0.5·(−100) = −50 kN.m`, `Mby = 0 − 0.5·200 = −100 kN.m`; S5: `q_bend = 50/3.0 + 100/2.0 =
  66.666667 kPa`, `q_max = 316.666667 kPa`, `q_min = 183.333333 kPa` (pairing `FX` with `Mbx` would give 58.333333 kPa).

Tolerances as the existing statics tests (exact steps to floating-point rounding; the absolute kN and kN.m tolerances
of the one-way and flexure hand checks for `Vu` and `Mu`).

**T2c Shared citation texts** (amendment B-421). `_common.py`: `c_half` takes the source of §1.1, `sf_max` gains the
`Cited.note` of §1.1, and the module docstring says "`sf_max` in MPa^0.5 stored with unit 1, plan §6 Q6" (Q6 now
records that decision). Test `test_shared_sources_match_clause_specs` in `tests/unit/test_common.py` reads §5 of every
clause spec under `packages/structural-codes/docs/clauses/aci318_14/` and, for each row whose Symbol is a key of
`CITED`, asserts the Citation cell equals `CITED[name].source`, the Value cell equals its value and the Unit cell its
unit (a key added later, such as the plan 0004 T1 constants of §1.1, is checked the same way with no test change);
it also asserts every key of `CITED` has at least one such row and that the `sf_max` note is the text of §1.1.
A development-length row named `c_half` is that check's own constant (§1.1) and is excluded by name. It fails at the
base because the merged `c_half` source and the missing `sf_max` note differ from the specs. `test_footing_statics.py`
may assert that the constants recorded by `statics`, `one_way_shears` and `face_moments` are the `CITED` objects.

**T3 to T8 Checks.** One check per task, each with its unit tests, its hand-check case file
(`tests/data/golden/verification/<check_id>.yaml`, a protected test oracle, CF §4.9.1), its golden test (runs
`verify_check` and asserts every hand check passes and the report lists the worked example and, where applicable,
the program comparison as unmet) and its property test. Each `CheckMeta.spec` is `aci318_14/<check_id>.md` (see §6
Q12). Gap ids are declared in `CheckMeta.gaps` exactly as numbered in the clause spec. Independent of each other once
T2 is merged; they may run in parallel.

**T9 Assembly.** `PACK = Pack("aci318_14", "ACI 318-14", "2014", __version__, checks=(...), approvals=...)` and the
entry point `[project.entry-points."structural_codes.packs"] aci318_14 = "aci318_14:PACK"`; README usage of
`structural_codes.evaluate` with the bearing check; changelog entry for 0.1.0.

## 3. Pack-level acceptance criteria

Test paths relative to `packages/structural-codes/aci318-14/`. Per-check criteria (BP, OS, PS, FL, MR, DL) are in §11
of each clause spec.

- PK-AC1. Given the package, when imported, then `__version__` is set and the shipped `approvals.yaml` loads as an
  empty file (CF AC23). Test: `tests/unit/test_package.py::test_version_and_empty_approvals`.
- PK-AC2. Given each shared precondition, when tested just below, at and above its limit, then the outcomes of the
  clause specs (`fc = 17` passes `FC_MIN`, `fy = 550` passes `FY_MAX`, `q_min = 0` passes `FULL_CONTACT`). Test:
  `tests/unit/test_common.py::test_shared_preconditions`.
- PK-AC3. Given `Registry.discover()`, when the pack is loaded, then it holds exactly the check ids of the pack's merged plans (the six of §1 and those of later plans of the pack) and each
  `CheckMeta.spec` names an existing clause spec file. Test: `tests/unit/test_pack.py::test_registry_and_specs`.
- PK-AC4. Given every check, when `lint_scope_violations(check, check_modules)` runs, then it is empty; and every
  `Cited` source in the pack starts with `ACI 318-14 `, `SI prefix`, `Mechanics of materials`, `Statics`, `Geometry`
  or names a physical bound. Test: `tests/unit/test_pack.py::test_lint_scope_and_citations`.
- PK-AC5. Given one footing evaluated by all six checks with literal hand-check inputs, when the payloads are built,
  then each validates as `verdicts.set/1` with `draft: true` and the expected verdict count (1, 2, 1, 2, 2, 2). Test:
  `tests/contract/test_pack_payloads.py::test_all_checks_payload`.
- PK-AC6. Given the shipped `approvals.yaml`, when each check's state is resolved, then `draft`; in `production` mode
  every check is refused with `CheckNotUsable` (CF AC25). Test: `tests/unit/test_pack.py::test_all_draft`.
- PK-AC7. Given the hand-check inputs, when evaluated in two subprocesses with `PYTHONHASHSEED` 0 and 1, then the
  canonical JSON of the payloads is byte-identical. Test: `tests/replay/test_pack_determinism.py::test_identical_across_hash_seeds`.
- PK-AC8. Given the pack, when `python -m structural_codes verify --pack P` runs with `P` the pack project root
  `packages/structural-codes/aci318-14/` (CF §4.9.3, amendment B-419), then it exits 0, every hand
  check passes, program comparisons are `pending` (needs local test) and every check is reported not `verified`
  (worked example missing, G-WE). Test: `tests/unit/test_verify_cli.py::test_verify_reports_unverified`.
- PK-AC9. Given the package, when the gate runs, then line coverage ≥ 95%, branch ≥ 90%, mutation ≥ 80% on the R1
  modules (process/05 §2), and imports are limited to `structural_codes`, `eng_contract` and the standard library.
  Evidence: the CI `gate` job (T9 pull request).
- PK-AC10. Given the rectangular cases R1 and R2 of §2 T2b, when the shared statics and both integrals run, then
  `Sx`, `Sy`, `Ix`, `Iy`, `Mbx`, `Mby`, `q_max`, `q_min`, and in both directions `Lc`, `x̄`, `Vu`, `Lp`, `Mu` equal
  the hand values. Tests: `tests/unit/test_footing_statics.py::test_rectangular_statics`,
  `tests/unit/test_footing_statics.py::test_rectangular_integrals`.
- PK-AC11. Given the clause specs §5 and `CITED`, when compared, then every shared constant's source, value and unit
  equal its rows in each clause spec that cites it (§1.1), and `sf_max` carries the note of §1.1. Test:
  `tests/unit/test_common.py::test_shared_sources_match_clause_specs`.

No fake-host workflow test applies: the checks touch no host. The footing workflow's fake-host and replay tests belong
to B-075.

## 4. Verification and local testing

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` exists; until then `uv run ruff format --check`,
  `uv run ruff check`, `uv run mypy --strict src tests` and `uv run pytest` with coverage, from
  `packages/structural-codes/aci318-14/`.
- Hand-check tolerances are absolute and stated in §8 of each clause spec. They replace the default of
  [10](../../../../design/docs/architecture/10-structural-codes.md) §6 (0.5% relative with an absolute floor) for hand
  checks only, because a hand check repeats the spec's own equations and differs from the check only by floating-point
  rounding; worked examples and program comparisons keep the 10 §6 default.
- Review: each pull request by a subagent that did not write it, with the R1 source-check lens (constants and
  equations against the clause spec, tracing of every intermediate). The C3 line-by-line comparison against the code
  text and the owner's G1 approval are `awaiting owner` in bootstrap mode.
- Needs local test (T1 writes these rows to `packages/structural-codes/docs/local-testing.md`; none is claimed here):

| Item | Host | What is compared |
|---|---|---|
| PC-1 bearing | SAFE | Soil pressure under a service combination for the bearing HC-2 footing |
| PC-1 one-way shear | SAFE | One-way shear at `d` from the face, if SAFE reports it for footings |
| PC-1 punching | SAFE | Punching shear ratio of the punching HC-1 footing, assumption differences listed |
| PC-1 flexure | SAFE | Strip moment at the column face for the flexure HC-2 footing |
| PC-1 minimum reinforcement | SAFE | Minimum steel in footing strips |
| Reaction convention | ETABS or SAFE | Signs of `FX`, `FY`, `MX`, `MY` in `forces.joint_reactions/1`, which FS S2 combines with the reaction height |

## 5. Dependencies and rollback

- Runtime: `structural-codes-core`, `eng-contract` (workspace). No new third-party dependency.
- Development: the root dependency group (`pytest`, `hypothesis`, `ruff`, `mypy`, `pytest-cov`).
- Rollback: each task is one squash-merged pull request on `build/v1`; the checks have no consumer until B-075, so a
  task is reverted by reverting its commit (with T9 if registered). After B-075 uses them, a defect is fixed forward
  with a regression case; any output change carries a golden diff report and is a major version of the pack
  (process/10 §5).

## 6. Open questions, gaps and non-goals

### 6.1 Questions (owner queue, with the author's recommendation)

| Id | Question | Recommendation |
|---|---|---|
| Q1 | Signed force inputs (`FX_kN` to `MY_kNm`) have no physical bound, but CF AC3 requires bounds and `bounds_source` on every numeric field | Resolved by B-097: the core spec allows `unbounded(reason=...)` (core §4.3, AC4a), implemented by core T3; T2 declares the signed force fields with it |
| Q2 | Design-basis field paths used by the clause specs (`foundation.allowable_bearing_pressure_kPa`, `foundation.allowable_bearing_kind`, `foundation.soil_unit_weight_kN_m3`, `foundation.soil_depth_above_footing_mm`, `foundation.surcharge_kPa`, `materials.concrete_fc_MPa`, `materials.concrete_class`, `materials.concrete_unit_weight_kN_m3`, `materials.rebar_fy_MPa`, `materials.rebar_coating`, `durability.cover_footing_mm`, `limits.ratio_limit_ratio`) | Adopt them in the design-basis template spec (B-063), or rename there and here together. Quantity paths carry the contract §4.7.2 unit suffix (owner decision OQ-Q44; amendments B-467, B-484); the clause specs name them without it until the owner renames them |
| Q3 | Punching with moment transfer (punching G-4): whether the Chapter 8 eccentric-shear rule applies to footings through 13.3.3.1 | Confirm at C3; then implement it as a new check version, since most real footings carry a base moment |
| Q4 | Strength checks use the net factored pressure from the column load only (footing and soil weights excluded) | Accept: the uniform self-weight pressure is balanced by the weight itself and causes no shear or moment in the footing |
| Q5 | Punching uses one effective depth `d` | B-075 passes the mean of `d_x` and `d_y`; confirm |
| Q6 | √MPa-valued steps (`sf`) are recorded with unit null because `UNITS` has no such unit. Amended (B-421): the constant `sf_max` (8.3, a limit on √f'c, true unit MPa^0.5) is stored with unit `1` for the same reason, its true unit in `Cited.note` ("true unit MPa^0.5; stored as 1 because the eng-contract unit table has no MPa^0.5 (plan 0002 §6 Q6)"); likewise the pack's √MPa coefficients (`c_vc` 0.17 of eq. 22.5.5.1, `c_a` 0.33, `c_b` 0.17 and `c_c` 0.083 of Table 22.6.5.2, `c_ld` 1.1 of eq. 25.4.2.3a) are stored with unit `1`, their true unit named in the citation ("..., coefficient in MPa^0.5"), as the merged checks already record them; only steps (`sf`) keep unit null; ratios of like units (`k_m` m per mm, `k_kN` kN per N, `k_kNm` kN.m per N.mm) are recorded with unit `1`, the ratio named in the citation. The clause specs' §5 unit columns say `1` for these rows | Accept; the formula (steps) or the note and citation (constants) name the unit |
| Q7 | Detailing clauses not checked: band rule for rectangular footings, bar spacing limits | Add detailing checks in a later version; B-075 uses uniform spacing on square footings until then |
| Q8 | `FY_MAX` uses the row for members that are not part of a special seismic system | B-075 refuses footings of special seismic systems until seismic checks exist |
| Q9 | Minimum flexural reinforcement: two-way slab minimum through 13.3.3.1, or also a beam-type minimum | Slab minimum (8.6.1.1), as specified; owner confirms |
| Q10 | Development length uses `ψs = 1.0` for every bar, because metric bar sizes do not map to ASTM designations | Keep (safe side) until a typed bar-designation input exists |
| Q11 | Development length has no program comparison (`program_comparison.not_available`) | Confirm |
| Q12 | Folder name: the core spec (CF §4.1, §4.2) places clause specs under `docs/clause-specs/<pack>/`; this task placed them under `docs/clauses/aci318_14/` | Resolved by B-097: the core spec now names `docs/clauses/<pack>/` |
| Q13 | Minimum effective depth of footings (13.3.1.2) is not in the 10 §9 list | Add a check `aci318_14.13_3_1_2.min_effective_depth` in a later version |
| Q14 | Bearing at the column-footing interface and dowels are not in scope (clause numbers confirmed when specified) | Add with the column workflow (phase 3) |
| Q15 | process/05 §2 requires worked examples for every check in `structural-codes`; none exists here | The gate reports this `awaiting owner` in bootstrap mode; the owner supplies G-WE |
| Q16 | `FC_MIN` (`fc_min = 17 MPa`) is the general row of Table 19.2.1.1; the table's foundation rows depend on the Seismic Design Category, and their limits are not confirmed here (one-way C-2, punching C-1, flexure C-2, development C-3) | Confirm the foundation rows at C3; until then B-075 refuses footings of structures in SDC D, E or F (`NEEDS_ENGINEER`), which needs a design-basis field for the SDC (B-063) |

### 6.2 Gaps

| Id | Gap | Where |
|---|---|---|
| G-WE | No worked example from a book or the code's own examples: the owner supplies book, edition, page and example number for each of the six checks; every case here is a labeled hand check | WE-1 of each clause spec |
| Check gaps | Bearing G-1, G-2; one-way G-1, G-2; punching G-1 to G-4; flexure G-1, G-2; development G-1, G-2: each returns `NEEDS_ENGINEER` and is tested | §10 of each clause spec |
| C items | Clause chains to confirm at C3: one-way C-1 (critical section at `d`), flexure C-1 (`fy_max` row, `β1` boundary), minimum reinforcement C-1, development C-1; the foundation rows of Table 19.2.1.1 behind `FC_MIN` (one-way C-2, punching C-1, flexure C-2, development C-3; Q16) | §10 of each clause spec |

### 6.3 Non-goals

Sloped, stepped or tapered footings; combined, strip and mat footings; pile caps; columns off the footing center;
circular columns; footings rotated from the global axes; partial soil contact and uplift; lightweight concrete;
coated bars; hooked or headed bars; shear reinforcement; seismic detailing; net allowable pressure; load-combination
generation; the SBC 304-2018 overlay (B-072); the footing block and workflow (B-075).
