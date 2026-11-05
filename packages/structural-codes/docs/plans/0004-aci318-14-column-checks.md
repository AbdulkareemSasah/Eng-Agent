---
id: plan-b082-aci318-14-column-checks
issue: "B-082"
spec: packages/structural-codes/docs/clauses/aci318_14/   # a directory on purpose: this plan's spec is the three clause specs of §1, one per check
status: draft            # draft | approved (approved only by merging this file's own pull request)
size: standard
risk: r1                 # binding for every pull request of this plan
tasks:
  - id: T1
    title: Shared column section model, column preconditions, shared constants moved to _common.py
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/_column.py"
      - "packages/structural-codes/aci318-14/src/aci318_14/_common.py"
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/flexure.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_column_section.py"
    max_changed_lines: 300
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/unit/test_column_section.py::test_section_point_sp1"
      - "packages/structural-codes/aci318-14/tests/unit/test_column_section.py::test_phi_rows_and_axial_cap"
      - "packages/structural-codes/aci318-14/tests/unit/test_column_section.py::test_column_preconditions"
    covers: [AF-AC1, AF-AC2, MA-AC3, CK-AC1]
    depends_on: []
  - id: T2
    title: Check max_axial_strength (22.4.2.1)
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/max_axial.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_max_axial.py"
      - "packages/structural-codes/aci318-14/tests/golden/test_max_axial_cases.py"
      - "packages/structural-codes/aci318-14/tests/property/test_max_axial_props.py"
      - "packages/structural-codes/aci318-14/tests/data/golden/verification/aci318_14.22_4_2_1.max_axial_strength.yaml"
    max_changed_lines: 120
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/golden/test_max_axial_cases.py::test_hand_checks"
      - "packages/structural-codes/aci318-14/tests/unit/test_max_axial.py::test_preconditions"
      - "packages/structural-codes/aci318-14/tests/property/test_max_axial_props.py::test_monotone"
    covers: [MA-AC1, MA-AC2, MA-AC4]
    depends_on: [T1]
  - id: T3
    title: Check axial_flexure_uniaxial (22.4.1.1), strain compatibility with the capped ray capacity
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/axial_flexure.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_axial_flexure.py"
      - "packages/structural-codes/aci318-14/tests/golden/test_axial_flexure_cases.py"
      - "packages/structural-codes/aci318-14/tests/property/test_axial_flexure_props.py"
      - "packages/structural-codes/aci318-14/tests/data/golden/verification/aci318_14.22_4_1_1.axial_flexure_uniaxial.yaml"
    max_changed_lines: 300
    max_sessions: 3
    tests_first:
      - "packages/structural-codes/aci318-14/tests/golden/test_axial_flexure_cases.py::test_hand_checks"
      - "packages/structural-codes/aci318-14/tests/unit/test_axial_flexure.py::test_preconditions"
      - "packages/structural-codes/aci318-14/tests/unit/test_axial_flexure.py::test_bracketing_gap"
      - "packages/structural-codes/aci318-14/tests/unit/test_axial_flexure.py::test_trace_complete"
      - "packages/structural-codes/aci318-14/tests/property/test_axial_flexure_props.py::test_monotone_and_ray"
    covers: [AF-AC3, AF-AC4, AF-AC5, AF-AC6]
    depends_on: [T1]
  - id: T4
    title: Check longitudinal_reinforcement_limits (10.6.1.1)
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/checks/reinforcement_limits.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_reinforcement_limits.py"
      - "packages/structural-codes/aci318-14/tests/golden/test_reinforcement_limits_cases.py"
      - "packages/structural-codes/aci318-14/tests/property/test_reinforcement_limits_props.py"
      - "packages/structural-codes/aci318-14/tests/data/golden/verification/aci318_14.10_6_1_1.longitudinal_reinforcement_limits.yaml"
    max_changed_lines: 80
    max_sessions: 1
    tests_first:
      - "packages/structural-codes/aci318-14/tests/golden/test_reinforcement_limits_cases.py::test_hand_checks"
      - "packages/structural-codes/aci318-14/tests/unit/test_reinforcement_limits.py::test_limits_and_preconditions"
      - "packages/structural-codes/aci318-14/tests/property/test_reinforcement_limits_props.py::test_monotone_and_scale"
    covers: [RL-AC1, RL-AC2, RL-AC3]
    depends_on: [T1]
  - id: T5
    title: Register the column checks, pack-level tests, changelog and local-testing rows
    files:
      - "packages/structural-codes/aci318-14/src/aci318_14/__init__.py"
      - "packages/structural-codes/aci318-14/CHANGELOG.md"
      - "packages/structural-codes/docs/local-testing.md"
      - "packages/structural-codes/aci318-14/tests/unit/test_pack.py"
      - "packages/structural-codes/aci318-14/tests/unit/test_pack_columns.py"
      - "packages/structural-codes/aci318-14/tests/contract/test_column_payloads.py"
      - "packages/structural-codes/aci318-14/tests/replay/test_column_determinism.py"
    max_changed_lines: 80
    max_sessions: 2
    tests_first:
      - "packages/structural-codes/aci318-14/tests/unit/test_pack_columns.py::test_registry_and_specs"
      - "packages/structural-codes/aci318-14/tests/unit/test_pack_columns.py::test_lint_scope_and_citations"
      - "packages/structural-codes/aci318-14/tests/unit/test_pack_columns.py::test_all_draft"
      - "packages/structural-codes/aci318-14/tests/unit/test_pack_columns.py::test_verify_reports_unverified"
      - "packages/structural-codes/aci318-14/tests/contract/test_column_payloads.py::test_column_checks_payload"
      - "packages/structural-codes/aci318-14/tests/replay/test_column_determinism.py::test_identical_across_hash_seeds"
    covers: [CK-AC2, CK-AC3, CK-AC4, CK-AC5, CK-AC6, CK-AC7, CK-AC8]
    depends_on: [T2, T3, T4]
---

# Implementation plan: ACI 318-14 column checks

Package: `structural-codes-aci318-14` (import package `aci318_14`), in `packages/structural-codes/aci318-14/`, layer 3
([10](../../../../design/docs/architecture/10-structural-codes.md) §2 and §9), on the core framework
([spec 0001](../specs/0001-core-framework.md), "CF §n"; [plan 0001](0001-core-framework.md)) and after the footing
checks ([plan 0002](0002-aci318-14-footing-checks.md)), whose skeleton, shared module and registration this plan
extends. File paths in the front matter are relative to the workspace root; `max_changed_lines` counts non-test,
non-generated lines ([process/04](../../../../design/process/04-implementation-rules.md) §4). Bootstrap mode
([ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4): this plan and its clause specs are
`draft`, every check ships `draft`, and `approvals.yaml` stays empty.

## 1. Approach

The scope is the column axial-flexure list of 10 §9 as narrowed by B-082: three checks, each specified by one clause
spec (the spec of this plan, written from
[process/templates/clause-spec.md](../../../../design/process/templates/clause-spec.md)):

| Check | Clause spec | Verdicts per column section and case |
|---|---|---|
| `aci318_14.22_4_2_1.max_axial_strength` | [maximum axial strength](../clauses/aci318_14/aci318_14.22_4_2_1.max_axial_strength.md) (also defines the shared column preconditions CP) | 1 |
| `aci318_14.22_4_1_1.axial_flexure_uniaxial` | [axial force with uniaxial flexure](../clauses/aci318_14/aci318_14.22_4_1_1.axial_flexure_uniaxial.md) (also defines the shared section model CS S1 to S7) | 1 |
| `aci318_14.10_6_1_1.longitudinal_reinforcement_limits` | [longitudinal reinforcement limits](../clauses/aci318_14/aci318_14.10_6_1_1.longitudinal_reinforcement_limits.md) | 2 (minimum, maximum) per section |

What is computed and what is not:

| Topic | In this plan | Gap (returns `NEEDS_ENGINEER`, tested) |
|---|---|---|
| Nominal and maximum axial strength, tied and spiral | Eq. 22.4.2.2, Table 22.4.2.1 | prestressed and composite columns (non-goal) |
| Strength reduction factor from the net tensile strain | Table 21.2.2 rows, `εty = fy/Es` | — |
| Axial force with uniaxial flexure | strain compatibility (22.2), stress block (22.2.2.4), `εcu` (22.2.2.1), steel model (20.2.2.1), axial cap | axial tension (G-3), non-unique ray intersection (G-4) |
| Biaxial bending | — | G-1: no method the author can cite in the code's normative text (Q3) |
| Slenderness | applicability limit only: `k·lu/r <= 22` (6.2.5(a)), `r = 0.30·min(b, h)` (6.2.5.1(b)) | G-2: moment magnification and second-order analysis |
| Longitudinal reinforcement ratio | `0.01·Ag <= Ast <= 0.08·Ag` (10.6.1.1) | reduced effective area of 10.3.1.2 not used (safe side) |

Every equation uses the SI form; every constant is a `Cited` value whose source is the clause, table or equation of its
clause spec (or an SI prefix, a statics or geometry identity, or the one numerical-method parameter `n_grid`, named as
such, Q7). Every clause number is the author's reading of the code, written without the code text at hand, so each is a
C item that the C3 verifier confirms line by line ([process/10](../../../../design/process/10-engineering-verification.md)
§3); where the author was not certain of a clause's content, the check returns `NEEDS_ENGINEER`. No value is guessed.

Inputs arrive as references (CF §4.3, EC §5): forces from a `forces.member_end/1` row of the column at the station
checked, converted by the column workflow (B-083) to compression-positive `Pu_kN` and moment magnitudes (Q2); material
values from `basis.design_basis/1`; section and layout from the column block (B-083). The harness calls the checks
through `ctx.calc` in batch (10 §7); the checks are pure and touch no host.

Order: the section model first (T1), because both strength checks use it and the axial-flexure check is the riskiest
logic (strain compatibility, `φ` transitions, root search); T1 also moves the stress-block and `φ` constants that plan
0002 T6 defines in the flexure module into `_common.py`, so each constant has one definition (no output change: the
flexure golden cases must stay green). Then the three checks in parallel (disjoint files), then registration (T5). Each
task is test-first ([process/05](../../../../design/process/05-testing-and-verification.md) §9).

Start condition: plan 0002 T2 (`_common.py`), T6 (flexure constants) and T9 (pack assembly) are merged before T1; core
plan 0001 tasks T6, T8, T9, T11 and T12 are merged before T2 to T5 (checks, runner, verification, lifecycle, command
line), and T14a (public modules declared; amendment B-385) before T1. Q12 of plan 0002 (clause-spec folder) applies here unchanged.

## 2. Tasks

**T1 Section model.** `_column.py`: CS S1 to S7 of the axial-flexure spec as functions that record their steps on the
caller's `TraceRecorder` (layout, `εty`, `β1`, section forces at a given `c`, `εt`, `φ`, `Po`, `Pn_max`, `phiPn_max`,
`c_full`), the column constants of the axial-flexure spec §5 that more than one check uses, and the CP preconditions
(`BAR_LAYOUT`, `STEEL_IN_SECTION`, `SHORT_COLUMN`, `AXIAL_COMPRESSION`; `FC_MIN` and `FY_MAX` are reused from
`_common.py`). The section function takes `c` as an argument so SP-1 tests it at the balanced depth without a root
search. R1 module; reviewed with the source-check lens.

**T2 to T4 Checks.** One check per task, each with its unit tests, its hand-check case file (a protected test oracle,
CF §4.9.1), its golden test (runs `verify_check`: every hand check passes, the worked example and the program comparison
are reported unmet) and its property test. `CheckMeta.spec` is `aci318_14/<check_id>.md`; `CheckMeta.members` is
`{frame}` (Q1); gap ids in `CheckMeta.gaps` exactly as numbered in the clause spec. T3 holds the bracketing and
bisection of AF §4.2 as a private helper with its own unit test (BD-5); it is the largest task and has three sessions.

**T5 Registration.** Adds the three checks to `PACK.checks` in `__init__.py`; extends the expected id set of plan 0002's
`test_pack.py::test_registry_and_specs` from six to nine (a scope change approved by this plan, not a weakened
expectation; Q11); adds `test_pack_columns.py` for the column checks; changelog entry; the rows of §4 to
`packages/structural-codes/docs/local-testing.md`.

## 3. Pack-level acceptance criteria

Test paths relative to `packages/structural-codes/aci318-14/`. Per-check criteria (MA, AF, RL) are in §11 of each
clause spec.

- CK-AC1. Given plan 0002's flexure case file, when its golden test runs after T1 moved the shared constants, then every
  case passes unchanged. Evidence: `tests/golden/test_flexure_cases.py::test_hand_checks` green in the T1 pull request
  (an existing test, not new).
- CK-AC2. Given `Registry.discover()`, when the pack is loaded, then it holds the six footing ids of plan 0002 and the
  three ids of §1, and each column `CheckMeta.spec` names an existing clause spec file. Test:
  `tests/unit/test_pack_columns.py::test_registry_and_specs`.
- CK-AC3. Given each column check, when `lint_scope_violations(check, check_modules)` runs, then it is empty; every
  `Cited` source starts with `ACI 318-14 `, `SI prefix`, `Statics`, `Geometry`, `Numerical method` or names a physical
  bound. Test: `tests/unit/test_pack_columns.py::test_lint_scope_and_citations`.
- CK-AC4. Given one column section evaluated by the three checks with the hand-check inputs, when the payloads are
  built, then each validates as `verdicts.set/1` with `draft: true` and verdict counts 1, 1, 2. Test:
  `tests/contract/test_column_payloads.py::test_column_checks_payload`.
- CK-AC5. Given the shipped `approvals.yaml`, when each column check's state is resolved, then `draft`; in `production`
  mode each is refused with `CheckNotUsable` (CF AC25). Test: `tests/unit/test_pack_columns.py::test_all_draft`.
- CK-AC6. Given the hand-check inputs, when evaluated in two subprocesses with `PYTHONHASHSEED` 0 and 1, then the
  canonical JSON of the payloads is byte-identical (the root search is deterministic). Test:
  `tests/replay/test_column_determinism.py::test_identical_across_hash_seeds`.
- CK-AC7. Given the pack, when `python -m structural_codes verify --pack aci318_14` runs, then it exits 0, every column
  hand check passes, program comparisons are `pending` and no column check is reported `verified` (G-WE). Test:
  `tests/unit/test_pack_columns.py::test_verify_reports_unverified`.
- CK-AC8. Given the package, when the gate runs, then line coverage ≥ 95%, branch ≥ 90%, mutation ≥ 80% on the R1
  modules (process/05 §2), including `_column.py` and the three check modules. Evidence: the CI `gate` job (T5 pull
  request).

No fake-host workflow test applies: the checks touch no host. The column workflow's fake-host and replay tests belong to
B-083.

## 4. Verification and local testing

- Local gate per task: `uv run eng-gate check` once `eng-dev-gate` covers the package; until then `uv run ruff format
  --check`, `uv run ruff check`, `uv run mypy --strict src tests` and `uv run pytest` with coverage, from
  `packages/structural-codes/aci318-14/`.
- Hand-check tolerances are absolute and stated in §8 of each clause spec; they replace the default of
  [10](../../../../design/docs/architecture/10-structural-codes.md) §6 for hand checks only (as in plan 0002 §4).
  SP-1 was also worked by hand layer by layer; the other hand checks were computed from the spec's equations by the
  author and are not independent evidence.
- Review: each pull request by a subagent that did not write it, with the R1 source-check lens. The C3 line-by-line
  comparison against the code text and the owner's G1 approval are `awaiting owner` in bootstrap mode.
- Needs local test (T5 writes these rows to `packages/structural-codes/docs/local-testing.md`; none is claimed here):

| Item | Host | What is compared |
|---|---|---|
| PC-1 maximum axial strength | ETABS | Axial design capacity of the common section (tied, spiral) in concrete frame design to ACI 318-14 |
| PC-1 axial-flexure | ETABS | Capacity ratio of a short, uniaxially loaded column at the HC-1 and HC-3 loads; ETABS's ratio definition and assumption differences listed |
| PC-1 reinforcement limits | ETABS | Reinforcement ratio limits applied by concrete frame design to the common section |
| Force sign convention | ETABS | Sign of `P` and the axes of `M2`, `M3` in `forces.member_end/1` (EC G-3), which B-083 converts to `Pu_kN`, `Mu_kNm`, `Mu_other_kNm` |

## 5. Dependencies and rollback

- Runtime: `structural-codes-core`, `eng-contract` (workspace). No new third-party dependency.
- Development: the root dependency group (`pytest`, `hypothesis`, `ruff`, `mypy`, `pytest-cov`).
- Rollback: each task is one squash-merged pull request on `build/v1`; the column checks have no consumer until B-083,
  so a task is reverted by reverting its commit (with T5 if registered). T1 reverts together with any later task that
  imports `_column.py`. After B-083 uses them, a defect is fixed forward with a regression case and a golden diff
  report (process/10 §5).

## 6. Open questions, gaps and non-goals

### 6.1 Questions (owner queue, with the author's recommendation)

| Id | Question | Recommendation |
|---|---|---|
| Q1 | `SubjectKind` has `frame` but no `column`; the checks cannot tell a column from a beam | Keep `frame` with the recorded assumption; B-083 passes only frames of kind `column` from `model.frame_placements/1`. Add `column` to `SubjectKind` (additive) only if another consumer needs it |
| Q2 | `forces.member_end/1` uses `host_local/1` signs (EC G-3); the checks take compression-positive `Pu_kN` and moment magnitudes | B-083 converts and records the conversion in its trace; confirm the CSI convention in the local test of §4 |
| Q3 | Biaxial bending (AF G-1): which method, from which source (code clause, commentary or textbook with edition and page)? | The owner names it; until then every column with two non-zero moments returns `NEEDS_ENGINEER`, which in practice is most columns, so this is the first column follow-up |
| Q4 | Transverse reinforcement (ties per 25.7.2, spirals per 25.7.3, including the spiral ratio) is assumed, not checked, yet it selects `φ` and `Pn_max` | Add transverse-reinforcement checks with the column workflow's next version; B-083 builds tied columns only until then |
| Q5 | Effective length factor `k` has no source in the design basis | Add a per-project design-basis field (for example `columns.effective_length_factor`, B-063) set by the engineer; no default |
| Q6 | Displaced concrete removed for bars inside the stress block (AF C-3) | Keep (consistent with Eq. 22.4.2.2 and slightly conservative); C3 confirms |
| Q7 | `n_grid = 1000` is cited as "Numerical method", not a code value | Accept the citation form for numerical parameters; CK-AC3 admits it |
| Q8 | The maximum ratio is checked at a section without lap splices | B-083 evaluates the section away from laps; the owner decides whether a lap-region check is needed |
| Q9 | Reduced effective area for the minimum ratio (10.3.1.2) | Do not add until a project needs it; the full `Ag` is safe for the minimum |
| Q10 | Columns of special moment frames (Chapter 18 limits, `fy` rows of Table 20.2.2.4(a)) | B-083 refuses them until seismic checks exist; needs a design-basis field for the seismic system (B-063) |
| Q11 | T5 changes the expected id set of plan 0002's `test_pack.py` (six to nine ids) | Accept as a scope change approved by this plan; alternatively amend plan 0002 PK-AC3 to "holds at least the six ids" in the lead's next documents change |
| Q12 | The `SHORT_COLUMN` limit uses the sway value (22) for braced columns too (AF C-4) | Accept (narrower applicability, no unsafe verdict); a braced-column limit can be added once C3 confirms 6.2.5(b) and its sign convention |

### 6.2 Gaps

| Id | Gap | Where |
|---|---|---|
| G-WE | No worked example from a book or the code's own examples: the owner supplies book, edition, page and example number for each of the three checks; every case here is a labeled hand check | WE-1 of each clause spec |
| Check gaps | Maximum axial G-1, G-2; axial-flexure G-1 to G-4; reinforcement limits G-1: each returns `NEEDS_ENGINEER` (or is a recorded safe-side choice) and is tested | §10 of each clause spec |
| C items | Every clause, table and equation number (maximum axial C-1, C-2; axial-flexure C-1 to C-5; reinforcement limits C-1) | §10 of each clause spec |

### 6.3 Non-goals

Circular, L-shaped or other non-rectangular sections; unsymmetric or bundled bars; prestressed and composite columns;
slender columns (moment magnification, second-order analysis); biaxial bending; axial tension; shear, torsion and
joint checks; transverse reinforcement and detailing; lap splices; seismic provisions (Chapter 18); the SBC 304-2018
column overlay; the column workflow and Revit update (B-083).
