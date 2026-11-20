# ADR-0001: Runtime dependencies of eng-dev-gate

Status: Proposed · Date: 2026-11-03 · Deciders: owner

## Context
The gate needs YAML loading, boundary models and the tools it pins (process/04 section 7 requires an ADR for each
runtime dependency; spec section 11 Q1). Licenses below are as published by each project and are to be verified by the
gate's license check (task T19); sizes and maintenance health are to be confirmed by the owner at review.

## Decision
Add these runtime dependencies:

| Dependency | Purpose | License |
|---|---|---|
| PyYAML | Safe YAML loading of front matter, `.gate/*.yml`, workflows | MIT |
| Pydantic v2 | Boundary models for configuration, front matter, events, results (process/04 section 5) | MIT |
| ruff | Format and lint steps, pinned so packages cannot choose a weaker version | MIT |
| mypy | Strict type step, pinned for the same reason | MIT |
| pytest | Test runner and plugin host | MIT |
| coverage | Line and branch coverage | Apache-2.0 |

Development only: Hypothesis (MPL-2.0), pytest-cov (MIT), types-PyYAML (Apache-2.0). Build backend: the uv build
backend. Exact versions are fixed in `uv.lock`.

## Consequences
The gate controls the tool versions that packages are judged by. Every upgrade is a separate pull request with tests.
Mutation tooling is decided later in ADR-0002 (task T20).

## Alternatives considered
- **ruamel.yaml, tomllib-only configuration**: PyYAML safe loading is enough and smaller; TOML cannot carry the front matter.
- **dataclasses with hand validation**: Pydantic is the process standard for boundaries.
- **Tools provided by each package**: packages could pick weaker versions.

## Pre-mortem
A tool release changes its output format or rules and breaks every package at once. Early warning: the gate's own CI
fails after a lock upgrade; the pinned lock limits the blast radius.
