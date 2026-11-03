# ADR-0031: `model_locked` after analysis is a precondition, not `HOST_LOCKED`; an approved unlock step

Status: Proposed · Date: 2026-11-03 · Deciders: owner (pending); proposed by the agent identity with the eng-harness
server and adapter spec

Amends [04](../architecture/04-tool-contract.md) §8.1 and [11](../architecture/11-harness-engine.md) §7 and §9 (both
Proposed). Closes spike gap S12-G3 (owner queue OQ-A3).

## Context

- ETABS locks a model after an analysis. The Sasaah CSI server then refuses every Write, Destructive and Code tool
  except `csi_unlock_model`, `csi_save_model`, `csi_run_analysis` and `csi_design_run` with the code `model_locked`
  ([S-12 report](../../../spikes/S-12-sasaah-tool-inventory/REPORT.md) §7, Sasaah `CsiToolService.cs:947-968`).
- In the model edit cycle ([ADR-0025](0025-first-workflow-edit-cycle.md), [18](../architecture/18-first-slice-dxf-to-etabs.md)
  §4) the edits of cycle N+1 follow the analysis of cycle N, so they meet `model_locked` in every cycle after the
  first.
- In 04 §8.1, `HOST_LOCKED` means "another live server process holds this host instance". 11 §9 maps `model_locked`
  to `HOST_LOCKED`, "shown to the engineer, never retried", which would stop every second cycle and gives one code two
  meanings: the harness's own host-instance lock (11 §6 item 10) also reports `HOST_LOCKED`.
- `csi_unlock_model` (`confirm` required) "discards the locked analysis state" (Sasaah `CsiModel.cs:1740-1744`). After
  edits the analysis results are stale anyway, but discarding them is still a change the engineer should see.
- The session evidence (Sasaah `agent-sessions/_baseline/REPORT.md` §6) records an unlock sent to the engineer's own
  instance by mistake, deleting its results: an unlock must name its target instance explicitly.
- The Sasaah server also refuses `csi_open_model`, `csi_new_model`, `csi_exit` (and deletes, unless started with
  `--allow-attached-writes`) on an instance it attached to rather than launched (`not_launched_by_server`). 04 §8.1 has
  no precondition for it either (S-12 §6).

## Decision

1. **Two new precondition values** in 04 §8.1 and `eng-contract` (`Precondition`, an additive minor version):
   `model_unlocked` (the model is locked by the host after an analysis; an unlock is needed before the write) and
   `server_owned_instance` (the operation needs a host instance the server itself started).
2. **Mapping.** The CSI adapter maps the Sasaah code `model_locked` to `PRECONDITION_FAILED` with `precondition:
   model_unlocked`, and `not_launched_by_server` to `PRECONDITION_FAILED` with `precondition: server_owned_instance`.
   Both are not retryable (the 04 retry rule for `PRECONDITION_FAILED`), and both are certain "not applied" outcomes:
   the server refuses before any host call.
3. **`HOST_LOCKED` keeps its 04 meaning only**: another live driver holds the host instance. In the harness it comes
   from its own machine-level host-instance lock (11 §6 item 10). It is shown to the engineer and never retried.
4. **The unlock step.** `csi_unlock_model` is on the CSI adapter's allowlist with the action `unlock`. It runs only as
   a journaled write step under an approval whose preview names it (in the edit cycle, an item of the change-set
   approval: "unlock the model; the analysis results of revision N are discarded"), or, without one, behind an
   approval the engine inserts in every permission mode: the action `unlock` joins the "always ask" list of 11 §7.
   The adapter always passes the explicit target (`product`, `pid`) of the model's bound instance. Before the first
   write of a change set, the adapter's model state reports `locked` (from `csi_model_info`), so a workflow can plan
   the unlock instead of meeting the refusal.
5. **Until this ADR is accepted** and `eng-contract` has the two values, the adapter keeps 11 §9 as written:
   `model_locked` maps to `HOST_LOCKED` and the unlock step is not offered; `not_launched_by_server` maps to
   `CONFLICT` ("the operation conflicts with model state", 04 §8.1). The switch is one task of the eng-harness server
   and adapter plan, blocked on this ADR.

## Consequences

- When accepted: 04 §8.1 lists `model_unlocked` and `server_owned_instance`; 11 §9 replaces "`HOST_LOCKED`
  (`model_locked` from the Sasaah CSI server) is shown to the engineer, never retried" with a reference to this ADR;
  11 §7 adds the action `unlock` to "always ask"; `eng-contract` gains the two values (minor version, its JSON
  Schema snapshot regenerated); the engine spec (eng-harness spec 0001 §4.7) adds `unlock` to its always-ask list.
- The edit cycle can run more than one cycle. Until acceptance it stops at the first edit after an analysis with
  `HOST_LOCKED`, which is safe but makes the second cycle a manual unlock by the engineer.
- A workflow that unlocks must re-run the analysis before it reads results; the stale results are not readable by
  mistake because `check_model` and the engine's staleness rule (11 §6 item 3) see the new revision.

## Alternatives considered

- **Keep `model_locked` as `HOST_LOCKED` (11 §9 as written)**: every second cycle stops, and one code means two
  different things. Rejected.
- **Map to `CONFLICT`**: needs no contract change, but a block cannot tell a locked model from a name collision, so it
  cannot route to the unlock step. Kept only as the interim mapping of `not_launched_by_server`.
- **The adapter unlocks silently before a write**: a hidden write that discards results, outside the journal's
  approval. Rejected (P9, P11).
- **Unlock automatically after every analysis**: the engineer may want to inspect results in the host first, and the
  unlock would hide a forgotten re-analysis. Rejected.

## Pre-mortem

If this is wrong a year from now, the likely cause is a Sasaah build in which `model_locked` is also raised for a
reason other than the post-analysis lock (for example a model opened read-only), so an approved unlock does not help
and the engineer is asked to approve a useless step. Early warning: an unlock step followed by `model_locked` again in
the same run.
