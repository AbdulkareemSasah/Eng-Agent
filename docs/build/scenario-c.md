<!-- The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text. -->

# Scenario C: two candidate reductions of the first-live-run path (analyst report)

Basis: `origin/build/v1` at 3b89c92 (B-455 merged), read in `<build-v1>`. Path under test: section 6.2 of
`task-log-brief.md` (scenario B, 50 tasks). Both reductions are plan amendments under D-12/D-28 and go to the owner
with Q10. Nothing here was assumed from the brief. Every claim below cites the file and section it comes from.

Result: both reductions hold, each with conditions. The path drops from 50 tasks to 41: S.T16, S.T17, F.T1, F.T2 and
F.T3 leave it, and so do P.T4, P.T6, P.T7 and P.T9. S.T19 becomes S.T19a and P.T10 becomes P.T10a, so neither changes
the count.

---

## 1. Split of servers plan 0002 T19 (port wiring)

### Verdict: holds, with conditions

### Evidence

- **What T19 covers needs neither the command-line adapter, nor recordings, nor SAFE profiles. The one exception is
  the SAFE stop test.**
  - Plan 0002 T19 (`packages/eng-harness/docs/plans/0002-servers-and-adapters.md`, front matter and §2 "T19 End to
    end") covers AC9, AC22, AC36 and AC41. Its tests_first are `test_cycle_steps`, `test_crash_matrix`,
    `test_allowlist_loaded_for_route`, `test_build_mismatch_stops_run`, `test_safe_build_mismatch_stops_run` and
    `test_units_trap`.
  - Spec 0002 (`specs/0002-servers-and-adapters.md`):
    - AC36 (§3.9) lists launch, open copy, read state, edits, save, analysis, design and results. Its crash matrix
      kills the engine at each CSI write step. There is no command-line tool step and no recording.
    - §9 (test strategy) runs AC36 and AC41 against "real server processes of the synthetic fakes".
    - AC9's engine clause and AC22 are ETABS-only.
    - AC41's `build_ports` case uses a "synthetic routed allowlist (test data, product-neutral)".
  - The only SAFE item is `test_safe_build_mismatch_stops_run`. Spec 0008 AC4 placed it in 0002 T19 (B-413). That is
    also the only reason T19 waits for plan 0008 T3, as the T19 prose and plan 0002 §3 both say.
- **T17 is not needed by T19.**
  - AC33 and AC34 (spec 0002 §3.8) are T17's own criteria.
  - The recorded-reply tests "skip with reason when no recording exists" (AC34). LOCAL-TESTING §4 says recordings
    exist only after the owner records them, which happens after a live session.
  - T19 shares no source file with T16 or T17:
    - T16 holds `adapters/cli/**`, `_toolport.py` and `tests/fakes/sasaah_cli/**`.
    - T17 holds `servers/_record.py`, `servers/__init__.py` and `tests/fakes/recorded/**`.
    - T19 holds `adapters/__init__.py`, its tests and `tests/fakes/sasaah_csi/**`.
  - The synthetic CSI fake is serialized through T14 (plan 0002 §1, "the tasks that share it (T6b, T10, T11, T11b,
    T12 to T14, T19)"). `depends_on: [T17]` is therefore only the linear chain, not a code dependency.
- **`build_ports` does not need the command-line adapter for ETABS.**
  - Spec 0002 §4.1: `build_ports(...) -> AdapterPorts (tool_port, host_port)`.
  - The merged `AdapterToolPort` (`src/eng_harness/adapters/_toolport.py`) is per adapter, over one allowlist.
    Command-line tools are a second adapter (spec 0002 §4.7) that `build_ports` would compose later.
  - Merged code holds no `adapters/cli/` package yet.
- **No edit-cycle task needs the command-line adapter.**
  - Spec 0007 §7 (non-goals) excludes "the DXF start (18 §2, §6)".
  - Plan 0007 §3 names no plan 0002 T16 or T17 for any task. T8 and T12 need "plan 0002 T19". T9 needs T13, and T15
    only for the unlock test (later cycles).
- **Why B-138 gained the F.T3 dependency.** Plan 0002 §3 says T19 "waits for plan 0008 T3 ... because it writes the
  SAFE engine stop of spec 0008 AC4". Plan 0008 §3 says the same: "Plan 0002 T19 in turn waits for T3 of this plan".
  The registry still lists only S.T17, S.T18 and S.T20 plus the engine tasks. Brief 6.1 item 8 proposed adding F.T3.
- **The SAFE stop can move to plan 0008 T3 without breaking test-first.**
  - B-413 placed it in 0002 T19 only because "plan 0008 has no later task that adds a source file the stop needs, so
    there it would pass at its merge base (TF004)". That holds only while `build_ports` comes after 0008 T3.
  - Once S.T19a has merged `build_ports`, the stop fails at F.T3's base for the right reason: F.T3 is the task that
    pins the SAFE fingerprint and adds the SAFE entries (plan 0008 T3, spec 0008 AC4).
- **S.T18 and S.T20 are merged** (3d0b4fb B-137, 3968ae7 B-139). The registry's B-138 `pending_deps` still lists both,
  which is stale.

### Amendment (documents, one lead amendment pull request)

**Plan 0002: T19 becomes T19a and T19b.**

```yaml
  - id: T19a
    title: Port wiring for the CSI adapter (ETABS), edit-cycle step sequence and crash matrix against real fake-server processes
    # Amendment (B-NNN, D-12/D-28): split of T19. The SAFE engine stop moves to plan 0008 T3. The command-line adapter
    # wiring moves to T19b. build_ports refuses [cli_tools.*] entries with NOT_IMPLEMENTED (gap H-G8) until T19b.
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/tests/workflow/test_csi_cycle.py"
      - "packages/eng-harness/tests/replay/test_csi_resume.py"
      - "packages/eng-harness/tests/workflow/test_build_ports.py"
      - "packages/eng-harness/tests/workflow/servers/test_session.py"   # the ETABS stop only
      - "packages/eng-harness/tests/workflow/adapters/test_units_after_timeout.py"
      - "packages/eng-harness/tests/fakes/sasaah_csi/**"
    max_changed_lines: 200
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/test_csi_cycle.py::test_cycle_steps"
      - "packages/eng-harness/tests/replay/test_csi_resume.py::test_crash_matrix"
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_allowlist_loaded_for_route"
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_cli_tools_not_wired_gap"
      - "packages/eng-harness/tests/workflow/servers/test_session.py::test_build_mismatch_stops_run"
      - "packages/eng-harness/tests/workflow/adapters/test_units_after_timeout.py::test_units_trap"
    covers: [AC9, AC22, AC36, AC41]
    depends_on: [T14, T18, T20]   # external: engine plan 0001 T13, T15, T16, T19 (as today)
  - id: T19b
    title: Command-line tool adapter in build_ports (closes gap H-G8)
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/adapters/__init__.py"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/tests/workflow/test_build_ports.py"
    max_changed_lines: 120
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/workflow/test_build_ports.py::test_cli_tool_routed_through_build_ports"
    covers: [AC43]
    depends_on: [T16, T19a]
```

T19b replaces the H-G8 gap test because the specified behaviour changes. That is a spec change, not a test changed to
pass, by the same pattern as plan 0008 T9.

**Other plan 0002 edits**

- §1: change "an end-to-end task (T19)" to T19a and T19b.
- §2: the T19 paragraph is split. The SAFE-stop sentences move to plan 0008 T3.
- §3: delete "T19 also waits for plan 0008 T3". Write that T19a waits for engine T13, T15, T16 and T19 only, and T19b
  waits for T16 and T19a.

**Spec 0002**

- AC9 and AC22: change "plan task T19" to "plan task T19a".
- New AC43 (§3.9): "Given `[cli_tools.*]` entries, `build_ports` routes each to the command-line tool adapter, and
  `ToolPort.describe` and `ToolPort.call` of such a tool reach it. Until plan task T19b, `build_ports` refuses a
  configuration with `[cli_tools.*]` entries with `NOT_IMPLEMENTED` (H-G8) rather than drop them."
- New gap H-G8 in §11. Search shows the id is unused.
- §9 table: add AC43 to the workflow row.

**Spec 0008 AC4:** "written in plan 0002 task T19, which waits for plan task T3" becomes "written in plan task T3,
after plan 0002 T19a, which adds `build_ports`".

**Plan 0008**

- T3:
  - Add `tests/workflow/servers/test_session.py` to files.
  - Add `test_session.py::test_safe_build_mismatch_stops_run` to tests_first.
  - External dependencies gain plan 0002 T19a and engine 0001 T13, T15, T16 and T19.
  - Update the comment at its line 59.
- T1: add `src/eng_harness/adapters/__init__.py` (where `build_ports` lives) to files. The per-product build check of
  T1 must reach `build_ports`; plan 0008 T1's own B-418 pre-start grep rule would otherwise add the file later.
- T8: the comments at lines 186 and 187 and §3 lines 324 to 328 change to "plan 0002 T17, T19a; SAFE stop in T3". Drop
  "no other task of this plan runs the real engine".
- §2: update lines 267 and 277.

**Re-point "plan 0002 T19" to T19a**

- Plan 0006: line 891, table row at line 979, §3 line 922.
- Plan 0007 §3: rows T8 and T12.
- Plan 0010 §3: row T9.
- Plan 0011 §3: "T15 needs T19".
- Plan 0012: lines 11 and 12, 172 and 173, and 205, which become "after plan 0002 T19a and plan 0008 T3". The SAP2000
  stop still goes into the file that holds both earlier stops.
- Spec 0012 line 73.
- `HANDOFF.md` line 87 (lead documents).

**Registry**

- B-138 becomes S.T19a. Its `pending_deps` are E.T13, E.T15, E.T16 and E.T19. S.T17 is removed, the stale S.T18 and
  S.T20 are removed, and F.T3 is not added.
- New work item: S.T19b (pending S.T16, S.T19a).
- Brief 6.1 item 8 drops "add the F.T3 dependency to B-138".
- Serialization condition: S.T19a and W.T5 (B-199) both edit `tests/fakes/sasaah_csi/**`, and cross-plan ordering is
  in the registry, not in either plan's `depends_on`. Give S.T19a a dependency on W.T5. W.T5 is wave 4 and S.T19 is
  wave 10, so the order is unchanged.

### Tasks that leave the path

S.T16 (B-135), S.T17 (B-136), F.T1 (B-210), F.T2 (B-211) and F.T3 (B-212).

### What returns later, and when

- **S.T16, then S.T19b:** with the DXF start, need (a). Nothing in plan 0007 needs them.
- **S.T17:** recommended immediately after the first run, or in a parallel low-priority lane. It is what lets the
  owner make recordings, and AC34 fidelity can only be checked on recordings.
- **F.T1 to F.T3 (with the SAFE stop in F.T3), then F.T4 and later:** with the SAFE work, already deferred in brief 6.5.

### Risks

- Tested after the first run instead of before it:
  - spec 0002 AC6, AC31 and AC32 (command-line tools);
  - AC33 and AC34 (record mode, fidelity; AC34 skips either way until recordings exist);
  - spec 0008 AC1 to AC5, AC28, and AC4's engine stop.

  None is exercised by an ETABS-only run.
- `record_csi.py` will not exist at the first live session. The owner cannot capture recordings in that session, so
  the fakes stay unchecked against the real server for longer.
- F.T1 must later reach into `build_ports` (per-product build check). That puts pressure on its 350-line budget. A
  further split would be decided at F.T1, not now.
- S.T19a's `build_ports` has to refuse `[cli_tools.*]` rather than ignore them. Otherwise `unreleased_tools()` would
  list command-line tools in the run header that no port can reach, a silent omission. The owner's live `harness.toml`
  must hold no `[cli_tools.*]` section until T19b.
- The amendment touches nine documents. Under AGENTS.md rule 4 every reference must move in the same pull request.

---

## 2. Rules-only decision assembly (providers off the path)

### Verdict: holds, with conditions

### Evidence

- **Phase 1 has no providers by design.**
  - Spec 0005 AC17 (§3.4): "Given no rule matches and no provider is configured (the phase 1 deployment, whatever the
    policy) ... a `PendingAnswer` ... no socket is opened".
  - Spec 0005 §4.5: the cascade takes "optional `DecisionProvider` and `LLMProvider` (both `None` in phase 1)".
  - Spec 0005 §4.3 and §4.6: "no release exists in phase 1"; "In phase 1 there are no providers".
  - ADR-0025 decision 5, as cited by the brief.
- **The decision tasks do not need the P lane.**
  - D.T7 (cascade core: tier 1, engineer tier, pending, record) covers AC17.
  - D.T8 and D.T9 test tiers 2 and 3 and `decide_many` against fake providers. Plan 0005 front matter: D.T8 depends
    only on T7.
  - D.T10 (engine wiring, `runtime_summary`) depends on T9 and the engine.
  - None depends on P.T4, P.T6, P.T7 or P.T9. All four stay on the path because the `_cascade.py` chain and I.T18
    (D.T7, D.T10) need them.
- **The command line needs only an assembler function, but needs a real one.**
  - Spec 0006 AC62: `load_providers_config` is read in step 1 (P.T1, merged as B-220). `assemble_decision_runtime` "is
    called exactly once ... also when no `[providers.*]` table exists", and the cascade is built from its runtime.
  - I.T14b and I.T16b (plan 0006) use injected recorders and do not wait for plan 0009 (plan 0009 §3, B-412).
  - Only I.T18 binds `decision_assembler` to the real `assemble_decision_runtime` (plan 0009 T10).
  - Spec 0006 §4.1 and plan 0006 §2 T18 forbid a stub: "no stub stands in for the missing implementation"; "the lead
    amends this plan to split T18 rather than bind a stub". A rules-only assembler is therefore acceptable only as a
    specified, tested function: a spec 0009 amendment, not a placeholder.
- **Spec 0009 already defines the phase-1 fall-through.** AC30: "no provider table, or a provider whose build raised,
  then the cascade receives `None` for that tier and the run proceeds with rules and the engineer (spec 0005 AC17); the
  failure is in the summary and in the build warnings, never silently dropped". A phase-1 assembler is the AC30
  behaviour without the factory.
- **Releases are moot in phase 1.**
  - Spec 0006 Q15: until `[decisions]` is named, "T14 builds `DecisionSettings` with its defaults (`local_only`
    false, no release), which is the phase 1 behavior".
  - A release changes nothing while no provider answers (spec 0005 §4.5 step 5).
  - Dropping every release (fail closed) needs neither `verify_releases` (P.T9) nor `point_policies` (Q16).
- **The path chain today:**
  - P.T10 (B-229) depends on P.T7 and P.T9 (plan 0009 front matter).
  - P.T7 depends on P.T2, P.T4 and P.T6.
  - P.T6 depends on P.T3, P.T4 and P.T5.
  - P.T1, P.T2, P.T3, P.T5 and P.T8 are merged (B-220, B-221, B-222, B-224, B-227).
  - `ReleaseFinding` and `DecisionRuntime` are not merged yet: `decisions/evaluation.py` has no `ReleaseFinding`, and
    `providers/` has no `_runtime.py`.

### Amendment

**Spec 0009**

- New AC49 (§3.6): "Given `assemble_decision_runtime(providers_config, settings, workspace, point_policies)` in a build
  without the provider factory (gap PR-G1), then:
  1. With no `[providers.*]` table, the runtime holds no provider, no release and a summary with an empty provider
     list.
  2. A configured provider is not constructed, no client is created and no key is read. The cascade receives `None`
     for its tier. Its summary entry (`name`, `model`, `version`, `is_local`, `tier`, `status = "not_implemented"`) and
     a build warning name PR-G1.
  3. Every `shadow_released` entry is dropped with a warning (`not_verified`), so effective shadow stays on.
     `point_policies` may be `None`.
  4. No summary or warning holds an endpoint, a `key_ref` or a header.
  5. With the real engine and cascade, `run_started.decision_runtime` equals the summary."
- New gap PR-G1 in §11 (provider factory and release verification absent). It is closed by plan task T10b. The id is
  unused.
- §4.1: one sentence pointing to AC49.

**Spec 0006 Q16:** add "(d) under spec 0009 AC49 (phase 1) `point_policies` may be `None`. Q16 (a) then gates only plan
0009 T10b."

**Plan 0009: T10 becomes T10a and T10b.**

```yaml
  - id: T10a
    title: Phase-1 runtime assembly (rules and engineer; providers not built, releases not kept; gap PR-G1)
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/src/eng_harness/providers/__init__.py"
      - "packages/eng-harness/src/eng_harness/providers/_runtime.py"
      - "packages/eng-harness/tests/unit/providers/test_runtime.py"
      - "packages/eng-harness/tests/workflow/providers/test_phase1_runtime.py"
    max_changed_lines: 150
    max_sessions: 2
    tests_first:
      - "packages/eng-harness/tests/unit/providers/test_runtime.py::test_no_provider_table_gives_phase1_runtime"
      - "packages/eng-harness/tests/unit/providers/test_runtime.py::test_configured_provider_not_built_is_reported"
      - "packages/eng-harness/tests/unit/providers/test_runtime.py::test_no_release_kept_without_verification"
      - "packages/eng-harness/tests/unit/providers/test_runtime.py::test_phase1_summary_has_no_secrets"
      - "packages/eng-harness/tests/workflow/providers/test_phase1_runtime.py::test_run_header_records_phase1_summary"
    covers: [AC49]
    depends_on: [T1]   # external: plan 0005 T10 (cascade runtime_summary, engine wiring), engine plan 0001 T14b
  - id: T10b
    title: Runtime assembly with built providers and verified releases, shadow-mode workflow, replay and isolation tests, local-testing notes (closes PR-G1)
    files:
      - "packages/eng-harness/pyproject.toml"
      - "packages/eng-harness/CHANGELOG.md"
      - "packages/eng-harness/docs/local-testing.md"
      - "packages/eng-harness/src/eng_harness/providers/__init__.py"
      - "packages/eng-harness/src/eng_harness/providers/_runtime.py"
      - "packages/eng-harness/tests/unit/providers/test_runtime.py"
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py"
      - "packages/eng-harness/tests/replay/test_provider_replay.py"
      - "packages/eng-harness/tests/rules/test_provider_imports.py"
      - "packages/eng-harness/tests/data/recordings/**"
    max_changed_lines: 200
    max_sessions: 3
    tests_first:
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py::test_timeouts_fall_through"
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py::test_one_screen_with_both_suggestions"
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py::test_decide_many_one_batched_screen"
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py::test_provider_outage"
      - "packages/eng-harness/tests/replay/test_provider_replay.py::test_resume_does_not_requery_providers"
      - "packages/eng-harness/tests/workflow/providers/test_shadow_workflow.py::test_run_header_records_runtime_summary"
    covers: [AC31, AC32, AC33, AC34, AC35, AC45, AC48]
    depends_on: [T7, T9, T10a]
```

Notes on T10b:

- `test_isolation` (AC45) is written in T10b but is not a tests_first node. At T10b's base, `_runtime.py` and the
  provider modules already exist, so it would pass there (TF004). This follows the precedent of plan 0009 T1's
  `test_error_shape`, which "stays as a regression test, not first".
- T10b replaces T10a's PR-G1 tests (provider not built, release dropped) because the specified behaviour changes. That
  is a spec change, not a test changed to pass.

**Plan 0006**

- T18 prose: "plan 0009 T1 and T10" becomes "plan 0009 T1 and T10a".
- §3 (line 926) and the table row at line 988 change the same way.
- T18 binds `point_policies`. Under AC49 it may be bound to `None` until T10b.

**Plan 0009 §3 and §5:** T10a needs plan 0005 T10 and engine T14b. T10b adds T7 and T9.

**Registry**

- B-229 becomes P.T10a. Its `pending_deps` are D.T10 and E.T14b.
- New work item: P.T10b (pending P.T7, P.T9, P.T10a).
- B-433 (I.T18): P.T10 becomes P.T10a.
- Brief 6.1 item 6 becomes non-blocking for the path, provided the Q16 (d) amendment is accepted. Q15 is unchanged:
  defaults are phase 1.

**What P.T10 becomes:** P.T10a, the phase-1 assembler, a real and specified function of about 150 lines, stays on the
path. P.T10b holds the original T10 scope (factory, verified releases, shadow workflow, replay, isolation) and is
deferred with the P lane.

### Tasks that leave the path

P.T4 (B-223), P.T6 (B-225), P.T7 (B-226) and P.T9 (B-228).

### What returns later, and when

P.T4, P.T6, P.T7, P.T9 and P.T10b return with phase 2. That means when a provider is first to be configured, after the
owner's S-07 spike (spec 0009 Q1) and the provider dependency ADRs. They are in no case before the first run.

### Risks

- Tested after the first run instead of before it:
  - spec 0009 AC9 to AC27 (Jev and PydanticAI adapters);
  - AC28 to AC30 and AC47 (factory, `local_only`, check command);
  - AC41 to AC44 (evaluation store, `verify_releases`);
  - AC31 to AC35, AC45 and AC48 with recorded providers.

  The live phase-1 run exercises none of them in either scenario, so no live evidence is lost.
- `_runtime.py` is written twice. T10b reworks T10a's code and replaces its PR-G1 tests, which must be recorded as the
  spec change of PR-G1, never as an expectation edit.
- An owner `harness.toml` with `[providers.*]` tables runs with rules and the engineer only. A standard-error warning
  and `status = "not_implemented"` in the journaled summary say so, but an operator could still overlook them.
- OQ-A12 and OQ-Q53 do not disappear. `pydantic-ai-slim`, `keyring` and `httpx2` are already locked
  (`packages/eng-harness/pyproject.toml`, `uv.lock`, merged with B-220). The run installs them even if it never calls
  them, and `cffi` is also reached through `mcp` (OQ-Q53). Only the run's use of them goes.
- The amendment needs owner acceptance as a spec change (new AC49, gap PR-G1, Q16 (d)). Without it, binding the phase-1
  assembler in I.T18 would break the no-stub rule of spec 0006 §4.1.

---

## 3. Path after both reductions (41 tasks)

Removed: S.T16, S.T17, F.T1, F.T2, F.T3, P.T4, P.T6, P.T7, P.T9. Renamed: S.T19 becomes S.T19a (B-138), and P.T10
becomes P.T10a (B-229). Every other wave of 6.2 is unchanged.

- W1 loses P.T9.
- W2 loses P.T4.
- W3 loses P.T6.
- W4 loses F.T1, P.T7 and S.T16.
- W5 loses F.T2 and S.T17.
- W6 loses F.T3.
- W10 holds S.T19a.
- W12 holds P.T10a.

The 6.4 owner items "OQ-A12 and OQ-Q53 if the P lane stays" stay open, for the reason in §2 Risks.

The owner decides (Q10). This report recommends applying both, each with the conditions above, in one lead amendment
pull request per plan family (servers and SAFE, providers and the CLI plan), before S.T19a and P.T10a start.
