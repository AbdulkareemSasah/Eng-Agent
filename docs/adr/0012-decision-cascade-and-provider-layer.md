# ADR-0012: Decision cascade and provider layer

Status: Proposed; phasing amended by ADR-0025 (no decision-model tier in phase 1) · Date: 2026-10-24

## Context

Language models are slow for in-workflow decisions. The owner wants to use typed decision models such as TypeSafe Jev
(choice, score and yes/no answers with confidence, sub-second, cheap) as much as possible, with providers that users can
swap, starting with OpenRouter.

## Decision

- Every decision point resolves through: rules, then a decision model, then a language model (only if the policy
  allows), then the engineer.
- Decisions return typed options only, never numbers.
- Two provider interfaces: `DecisionProvider` (choose, score, yes/no, batch) and `LLMProvider` (structured output).
  Providers are configured by endpoint, model id and key; OpenRouter is the default; local and private endpoints are
  supported.
- Tier 2 and 3 run in shadow mode per decision point until the point passes its evaluation, unless the owner explicitly
  enables a low-risk point earlier.
- Every decision is journaled with its tier, model version and confidence.
- Phasing: phase 1 has rules, the engineer, and the decision model for one decision point (DXF layer classification)
  in shadow mode, so evaluation data accumulates from the first runs. The language-model tier arrives in phase 2.

## Consequences

- Most decisions cost nothing (rules); the rest are fast and recorded.
- Early runs ask the engineer more often (shadow mode); speed improves as points pass evaluations.
- The Jev adapter depends on spike S-07 (API shape, batching, data terms).

## Alternatives considered

- **Language model for every decision**: slow and costly. Rejected.
- **Decision model without engineer fallback**: unsafe for low-confidence cases. Rejected.
