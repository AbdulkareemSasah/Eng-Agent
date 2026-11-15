---
id: spec-0004-templates-and-basis
issue: "B-063"
status: draft        # draft | approved (approved only by merging this file's own pull request)
size: large
risk: [r1, r2]
---

# Spec 0004: eng-harness templates and the design basis

Package: `eng-harness` (import package `eng_harness`) · Author: agent identity (bootstrap mode,
[ADR-0028](../../../../design/docs/adr/0028-build-v1-in-this-repository.md) §4) · Date: 2026-11-03

This spec implements [13-templates-and-design-basis](../../../../design/docs/architecture/13-templates-and-design-basis.md)
("13 §n") and [ADR-0017](../../../../design/docs/adr/0017-templates-and-design-basis.md), with the phase 1 interface of
[ADR-0027](../../../../design/docs/adr/0027-phase-1-interface.md). It implements the `BasisPort` of the engine
([spec 0001](0001-engine.md), "engine §n") and uses the contract of
[eng-contract spec 0001](../../../eng-contract/docs/specs/0001-eng-contract-0.1.md) ("contract §n"). It does not repeat
them. Details that 13 leaves open are marked **[added]** and listed in §11. The page that shows and confirms the basis
is spec 0006's; this spec defines the interface it implements (§4.6). The fields the edit cycle needs are spec 0007's;
this spec defines how a workflow declares them (§4.5).

## 1. Problem

Without templates the engineer retypes the same project knowledge on every run; without a design basis the harness
assumes values (P8). The session review behind
[ADR-0024](../../../../design/docs/adr/0024-harness-on-existing-sasaah-servers.md) showed runs that used values nobody
had shown to the engineer. The engine already refuses to start without a complete, confirmed basis (engine AC41) and
reads it through `ctx.basis` (engine AC17), but nothing builds, stores or presents that basis yet.

This spec must also respect rule A2: no engineering number is invented. v1 therefore ships a template that declares
structure and asks every engineering value at run start (§4.8).

## 2. Reuse research

| Candidate | Finding | Decision |
|---|---|---|
| Contract `basis.design_basis/1`, `DesignBasis.missing`, `Cited`, `Timestamp`, `ResultStore` (contract §4.8, §4.10, §4.12) | Already define the stored payload, source syntax, reference rule and required-field check | Used as is; this spec adds no kind |
| Pydantic 2 | Models, strict validation, JSON Schema | Used (already a runtime dependency) |
| `tomllib` (standard library) | No new dependency, but 13 and ADR-0017 fix the format as YAML, and engineers edit these files | Not used; format kept |
| PyYAML `safe_load` | YAML 1.1 reads `no` and `on` as booleans and `1:30` as a number; allows aliases and duplicate keys silently | Not used (Q2) |
| `ruamel.yaml` (YAML 1.2, safe mode) | Core schema without the 1.1 surprises, duplicate keys refused by default | Proposed, needs an ADR (A10, Q2) |
| Sasaah template or settings code | Read-only and out of scope (A12) | Not used |

## 3. Acceptance criteria

Template files
- AC1. Given a synthetic template with every section of 13 §2, when loaded, then it validates into `Template` and
  every leaf `Entry` has a `value`, a `unit` or null, and a `citation`. Test:
  `tests/unit/test_template_model.py::test_valid_template_loads`.
- AC2. Given an entry with no citation, a blank one, or one outside 8 to 500 characters, when loaded, then
  `TemplateInvalid` with reason `citation_missing` and the entry path. Test:
  `test_template_model.py::test_citation_required`.
- AC3. Given an unknown top-level section or an unknown key in `meta`, in an entry or in an ask item (the schema has no
  key for expressions, formulas or scripts, and a string value is never evaluated), when loaded, then `TemplateInvalid` with reason `unknown_key`. Test: `test_template_model.py::test_extra_keys_forbidden`.
- AC4. Given an entry whose last key has a unit suffix (contract §4.7.2) and a `unit` that is absent or not the
  canonical unit of that suffix (for example `kPa` under `fy_MPa`), or a unit on a key with no suffix, when loaded,
  then reason `unit_mismatch`; no conversion is attempted. Test: `test_template_model.py::test_canonical_units_only`.
- AC5. Given a numeric value that is not finite, a boolean where a number is declared, or a value outside the entry's
  `bounds`, then reason `out_of_bounds` or `value_invalid`; given `bounds` with `min` above `max` or a bound without
  its own `Cited` source, then `bounds_invalid`. Test: `test_template_model.py::test_values_and_bounds`.
- AC6. Given a `meta.name` outside `^[a-z][a-z0-9_-]{0,63}$`, a `meta.version` that is not Semantic Versioning 2.0.0, or
  a file name that is not `<name>-<version>.template.yaml`, then reason `meta_invalid`. Given `meta.synthetic: true`,
  the name must start with `synthetic-`, and the converse. Test: `test_template_model.py::test_meta_rules`.
- AC7. Given a YAML file with a duplicate key, an alias or anchor, a non-string key, a custom tag, a file over 1 MiB, or
  nesting deeper than 8 levels, then reason `yaml_invalid`; given the scalars `no`, `on`, `1:30` and `010`, then they load
  as the strings or integers of YAML 1.2, never as booleans or sexagesimal numbers. Test:
  `tests/unit/test_template_yaml.py::test_strict_loader`.

Inheritance and identity
- AC8. Given a child with `meta.extends: "<name>@<version>"`, when resolved, then mappings merge key by key, a child
  leaf replaces the parent's whole entry (value, unit and citation together), lists replace as a whole except
  `ask_each_run`, which merges by `path` (a child item replaces the parent's item with the same path), and the child
  cannot delete an inherited key or ask. Test: `tests/unit/test_template_resolve.py::test_merge_rules`.
- AC9. Given an `extends` that is missing, has no exact version, cycles, is deeper than 8, or names a version that is
  not found, then reason `extends_invalid`. Test: `test_template_resolve.py::test_extends_errors`.
- AC10. Given a resolved template where a path in `ask_each_run` also has an entry with a value, or a path asked twice,
  then reason `ask_has_value`. Test: `test_template_resolve.py::test_ask_paths_carry_no_value`.
- AC11. Given the same logical template written with different key order, comments or spacing, then the resolved
  `sha256` (of the contract canonical JSON of the resolved model, with the chain of `name@version` and each file's own
  hash) is identical; given one changed value or citation, then it differs. Test:
  `test_template_resolve.py::test_content_hash_stable`.
- AC12. Given a shipped folder and a user folder, when a name and version exist in both, then `TemplateAmbiguous`;
  given a template with `synthetic: true` and a repository not built with `allow_synthetic=True`, then
  `TemplateInvalid` (`synthetic_not_allowed`); given `meta.status: draft`, then `Template.is_draft` is true. Test:
  `tests/unit/test_template_repository.py::test_lookup_rules`.
- AC13. Given `check_template(path)`, then it returns a `TemplateReport` listing every error (not only the first) and
  every warning (paths that no known workflow declares), and raises nothing for a malformed user file. Test:
  `tests/unit/test_template_check.py::test_report_lists_all_errors`.

Building the basis
- AC14. Given a workflow's `FieldSpec`s, a template, engineer values and detected values, when `build_draft` runs, then
  each field takes the first of: engineer value, detected value, template value; a path with none is listed in
  `BasisDraft.pending` and is absent from `fields`; nothing is defaulted. Test:
  `tests/unit/test_basis_build.py::test_precedence_and_pending`.
- AC15. Given the built draft, then `source` is `template:<name>@<version>` of the template that defines the final
  value (the ancestor when inherited), `model:<RefString>`, or, for a value from the engineer's values file, no `source` yet (the draft row shows
  `origin: values-file:<name>`, which is not stored); `freeze` sets `engineer:<answer.by>@<answer.at>` from the confirming
  answer (AC22), never from the file's name or the build clock; `citation` is copied from the entry for `template:*` sources and null otherwise; `confirmed` is
  false for every field. Test: `test_basis_build.py::test_sources_and_citations`; the freeze-time stamp is tested under AC22.
- AC16. Given a detected value that differs from the template's value for the same path, then the draft carries the
  detected value with source `model:*` and a `detected_differs` warning that holds both values. Test:
  `test_basis_build.py::test_detected_differs_warning`.
- AC17. Given an engineer value for a path no `FieldSpec` declares, or one that violates its `FieldSpec` (kind, unit,
  choice, bounds), or a value file that sets `confirmed`, then `BasisInvalid` with reason `unknown_field`,
  `field_invalid` or `confirmed_not_allowed`. Test: `test_basis_build.py::test_value_file_rules`.
- AC18. Given a path in `ask_each_run`, then the draft takes no template value for it (AC10) and lists it as pending
  until an engineer value arrives. Given a required `FieldSpec` that neither the template nor `ask_each_run` covers,
  then it is still asked (pending). Test: `test_basis_build.py::test_asked_and_undeclared_fields`.
- AC19. Given the same inputs, then `BasisDraft.sha256` is identical across runs; given any change in template, values,
  field specs or pending list, then it differs. Test: `test_basis_build.py::test_draft_hash`.
- AC20. Given a previous run's basis for the same template, then nothing of its `confirmed` flags or timestamps carries
  into a new draft. Test: `test_basis_build.py::test_confirmation_never_carried`.

Declaration by the workflow
- AC21. Given a workflow that declares `basis_fields`, then `required_basis` equals the paths of its required
  `FieldSpec`s (otherwise `BasisInvalid`, reason `declaration_mismatch`), a `count` field is an integer with no unit,
  a `choice` field has at least two string choices, a `quantity` field has a canonical unit matching its path suffix.
  Test: `tests/unit/test_basis_fields.py::test_field_spec_rules`.

Confirmation, freeze and storage
- AC22. Given a `BasisSetupAnswer` whose `draft_sha256` differs from the draft, or that confirms a section with a
  pending required field, or that confirms no section, then `freeze` raises `BasisNotConfirmed` (reason
  `draft_changed`, `section_incomplete` or `nothing_confirmed`) and stores nothing. Given a valid answer, then each
  values-file field is stored with `source` `engineer:<answer.by>@<answer.at>`. Tests:
  `tests/contract/test_basis_freeze.py::test_refusals` and `::test_engineer_source_from_answer`.
- AC23. Given a draft with a required field still missing or a field in an unconfirmed section, when frozen, then
  `BasisIncomplete` lists the paths (the same list as `DesignBasis.missing`) and stores nothing. Test:
  `test_basis_freeze.py::test_incomplete_lists_paths`.
- AC24. Given a complete draft and an answer confirming every section that has fields, when frozen, then one
  `basis.design_basis/1` result is stored with `confirmed: true` on every field, `template` set to
  `{name, version, sha256}` (null when no template was chosen), and its reference is returned; the payload validates
  against the contract kind. Test: `test_basis_freeze.py::test_freeze_stores_result`.
- AC25. Given a frozen basis, then it is never rewritten: freezing identical content twice gives the same
  `payload_sha256`, changing the draft afterwards does not change the stored result, and `StoreBasisPort.load` of a
  result of another kind, of an unknown reference or of a payload whose hash does not match raises `BasisInvalid`
  (`not_a_basis`, `not_found`, `hash_mismatch`). Test: `test_basis_freeze.py::test_stored_basis_immutable`.

Interface to the approval page (spec 0006)
- AC26. Given a draft, when `build_setup_view` runs, then the view holds `setup_id`, `draft_sha256`, the workflow, the
  template identity and chain, banners (`draft_template`, `synthetic_template`), and one section per top-level key in a
  fixed order; every row has `path`, `label`, `value`, `unit`, `source`, `citation`, `state` (`provided`, `detected`,
  `missing`) and the FieldSpec's bounds; a section with a `missing` required row is `confirmable: false`. Test:
  `tests/unit/test_basis_setup.py::test_view_rows`.
- AC27. Given the answer model, then it holds only `setup_id`, `draft_sha256`, `confirmed_sections`, `by`, `at`, or a
  `rejected` reason; it has no member that carries a value, and extra members are refused. Test:
  `test_basis_setup.py::test_answer_cannot_carry_values`.

Integration
- AC28. Given a synthetic workflow that reads `ctx.basis.quantity`, `count` and `choice` and a basis frozen by AC24, when
  run in fake-host mode, then the values arrive typed, the run header holds the `basis_ref`, and a replay of the journal
  shows no divergence; given a draft frozen without confirmation (built by hand in the test), then `start` raises
  `RunRefused` (`BASIS_INCOMPLETE`) with no run folder. Test:
  `tests/workflow/test_basis_workflow.py::test_basis_reaches_ctx_and_replays`.

Shipped content
- AC29. Given the template folder shipped with the package, then it holds no entry with a `value` (structure and asks
  only), every shipped file loads, its resolved hash equals the pinned value in `tests/data/golden/shipped_templates.json` (the protected golden path), and no shipped file is
  `synthetic`. Test: `tests/golden/test_shipped_templates.py::test_shipped_templates_pinned`.
- AC30. Given any template, a draft built from it, a frozen basis and a load, then for random trees the round trip
  `entries -> fields -> payload -> load` keeps every path, value, unit, source and citation, and an inheritance chain
  always yields the union of the chain's paths. Test: `tests/property/test_template_basis_props.py`.

## 4. Design

### 4.1 Modules

| Module | Contents | Visibility |
|---|---|---|
| `eng_harness.templates` | `Template`, `Entry`, `Meta`, `AskItem`, `Bounds`, `TemplateRepository`, `load_template`, `resolve`, `check_template`, `TemplateReport`, `TemplateInvalid`, `TemplateAmbiguous` | public |
| `eng_harness.basis` | `FieldSpec`, `build_draft`, `BasisDraft`, `EngineerValues`, `DetectedValue`, `freeze`, `StoreBasisPort`, `BasisSetupPort`, `BasisSetupView`, `BasisSetupAnswer`, `build_setup_view`, `BasisInvalid`, `BasisNotConfirmed`, `BasisIncomplete` | public |
| `templates._model`, `_yaml`, `_resolve`, `_repository`, `_check`; `basis._fields`, `_build`, `_setup`, `_freeze`, `_port` | implementation | private (underscored, engine AC1) |

Import rules: `eng_harness.templates` and `eng_harness.basis` import `eng_contract` and each other in one direction only
(`basis` imports `templates`); neither imports the engine's internals (only `eng_harness.ports` and `eng_harness.ctx`
types). Both are pure: they read files, make no network call, start no process (engine invariants on block code do not
apply, but the engine's runtime guard is not needed because no block module imports these modules directly). Amendment
B-415 (draft; review fix): `eng_harness.block` exports `FieldSpec` by importing it from `basis._fields`, which
therefore keeps importing only the standard library, `eng_contract` and `pydantic` (no `eng_harness` module), so that
spec 0005 AC42 holds; engine §4.1.2 states why the block import rules and the runtime guard still hold.

### 4.2 Template schema (13 §2)

A template file is `<name>-<version>.template.yaml` with `schema: eng-template/1` and these top-level keys: `meta`,
`materials`, `sections`, `loads`, `combinations`, `limits`, `analysis`, `modeling`, `drawing`, `ask_each_run`. Every
section is optional and may be empty. Only these keys exist (AC3).

- `meta`: `name`, `version`, `description` (max 500), `author` (free text; no personal path), `code_pack`
  (`{name, edition}` or null; recorded, not checked until phase 2), `status` (`draft` or `approved`; default `draft`),
  `synthetic` (bool, default false), `extends` (`"<name>@<version>"` or null).
- A section is a tree of groups (mappings) whose leaves are **entries**. A mapping is an entry exactly when it has the
  key `citation` or the key `value` **[added; `value` amended by B-378]**, so an entry that lacks its citation is refused (AC2) instead of being read as a group; any other mapping is a group. Group and leaf keys follow
  the path-segment rule of the contract (Q1). The path of a leaf is the dotted key path from the section, for example
  `materials.concrete.<grade>.fc_MPa`; it is the key of the basis field.
- Entry: `value` (JSON: number, integer, string, bool, or a list or mapping of those for catalogs and combination sets;
  never null), `unit` (canonical unit symbol or null), `citation` (8 to 500 characters, non-blank: code clause,
  standard, or the owner's documented practice with its document reference, as `Cited.source` in contract §4.8),
  `bounds` (optional `{min, max}`, each a `Cited` so a bound has its own source; numeric values only). Extra keys are
  refused.
- `ask_each_run`: list of `AskItem` `{path, label (max 120), kind (quantity, count, choice, text), unit, choices,
  bounds}` with the same rules as `FieldSpec` (§4.5). The template can ask for a field; the workflow's own `FieldSpec`
  remains authoritative when both exist and they disagree on kind, unit or choices (`field_invalid`).
- The loader holds no table of engineering names, bounds or defaults. The only checks are structural: suffix and unit
  (contract §4.7.2), finiteness, the entry's own bounds, citation, and the rules above. Bounds exist only when a
  template or a `FieldSpec` states them with a source.

### 4.3 Loading, inheritance, identity

- `_yaml.load_strict(path)` reads YAML 1.2 in safe mode, refusing the cases of AC7, and returns plain JSON data.
- `resolve(template, repository) -> ResolvedTemplate` follows `extends` (exact version pin, one parent, depth at most
  8 **[added]**), merges per AC8, validates the merged result again (AC10), and computes
  `sha256 = payload_sha256({chain: [{name, version, file_sha256}...], resolved: <model>})`. The `file_sha256` of each
  link is the hash of its own validated model, not of its bytes, so formatting never changes identity (AC11).
- `TemplateRepository(shipped_dir, user_dir, allow_synthetic=False)` finds `name@version` and lists templates. Shipped
  templates are package data; the user folder comes from the settings file of spec 0006 (its key is open: spec 0006
  Q22, amendment B-510). Same name and version in both is
  an error, so a user file never silently shadows a shipped one.
- `meta.status: draft` templates are usable and are flagged on the page and in the run report (§4.6). A shipped template
  moves to `approved` only with the owner's approval (process/10 §4).

### 4.4 Building the basis (13 §3)

`build_draft(fields, template, engineer, detected, clock) -> BasisDraft`:

1. Take the `FieldSpec`s the workflow declares (§4.5); the basis holds exactly those paths (the values "the workflow
   will use") **[added]**; template values for other paths are ignored and listed as `unused` in the view.
2. For each path take, in order: the engineer value (`EngineerValues`: `name` and `values: {path: {value, unit}}`, read
   from the values file of the command line `--basis <file>`, 11 §3), then the detected value (`DetectedValue`: `path`,
   `value`, `unit`, `ref`), then the template's resolved entry.
3. Validate each value against its `FieldSpec` and, for template values, the entry (AC17).
4. Set `source` and `citation` (AC15; values-file values stay without `source` until freeze), `confirmed: false`, then compute `pending` (required paths without a value) and
   `sha256` (contract canonical JSON of `{template, fields, pending, warnings}`).

The engineer's values file is data, so an agent may write it, which is why its values carry no engineer source until a person confirms them and `freeze` stamps the confirming engineer (§4.6); protection comes from the confirmation step: values show
with their source on the page and become `confirmed` only through the page (ADR-0027 §2). The file cannot set
`confirmed` (AC17). Conversion between units is never done here: the caller converts detected values with
`eng_contract.units` before passing them, and a non-canonical unit is refused.

### 4.5 Fields declared by the workflow

```python
class FieldSpec(BaseModel, frozen=True, extra="forbid"):
    path: BasisPath  # contract field-path rule, e.g. "limits.drift_ratio"
    kind: Literal["quantity", "count", "choice", "text"]
    label: str  # shown on the page, max 120
    required: bool = True
    unit: str | None = None  # quantity: canonical unit of the path suffix; otherwise None
    choices: tuple[str, ...] | None = None  # choice: two or more
    min: Cited | None = None  # quantity or count; each bound has its own source
    max: Cited | None = None
```

A workflow module exposes `basis_fields: tuple[FieldSpec, ...]`; its `WorkflowDef.required_basis` must equal the
required paths (AC21; Q7 proposes making the engine derive it; engine text: engine §4.2, rule EC4 (amendment B-415, draft)). `ctx.basis.quantity` reads a `quantity` field,
`count` a `count` field (an integer, including the `attempts.<name>` fields of engine Q1), `choice` a `choice` field.

Fields the model edit cycle is expected to need (proposal for spec 0007, which owns the final list; **no values**):

| Path | Kind | Why |
|---|---|---|
| `limits.drift_ratio` | quantity (ratio) | summary of drifts against a limit (13 example, engine AC17) |
| `limits.ratio_limit_ratio` | quantity (ratio) | design-ratio threshold for the summary (contract §4.9 `ratio_limit`) |
| `modeling.merge_tolerance_mm` | quantity | joint merge after edits (13 §2 `modeling`) |
| `modeling.snap_tolerance_mm` | quantity | grid snapping of new objects (13 §2) |
| `modeling.section_rounding_increment_mm` | quantity | new section sizes (13 §2) |
| `attempts.<name>` | count | `ctx.attempts` limits (engine Q1) |

### 4.6 Confirmation and the approval page (spec 0006)

ADR-0027 makes the page read-only apart from approve, reject and sign, and warns against requests to edit values on it.
So values arrive in the values file (§4.4), and the page shows the basis and confirms it. This spec defines the
interface; spec 0006 implements the page and passes through the pause and resume (the setup runs before a run exists,
so it is not an engine `ApprovalPort` request).

```python
class BasisSetupPort(Protocol):
    def present(self, view: BasisSetupView) -> None: ...
    def answer(self, setup_id: str, *, wait: bool) -> BasisSetupAnswer | None: ...  # None: no answer yet
```

- `BasisSetupView` (frozen): `setup_id` (ULID), `draft_sha256`, `workflow`, `template` (name, version, sha256, chain,
  `status`) or null, `banners`, `sections` (each `name`, `confirmable`, `rows`), `warnings`, `unused`. A row is `path`,
  `label`, `value`, `unit`, `source`, `citation`, `state`, `min`, `max`. Detected values show as `detected`; they are
  confirmed like any other (13 §5). Banners: `draft_template`, `synthetic_template`.
- `BasisSetupAnswer` (frozen, `extra="forbid"`): `setup_id`, `draft_sha256`, and either `confirmed_sections` (names),
  `by` (engineer name), `at` (`Timestamp`), or `rejected` (reason, 1 to 500 characters). No member carries a value.
- A reject leaves no run and no stored basis; the engineer edits the values file and a new draft (a new hash) is shown.
- `freeze(draft, answer, store, clock) -> FrozenBasis` (`ref`, `result_id`, `payload_sha256`) checks the answer against
  the draft (AC22), sets `confirmed: true` on the fields of the confirmed sections and `source` `engineer:<answer.by>@<answer.at>` on those that came from the values file, requires
  `DesignBasis.missing(required)` to be empty and every present field to be confirmed (AC23), writes the result through
  the contract `ResultStore` and returns the reference for `RunRequest.basis_ref`. Confirmation is per run: it is never
  read from earlier runs (AC20).
- Mid-run questions (`ctx.ask`, engine AC61) are separate: they store `basis.engineer_input/1` and never alter the
  frozen basis.

### 4.7 Storage and access

The frozen basis is one `basis.design_basis/1` result (contract §4.10). `StoreBasisPort.load(basis_ref)` implements the
engine `BasisPort`: it resolves the reference through the `ResultStore`, checks the kind and the payload hash, and
returns `LoadedBasis`. The engine puts `basis_ref` in the run header and builds `ctx.basis` from it (engine §4.8,
AC17); blocks read by reference (`res_<id>#/fields/<path>/value`), so a step records the basis value it used. The basis
is frozen for the run: a change means a new draft, a new confirmation, a new result and a new run (13 §4 step 6).

### 4.8 What v1 ships

- One template, `blank-0.1.0.template.yaml` (`status: draft`): `meta` only, every other section empty, and
  `ask_each_run` listing the paths of the edit cycle's `FieldSpec`s (§4.5, final list from spec 0007). It contains no
  value, so there is nothing to cite. Every engineering value is asked at run start.
- No shipped values are proposed in this spec. When the owner wants shipped templates, each value arrives in its own
  pull request with an exact citation, `meta.status: draft`, the golden diff report and verification record of
  process/10 §5, and an owner queue entry (Q8).
- Test templates are fixtures under `tests/fixtures/templates/`, `synthetic: true`, names starting `synthetic-`, with
  placeholder values that are plainly not engineering values and citations that say so. The loader refuses them unless
  `allow_synthetic=True`, which only tests set (AC12).

## 5. Inputs and outputs

| Name | Type | Unit | Bounds | Ref-capable | Source |
|---|---|---|---|---|---|
| Template file | YAML, `eng-template/1` | canonical per suffix | at most 1 MiB, depth 8 | no | shipped folder or user folder |
| Values file (`--basis`) | YAML or JSON `{engineer, values}` | canonical per suffix | by `FieldSpec` | no | engineer or a coding agent |
| `FieldSpec` list | `tuple[FieldSpec, ...]` | canonical | see §4.5 | no | workflow module |
| `DetectedValue` | `path, value, unit, ref` | canonical | by `FieldSpec` | `ref` | the caller (spec 0006, 0007) |
| `BasisDraft` | model | | | no | `build_draft` |
| `basis.design_basis/1` | result | per field | contract §4.10 | yes | `freeze` |

## 6. Errors

All are subclasses of the contract `ContractError` with code `INVALID_ARGUMENT` and a `reason` member (Q6), except
`BasisIncomplete`, whose name matches the engine code `BASIS_INCOMPLETE`.

| Condition | Error | Reasons / fields |
|---|---|---|
| Template file invalid | `TemplateInvalid` | `yaml_invalid`, `unknown_key`, `meta_invalid`, `citation_missing`, `unit_mismatch`, `value_invalid`, `out_of_bounds`, `bounds_invalid`, `ask_has_value`, `extends_invalid`, `synthetic_not_allowed`; `file`, `path` |
| Template lookup | `TemplateAmbiguous`, `TemplateInvalid` (`not_found`) | `name`, `version` |
| Values or declarations invalid | `BasisInvalid` | `unknown_field`, `field_invalid`, `confirmed_not_allowed`, `declaration_mismatch`, `not_a_basis`, `not_found`, `hash_mismatch`; `path` |
| Answer does not match the draft | `BasisNotConfirmed` | `draft_changed`, `section_incomplete`, `nothing_confirmed`, `rejected` |
| Required field missing or unconfirmed at freeze | `BasisIncomplete` | `paths` (same as `DesignBasis.missing`) |

Messages never contain file contents beyond the offending path and a reason key.

## 7. Non-goals

- Consistency with a code pack (combinations valid for the code, materials within ranges): phase 2 (13 §5).
- A template editor, a graphical setup screen, typing values on the page (Q3), choosing the last template per project
  (spec 0006), merging or diffing templates, version ranges in `extends`.
- Any expression, formula, script or conditional in a template; combination generators (phase 2).
- Shipping engineering values, bounds or defaults; converting units inside a template or draft.
- Reading values from a host model (the caller passes `DetectedValue`s); the DXF header detection itself.
- The edit cycle's final field list (spec 0007) and the page itself (spec 0006).

## 8. Risks

| Risk | Class | Mitigation |
|---|---|---|
| A wrong value in a shipped template silently becomes a project basis | R1 | v1 ships no value; later values only with exact citation, `draft`, owner approval, golden diff (AC29) |
| An agent writes values and confirms them itself | R1 | confirmation only on the page; the answer has no value member and no command-line path; sources shown on the page (AC17, AC27) |
| Confirmation of a stale view | R1 | the answer is bound to `draft_sha256` (AC22) |
| YAML 1.1 surprises or aliases change a value silently | R1 | strict YAML 1.2 loader and tests (AC7) |
| Inheritance hides an override | R2 | the source names the defining template; the page shows the chain; the hash covers the chain (AC11, AC15) |
| Unit mix-ups | R1 | canonical units only, suffix check, no conversion (AC4) |
| Scope growth of the page | R3 | answer model without values (AC27); ADR-0027 pre-mortem |

## 9. Test strategy

| Criterion | Test layer | Test name (planned) |
|---|---|---|
| AC1 to AC6 | unit | `tests/unit/test_template_model.py::*` (names in §3) |
| AC7 | unit | `tests/unit/test_template_yaml.py::test_strict_loader` |
| AC8 to AC11 | unit | `tests/unit/test_template_resolve.py::*` |
| AC12 | unit | `tests/unit/test_template_repository.py::test_lookup_rules` |
| AC13 | unit | `tests/unit/test_template_check.py::test_report_lists_all_errors` |
| AC14 to AC20 | unit | `tests/unit/test_basis_build.py::*` |
| AC21 | unit | `tests/unit/test_basis_fields.py::test_field_spec_rules` |
| AC22 to AC25 | contract (against the contract `ResultStore` and kind) | `tests/contract/test_basis_freeze.py::*` |
| AC26, AC27 | unit | `tests/unit/test_basis_setup.py::*` |
| AC28 | fake-host workflow and replay | `tests/workflow/test_basis_workflow.py::test_basis_reaches_ctx_and_replays` |
| AC29 | golden | `tests/golden/test_shipped_templates.py::test_shipped_templates_pinned` |
| AC30 | property (Hypothesis) | `tests/property/test_template_basis_props.py::*` |

Fixtures are synthetic (`tests/fixtures/templates/`). Coverage thresholds per process/05 §2 (`eng-harness`: line 85,
branch 75); the freeze and merge code is also under mutation testing. A change to the golden hash follows process/10 §5.

## 10. Version impact

New public modules in `eng-harness`: minor. No contract change in this spec. Q1 is decided (OQ-Q44) and lands in
`eng-contract` 0.1.0 through contract plan 0001 T19 (B-464); Q4 still asks for a contract change (minor, contract 0.2)
that is not assumed.

## 11. Open questions

| Question | Owner | Answer |
|---|---|---|
| Q1. Conflict: 13 §2 and the contract unit suffixes use mixed case (`fc_MPa`, `fy_MPa`, `_kN`), but the contract's `basis.design_basis/1` path rule `^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$` allowed lowercase only, so `materials.concrete.c1.fc_MPa` could not be a basis path. | Owner (contract) | Decided (owner, OQ-Q44; amendment B-463): segments stay lowercase and the last one may end with a contract §4.7.2 suffix (contract spec §4.10.2, AC48a), built by eng-contract plan 0001 T19 (B-464). This plan's T1, T4, T5 and T8 are merged with the earlier answer, the contract FieldPath name rule (`[A-Za-z_][A-Za-z0-9_]*` per segment), which is wider than the decided rule; storing a suffixed field needs T19, a key that passes the harness rule but not contract §4.10.2 is refused only at freeze (T8), and plan T11 aligns the harness rule (amendment B-484) |
| Q2. A YAML parser is a new runtime dependency (A10); the engine plan allows only Pydantic | Owner | Approve an ADR for `ruamel.yaml` (YAML 1.2, safe mode); fall back to JSON templates if refused |
| Q3. 13 §4 has the engineer fill values on the setup screen; ADR-0027 keeps the page read-only | Owner | Keep the page read-only: values come from the values file, the page confirms per section (this spec); revisit with the full UI ADR |
| Q4. `basis.design_basis/1` has no `draft` flag, so a frozen basis cannot show that its template was draft | Owner (contract) | Add `draft: bool` in contract 0.2 (as `verdicts.set/1` has); until then only the page banner and the run report show it |
| Q5. Who confirmed, and when, is not stored in the payload (`confirmed` is a bool) | Owner | Record `by` and `at` in the setup answer kept by spec 0006's page log; add `confirmed_by` and `confirmed_at` to the kind in contract 0.2 if the owner wants it in the result |
| Q6. Template and basis errors have no contract code | Owner | `INVALID_ARGUMENT` plus a `reason` key now (as engine Q7); a `HarnessCode` family only if the engine needs to branch on them |
| Q7. `WorkflowDef` carries `required_basis` (paths) only | Owner (engine) | Add `basis_fields: tuple[FieldSpec, ...]` to `WorkflowDef` in spec 0007's plan and derive `required_basis`; this spec's check (AC21) then becomes trivial. Engine text written by amendment B-415 (engine §4.2, rule EC4, Q30; built by plan 0007 T6; draft until the owner approves) |
| Q8. Whether v1 should ship any engineering values | Owner | No. Ship `blank` only; the owner supplies values with citations by pull request when wanted |
| Q9. Engineer name for `engineer:<name>@<timestamp>` | Owner | The values file's `engineer` member is only the name the page proposes; the recorded name is the confirming answer's `by` (spec 0006's settings may default it); never from the operating system account |
