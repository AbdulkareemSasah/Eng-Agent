# ADR-0004: ruamel.yaml as a runtime dependency of eng-harness (strict YAML 1.2 template and values files)

Status: Proposed · Date: 2026-11-04 · Deciders: owner

## Context
[Spec 0004](../specs/0004-templates-and-basis.md) §4.2 and §4.3 fix the template format as YAML (13 §2, ADR-0017) and
require a loader that reads YAML 1.2 and refuses duplicate keys, aliases, anchors, tags, non-string keys, oversize
files and deep nesting (AC7), so that a parser quirk cannot change an engineering value silently (risk R1 in the spec's
risk table). The same loader serves the values file of the command line (spec 0004 §4.4) and plan 0003 T3. The standard
library has no YAML parser. Process/04 §7 requires an ADR for a runtime dependency (spec 0004 Q2).

Measured on 2026-11-04 in the workspace environment (CPython 3.14.6, Linux): `ruamel.yaml` 0.19.1 resolves with no
runtime dependency of its own (its `ruamel.yaml.clib*`, `jinja2`, `ryd` and `mercurial` requirements are optional
extras that we do not select); it is pure Python, so it has one wheel for every platform. Installed size about 1.4 MiB
(`du` of the package folder, bytecode included). License MIT as published in its metadata (enforced for the whole lock
by the gate's license check).

Behavior measured with the safe loader in its default configuration: it refuses duplicate keys and unknown tags, but it
resolves aliases and merge keys silently, reads `2026-01-31` as a date, and reads `1_000` and `0b11` as integers, which
YAML 1.2 core does not. The loader therefore installs its own resolver with the YAML 1.2 core schema only (null, bool,
int, float), checks the parse events for anchors, aliases, tags, a second document and depth before any data is built,
and checks the built data for string keys and finite numbers (`tests/unit/test_template_yaml.py`). The resolver is a
subclass of `ruamel.yaml.resolver.VersionedResolver` that overrides its `versioned_resolver` and `processing_version`
properties; those are internal API of the library, which is why the dependency is bounded to the 0.19 series and why the
strict-loader test must fail at an upgrade that changes them.

Maintenance health (PyPI release history, read 2026-11-04): 273 releases since 2014, the latest 0.19.1 on 2026-01-02,
before it 0.19.0 on 2025-12-31 and 0.18.17 on 2025-12-17; a long-lived library with several releases a year. Whether
this health is acceptable is for the owner to confirm at review.

## Decision
Add `ruamel-yaml>=0.19,<0.20` (resolved to 0.19.1 in `uv.lock`) to `packages/eng-harness`, imported only by
`eng_harness/templates/_yaml.py`. No other module parses YAML; callers receive plain JSON data from `load_strict` and
`loads_strict`. The C extension packages are not added.

| Package (resolved version) | Role | License | Installed size |
|---|---|---|---|
| `ruamel.yaml` 0.19.1 | YAML 1.2 parser (pure Python mode) | MIT | about 1.4 MiB |

## Consequences
- Easier: templates and values files are YAML as the design says; the strictness rules live in one small module with one
  test file.
- Harder: the loader uses a resolver subclass that touches library internals, so an upgrade beyond 0.19 needs a
  deliberate pull request that re-runs the loader tests.
- Pure Python parsing is slower than a C parser; the 1 MiB limit bounds it, and a template is loaded once per run.

## Alternatives considered
- **PyYAML `safe_load`**: YAML 1.1 reads `no`, `on` and `1:30` as a boolean or number, and allows aliases and duplicate
  keys silently (spec 0004 §3). It is in the lock only as a development tool dependency, not a runtime one.
- **`tomllib` (standard library)**: no new dependency, but the design fixes YAML and engineers edit these files.
- **JSON templates**: the fallback of spec Q2 if this ADR is refused; no comments, harder for engineers to edit (plan
  0004 §3 would change T2 by an amendment).
- **A hand-written YAML subset parser**: a parser is a source of the very errors AC7 exists to prevent.

## Pre-mortem
A `ruamel.yaml` release renames the resolver properties we override and the loader silently reads `yes` as a boolean
again. Early warning: `test_strict_loader` asserts the 1.2 reading of `no`, `on`, `1:30`, `010` and `2026-01-31`, and
fails at the upgrade pull request before it merges.
