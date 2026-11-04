# eng-dev-gate

The gate of the Eng-Agent platform: one command, `eng-gate`, that enforces the process rules locally and in CI.

- Spec: [docs/specs/0001-eng-dev-gate-0.1.md](docs/specs/0001-eng-dev-gate-0.1.md)
- Plan: [docs/plans/0001-eng-dev-gate-0.1.md](docs/plans/0001-eng-dev-gate-0.1.md)
- Runtime dependencies: [docs/adr/0001-runtime-dependencies.md](docs/adr/0001-runtime-dependencies.md) (Proposed)
- Live steps: [docs/local-testing.md](docs/local-testing.md)
- Changes: [CHANGELOG.md](CHANGELOG.md)

## Exit codes

| Code | Meaning |
|---|---|
| 0 | pass, or awaiting owner (bootstrap mode; the finding is printed as a notice) |
| 1 | a rule failed |
| 2 | usage or configuration error |
| 3 | environment or tool error |

Every finding carries a stable diagnostic code (for example `GC001`, `FB005`, `IM003`); the codes, the exit codes, the
`.gate/` file formats and the `[tool.eng-gate]` keys are the public interface. Global options: `--root`, `--gate-root`
(policy and gate code from a checkout of the base commit) and `--format text|json`.

## Setup

```
uv sync
uv run eng-gate --version
uv run pytest
```

## Commands

Run the whole local gate (all steps, one member or all members):

```
uv run eng-gate check
uv run eng-gate check --package eng-dev-gate --skip mutation
```

Pull-request rules (CI passes `--event`; locally use the explicit options):

```
uv run eng-gate gate-check --event "$GITHUB_EVENT_PATH"
uv run eng-gate risk-floor --base origin/build/v1 --head HEAD --body-file body.md
uv run eng-gate test-first --base origin/build/v1 --head HEAD --title "feat(x): y"
```

Single steps of `check`:

```
uv run eng-gate forbidden --all
uv run eng-gate imports --package eng-dev-gate
uv run eng-gate licenses --all
uv run eng-gate ratchet
uv run eng-gate ratchet --update
uv run eng-gate secrets --range origin/build/v1..HEAD
uv run eng-gate workflows
uv run eng-gate mutation --package eng-dev-gate --base origin/build/v1
uv run eng-gate windows-tests
```

Other commands:

```
uv run eng-gate agents drift
uv run eng-gate agents render
uv run eng-gate review --check-prompts
uv run eng-gate packages --names
```

## Notes

- `agents render` writes `AGENTS.md`; `agents drift` fails when a committed file differs from its rendering.
- `ratchet --update` lowers recorded suppression counts and never raises one.
- Steps that need a real CI run are listed in [docs/local-testing.md](docs/local-testing.md).
