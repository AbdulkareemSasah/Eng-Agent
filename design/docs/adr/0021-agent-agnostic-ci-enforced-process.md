# ADR-0021: A development process that is tool-agnostic and enforced by machines

Status: Proposed; amended by ADR-0026 (project lane) · Date: 2026-10-24

## Context

Most code will be written by AI coding agents. Earlier, agents wrote random code and took hours when rules were only
suggestions. The process must hold no matter which agent, editor or person does the work, and it must scale as if many
developers contributed. An adversarial review of the first draft showed that rules an agent can satisfy by itself (setting
labels, posting "approved" comments, reviewing its own work in a second session, writing tests that match its output,
editing the local gate) are not rules.

## Decision

- **Rules live in one place and are rendered.** The process lives in this hub's `process/`. Each package's `AGENTS.md`
  (the cross-tool convention for agent instructions) is rendered from the hub's template; a CI job fails on drift.
  Tool-specific instruction files only point to `AGENTS.md`.
- **Gates are records CI can verify**: specs and plans merged to `main` with `status: approved` through their own pull
  requests, approved by the identity their risk requires; implementation pull requests name their plan task; CI
  checks file scope, diff budget, risk floor by path, and that tests from the first `test:` commit fail on the base and
  pass at the head. Labels are informational.
- **Separate identities**: the owner's account (admin, never in agent environments), an agent identity (no admin, no
  bypass), and a reviewer identity used only by CI.
- **Independent review means CI-started review**: pinned reviewer prompts run by CI on the diff, issue, spec and plan,
  with a different model family for R1 and R2 (checked against `Assisted-by` commit trailers). Author-started reviews
  are pre-checks.
- **Protected oracles**: tests' reference data (golden data, acceptance records written by scripts, recordings,
  evaluation sets) and every configuration that can weaken checks are owner-reviewed paths; a suppression ratchet only
  goes down.
- **One shared gate**: `eng-dev-gate` holds the local gate command, the CI checks, reusable workflows, reviewer prompts
  and the `AGENTS.md` renderer, pinned by version, so no package can quietly weaken enforcement.
- **Owner load is bounded**: the owner approves engineering content, contracts, protected paths and releases; CI and
  CI reviewers handle the rest; a daily digest lists every pending owner decision; the owner audits delegated merges by
  sampling and seeded-defect pull requests.
- Workflow accelerators (ECC, gstack and other skill packs) are mapped per stage in
  [process/09-tooling-map](../../process/09-tooling-map.md), with restrictions where a tool conflicts with a rule. The
  written checklist of each stage is the norm.

## Consequences

- An agent that does not know the accelerators still produces conforming work, because CI defines done.
- Setting up identities, a paid GitHub plan for private branch protection, and `eng-dev-gate` are phase 0 work.
- Some intent remains trust-based (meaningful assertions, honest status reports, stop-and-ask); it is reduced by
  sampling and seeded-defect audits.

## Alternatives considered

- **Rules in prose only**: proven not to hold. Rejected.
- **A process tied to one agent tool's hooks**: breaks when the tool changes. Hooks are allowed as local accelerators,
  never as the only enforcement.
- **Owner approval on every gate**: safe but turns the owner into the bottleneck (risk R5). Rejected.

## Pre-mortem

If agents still bypass the process, the likely cause is a gap between what `gate-check` verifies and what the rules
say. Early warning: seeded-defect audits that pass undetected, or merged pull requests the owner's sampling flags.
