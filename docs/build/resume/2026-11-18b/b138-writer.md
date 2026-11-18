# B-138 writer handoff (session 4 of 4)

S.T19a (plan 0002 T19a), risk r1, r2, r3. Worktree `<worktrees>/b138`, branch
`feat/b138-harness-st19-port-wiring-edit-cycle`, tracking origin; no rebase, no force push.

## Start state checked

- Branch on origin at `0a407606b1b49c8f7d6277bd6a585d20fbcd6762` (verified with `git rev-parse`); first `test:` commit
  `eeae76fec4108d95cefb77c2801a8a10cfe27210` is an ancestor (verified with `git merge-base --is-ancestor`).
- Merged `origin/build/v1` at `da10f87` (B-562 #418 and B-563 #419 on it) as `8f16e73`; the one conflict,
  `packages/eng-harness/CHANGELOG.md`, resolved by keeping both sides' lines.

## Done in this session

1. `c84a01c` feat (B-562 scope, all files in the T19a list):
   - `ports.py`: `ToolInfo.opens_model_without_writing(args)`, false by default.
   - `adapters/csi/_revisions.py`: `CsiToolInfo` returns true only for `csi_open_model` with no `path` key.
   - `journal/_events.py`: `StepStarted.opens_model_without_writing: StrictBool | None`; true only on a `tool` step with
     effect `write` and action `open`; a wrap serializer drops the field when `None`, so earlier payloads keep their
     canonical form and hashes (journal version 1).
   - `engine/_ctx_impl.py`: records the explicit true on the attempt's `step_started` before the call; skips only that
     step's dirty mark live, on an immediate `applied` and in replay (the recorded value of the latest attempt); an
     immediately applied open now goes through the same post-open binding, units and EC1 copy as a success (`_opened`);
     a replayed open fills a missing binding and units from the journaled host key and action before a still-live copy,
     and is not bound again when its recorded copy was replayed.
   - `engine/_hostsafety.py`: `Pending.bind` takes `host_key` and `action` instead of a `ToolInfo`.
   - `engine/_modes.py`: `_copy` reports whether it replayed the journal; `Modes.handed(path)` says the recorded
     `~post.working_copy` of that open was replayed.
   - `engine/_inflight.py`: `Fold.content(key)` (writes without a marked open that completed or was applied),
     `Fold.copies` (uncut `working_copy` saves with their path), `Fold.cuts`; `lacking` uses the content view.
     `writes`, `written`, `pending` stay raw (leases, reconciliation, restore restrictions).
   - `engine/_hoststate.py`: the latest write result for the comparison and the 8a save candidate come from the content
     view; `handed_off(f, key)` skips the original's state read only on the full journal proof of engine 4.5.4 (all
     writes on the key are resolved marked opens, none cut; the open's `~post.working_copy.<key>` completed after the
     open's outcome, uncut, naming the key and a distinct copy, with the copy's `model_saved` role `working_copy` inside
     that step; no later binding of the original).
2. `9837918` test: the B-562 regressions (journal marker and legacy payload; CSI descriptor opt-in and exclusions;
   dirty state, immediate applied and replayed open; 16 handoff proof cases, content view, comparison provenance,
   pending open on a lost model, copy still checked after the handoff).
3. `da18e9f`: `test_units_trap` passes its engineering quantity as a `Ref` (invariant 2 refused the raw `$ref` dict
   before the port call, which was the only failure of the first gate run); CHANGELOG line for AC52; local-testing
   item 26 extended for the original-open handoff.

With 1 the committed cycle and the full six-write AC36 matrix pass: `test_cycle_steps` checks only `m@copy`; the
open cut binds `m`, reads its units and then takes the copy; setters are adapter `applied` with evidence; the open,
save, analysis and design cuts take the engineer's `engine.in_flight` decision; the save cut takes the AC34 `accept`
baseline on `m@copy`; one logical call and one attempt per cut. Command:
`uv run pytest -q -o addopts='' packages/eng-harness/tests/workflow/test_csi_cycle.py packages/eng-harness/tests/replay/test_csi_resume.py`
-> `7 passed in 37.81s`.

## Verification

- `uv run eng-gate check --package eng-harness --skip mutation` at `da18e9f`: `check: pass` (lock, config, format,
  lint, types, forbidden, imports, ratchet, secrets, tests, docs-fresh, licenses, workflows all pass; tests
  `2055 passed`; ratchet notice RT001 about `tools/eng-dev-gate` noqa count, not this member). Log
  `<lead>/logs/b138-gate-nomut-2.log`.
- `uv run -q eng-gate test-first --base da10f87 --head HEAD --title "<pull request title>"` at `da18e9f`:
  `test-first: pass`.
- Mutation (`--only mutation`, under `gate.lock`, log `<lead>/logs/b138-mutation.log`): started at 05:01 UTC
  on `da18e9f`; the machine restarted (uptime 06:10 UTC) before it produced a result (the log holds only the uv warning).
  Not run again: plan T19a does not set `mutation: true` and playbook section 9 item 5 (owner decision 2026-11-18)
  drops the per-task mutation run; the periodic mutation run every ten merges covers these modules.
- Pushed fast-forward after each part: `c84a01c`, `9837918`, `da18e9f`, then `5991420` (below).

## Continuation after the machine restart (2026-11-18, 06:11 UTC)

- Worktree reused, tree clean at `da18e9f` = origin. `origin/build/v1` had moved to `51d9573` (B-555 #420, B-164 #421,
  B-564 #422). Merged it as `5991420`; one conflict, `packages/eng-harness/CHANGELOG.md`, kept both sides' lines.
  `engine/_ctx_impl.py` auto-merged (B-164 adds the `basis` loader to `Ctx`; the only constructor call is
  `_runner.py`, updated on the base side).
- `uv run eng-gate check --package eng-harness --skip mutation` at `5991420`: `check: pass` (every step pass; notice
  RT001 for `tools/eng-dev-gate`, not this member). Log `<lead>/logs/b138-gate-nomut-3.log`.
- `uv run -q eng-gate test-first --base 51d9573 --head HEAD --title "feat(eng-harness): port wiring ... (B-138)"` at
  `5991420`: `test-first: pass`.
- Counted lines at `5991420` over the merge base `51d9573`: 478 (unchanged), 1288 test lines; every file in the T19a
  list.
- Pushed `da18e9f..5991420` fast-forward. PR body `<lead>/pr/b138-body.md` updated with these facts.

## Counted lines

478 counted (additions plus deletions over `git diff --numstat -M` from the merge base, `da10f87` then `51d9573`, test files excluded), 1288 test lines.
Plan estimate 380 (information only, owner decision of 2026-11-17). Every changed file is in the T19a `files` list
(16 source and document files, 12 test files).

## Review points of the earlier lead reviews

- Preliminary findings 1 to 5 and the adapter checkpoint's stale-PID finding: resolved in sessions 1 to 3 (pause
  checkpoint review approved the scoped fix).
- Pause checkpoint "CHANGES pending B-562": the B-562 port capability, journal field and engine changes are now
  implemented with the regressions plan T19a names; the committed six-write matrix passes; test-first and the gate
  without mutation pass; mutation as above.

## Left for later roles

- Independent final review of the whole diff and the sources verification (engine EC1 and 4.5.4 proof especially).
- Local CI on the merged head; owner-side Windows and real ETABS checks (local-testing item 26).

## Risks and notes for later tasks

- `Pending.bind` signature changed (`host_key`, `action`); no other caller in the tree.
- `handed_off` uses `Fold.copies`, which keeps only uncut `working_copy` saves; a restore cut that covers the copy's
  save or the open removes the handoff, so the original is checked again (conservative).
- An explicit `path: null` argument of `csi_open_model` gets no guarantee (conservative; the port treats it as the
  pathless open).
- Gate runner (mutation step only, `uv run eng-gate check --package eng-harness --only mutation` under gate.lock, log `<lead>/logs/b138-mutation.log`) at `5991420` (matches the `check: pass` head of 06:19 UTC): FAILED with MU002, mutmut run timed out after 7200 s; the cleanup then raised `OSError: [Errno 39] Directory not empty: .../member/mutants`; no surviving mutant is reported (the log holds 0 survived lines).
- Gate runner attempt 1 (mutation): BLOCKED; the writer must rerun the mutation step (playbook section 7 item 5 gate fix round) after checking the mutmut run time for the eng-harness modules.
