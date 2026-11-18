# B-138 review (S.T19a, plan 0002 T19a)

Earlier lead rounds (preliminary, adapter checkpoint 668c383, pause checkpoint 0a40760) are recorded in
`docs/build/resume/2026-11-18/b138-review.md` on the branch. This file holds the lane review rounds.

## Round 1 (5991420)

Reviewer: an independent subagent of the lead (did not write the change). Reviewed the full diff
`git diff 51d9573 5991420` (merge base with origin/build/v1; 28 files, +1724/-42) against plan 0002 T19a (front matter,
prose, amendments B-413 to B-563), engine spec 0001 4.4.2, 4.5.4, 4.7, 4.8 and section 10 (B-562), and spec 0002
4.1, 4.5.9, AC36 and AC52; the focus of this round was the session-4 delta (c84a01c, 9837918, da18e9f, merge 5991420)
on top of the pause checkpoint the lead already reviewed.

What was checked:
- Scope: every changed file is in T19a's `files` (16 source and document files, 12 test files; `pyproject.toml`
  already lists `eng_harness.adapters`). No `ops/`, BUILD-STATUS or HANDOFF edit. Counted lines 478 against the
  estimate 380 (information only, owner decision 2026-11-17).
- Test-first: first commit eeae76fe is `test:`; `uv run -q eng-gate test-first --base 51d9573 --head HEAD --title ...`
  rerun by the reviewer: `test-first: pass`. The B-562 regressions are in the implementation commits as the plan says.
  da18e9f changes the input form of `test_units_trap` (thickness as a `Ref` instead of a raw `$ref` dict, which
  invariant 2 refuses before the port call); its expectation (`PRECONDITION_FAILED`, `units_verified`, before
  reconciliation) is unchanged, so no expectation was weakened.
- B-562 port and journal: `ToolInfo.opens_model_without_writing` false by default; `CsiToolInfo` true only for
  `csi_open_model` without a `path` key (false for `path`, `path: null`, `csi_open_revision`, every other tool).
  `StepStarted.opens_model_without_writing` is `StrictBool | None`, true accepted only on a `tool`/`write`/`open` step,
  omitted from the canonical payload when `None` (legacy payloads and hashes unchanged, journal version 1).
- Engine: the explicit true is recorded on each live attempt before the call; only that step's dirty mark is skipped
  (live success, immediate `applied`, replay from the recorded attempt), earlier dirty state kept; write effect still
  drives leases, approvals, units, sibling board, reconciliation and retries. Immediate `applied` now goes through the
  same post-open binding, units and EC1 copy as a success; a replayed open binds from the journaled host key and action
  before a still-live copy and is not rebound when its recorded copy replays (`Modes.handed`). Resume: comparison
  result and 8a save candidate come from `Fold.content`; `lacking` (reopened) uses the content view; the original's
  state read is skipped only by `handed_off`, which checks every clause of engine 4.5.4 (marked open resolved
  completed/applied, no other content or unresolved write, nothing cut, copy attempt completed after the open's
  outcome, distinct copy key, `model_saved` role `working_copy` on that path inside the attempt, no later binding).
- AC36: the six-write matrix (open, two setters, save, analysis, design) kills a spawned engine process after each
  write and resumes with new ports: one logical call and one attempt per cut, setters `applied` by the adapter with
  evidence, the others by the engineer's `engine.in_flight` decision, the save cut takes the AC34 baseline on
  `m@copy`, the open cut binds, reads units and copies in that order, and only `m@copy` is checked. AC52's handoff is
  verified indirectly: a missing marker or a wrong handoff would raise an `engine.host_state` request that the matrix
  asserts absent.
- No engineering number introduced; the read-back tolerance comes only from the frozen basis field
  `checks.readback_relative_tolerance_ratio` with no fallback value. Error codes as in the contract.
- Tests run by the reviewer: the twelve T19a test files (cycle, crash matrix, host state, engine amendments, journal
  events, CSI revisions, units trap, build_ports, session, exit codes): `214 passed in 140.90s`. Writer's gate without
  mutation at 5991420: `check: pass` (log `<lead>/logs/b138-gate-nomut-3.log`).

Findings (author): none of severity high or medium.

Findings (lead, non-blocking):
1. AC52 says the real-engine cycle journal records the guarantee and the original's write effect;
   `test_csi_cycle.py::test_cycle_steps` does not assert `opens_model_without_writing is True` and `effect == "write"`
   on the `csi_open_model` `step_started` directly (covered indirectly by the crash matrix and directly only in the
   unit engine test with a test `ToolInfo`). A two-line assertion would make the AC explicit; can ride with W.T8 or a
   later touch of the file.
2. Mutation evidence: the writer's mutation run (on da18e9f) died with the machine restart and was not rerun; T19a
   sets no `mutation: true`, and playbook section 9 item 5 drops the per-task run, so the periodic run covers these
   modules. The lead notes asked for mutation evidence; the lead decides whether that stands.
3. `handed_off` is defeated by any later `model_bound` of the original, so a future resume path that rebinds the
   original (for example a reattach after a host loss) would re-check the unloaded original and stop with
   `model_not_loaded`. Conservative and correct under the spec; the current T19c reload does not rebind (the matrix
   passes).
4. `origin/build/v1` moved to 6469d93 (B-565, eng-dev-gate documents only) after the last merge; the integrator merges.

Verdict: APPROVE.
