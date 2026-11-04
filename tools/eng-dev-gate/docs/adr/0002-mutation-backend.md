# ADR-0002: Mutation backend of eng-dev-gate

Status: Proposed · Date: 2026-11-04 · Deciders: owner

## Context
The `mutation` step (spec 4.12, AC53; plan task T20) needs a mutation testing tool. Spec section 11 Q4 left the choice
between mutmut and cosmic-ray open, with a check of Windows support. Process/04 section 7 allows only MIT, BSD,
Apache-2.0, ISC, PSF and MPL-2.0 licenses, for the whole dependency closure.

Facts checked on 2026-11-04 on Linux with Python 3.14 (versions as resolved by uv at that date):

| | mutmut 3.8.1 | cosmic-ray 8.7.0 |
|---|---|---|
| License | BSD-3-Clause | MIT |
| Closure licenses | MIT, BSD, PSF (click, libcst, setproctitle, textual, rich, coverage, pytest) | includes `yattag`, classified LGPL: not on the allowed list |
| Runs on Python 3.14 | yes (toy package mutated and scored) | yes |
| Windows | no native support: `mutmut` exits on Windows and asks for WSL (upstream issue 397); mutants run in forked processes | OS independent by its classifiers; not run on Windows here |
| Result access | `mutmut results --all true`, one `name: status` line per mutant | SQLite session, `cr-rate` |

## Decision
Use **mutmut**, as a runtime dependency (`mutmut>=3.8.1`, pinned by `uv.lock`). The gate writes the mutmut
configuration (`setup.cfg`) into a temporary copy of the package, listing only the changed R1 and R2 modules, and
refuses a `[tool.mutmut]` table in the package, so a package cannot choose what is mutated. The score is (killed +
timeout) over all mutants. The copy holds the whole source tree (the mutants are complete packages, so they shadow the
editable installation of the member), the pytest `addopts` of the package are switched off for the mutated runs, and in
a pull-request run mutmut runs in the environment uv builds from the judged tree (`uv run --project <tree> --locked`),
so mutmut must be in that tree's lock file (it is, through this package) and the member's tests find their dependencies.

On Windows the step reports MU002 as a notice locally and raises an environment fault (exit 3) when `CI` is set, so
mutation runs on Linux CI only (spec 4.12, Q4 fallback). Windows support was not run on Windows here: the statement
rests on mutmut's own refusal message and needs the Windows CI job to confirm.

## Consequences
Adds mutmut and its closure (libcst, textual, rich, setproctitle and others) to the lock. The license check (T19) must
accept the closure; the metadata of some members carries only a trove classifier. Local mutation runs are slow on large
modules; only changed modules are mutated.

## Alternatives considered
- **cosmic-ray**: works on Windows in principle, but its closure contains an LGPL package (`yattag`), which process/04
  section 7 does not allow; an exception would need its own ADR.
- **A gate-owned mutation engine**: more code to maintain and review than a pinned tool; rejected.

## Pre-mortem
A mutmut release changes its results listing or configuration keys and the score becomes wrong or zero. Early warning:
the integration test (real mutmut on a toy package, one strong and one weak test suite) fails after a lock upgrade.
