> Adapter-only review at the session 2 head. Session 3 fixed the stale PID finding. It still needs complete final implementation and sources review, as recorded in [the current writer note](b138-writer-session-3.md) and [lead review](b138-review.md).

# B-138 production adapter source verification

**Decision — CHANGES REQUESTED.** One high-severity production wiring finding. Reviewed S.T19a at `668c3830c7c25912483d09626d43d64ca87e259b` on the clean `feat/b138-harness-st19-port-wiring-edit-cycle` worktree. This is a source-only review of the files listed below. Full B-138 package and test-first verification remain pending, including the separately tracked B-562 scope and EC1 work.

## High — Resume can try to attach to an expired CSI process before it offers recovery

1. `build_ports` builds a fresh `ServerManager` and passes it into the host port. The constructor creates `CsiSession` before loading the adapter state. The reload restores saved process identity, bindings, files and units with session `-1`. Its unguarded `self._sessions.bind_instance(...)` at `adapters/_hostport.py:330` is new in B-138 commit `f0f68cc9`. `ServerManager.bind_instance` stores one PID and product per host key, with each persisted row overwriting the previous target (`servers/_session.py:168–170`).
2. `Engine.resume` calls server preflight before acquiring leases, checking units, reconciling or checking model state (`engine/_runner.py:255–262`). A configured server's preflight invokes `_ensure` before `_verify` (`servers/_session.py:194–206`). `_ensure` calls `_attach` even on a role's first startup (`287–309`). `_attach` passes only PID and product, and a failed attach becomes `HOST_NOT_CONNECTED` (`371–382`). Preflight turns that failure into a failed check, which the engine raises as `SERVER_CHECK_FAILED` (`engine/_hostsafety.py:45–55`). Thus a healthy server can be refused before its build is verified because the cached model's process died. If a reused PID belongs to an attachable process, this path can attach to that process before the adapter checks the recorded start time. This source trace establishes an attach attempt, with success on a reused PID conditional on what the server accepts.
3. Neither the fresh guard nor the later host-port checks intercept that preflight path. `CsiSession.alive` constructs a `ProcessIdentity` from the recorded PID, start and executable (`adapters/csi/_session_ops.py:49–50`). The implemented inspector predicate checks the PID and start time and requires a live process, excluding zombies on POSIX (`servers/_procinfo.py:90–93,248–251`). It does not separately compare the executable name. `acquire` and `locate` call that predicate (`adapters/_hostport.py:64–70,245–261`). Launch identification and cleanup have their own guards (`servers/_guard.py:78–105`). The session startup attach consults none of them. Session `-1` protects launch ownership but does not suppress `csi_attach`.
4. Spec 0002 §4.3.4 defines preflight as a build check and §4.3.5 retains the normal attach behavior. §4.4.2 and AC47 distinguish known instances by recorded process identity. §4.5.9 defines an absent bound model as unloaded and preserves the run-state cache for recovery. Engine spec 0001 AC63 and §4.5.1 steps 6–8 and §4.5.4 require a lost model with a write in flight to skip reconciliation and reach `model_not_loaded`, where the engineer can restore when the saved state permits it or abandon. The existing engine does that after preflight (`engine/_hoststate.py:40–57,68–69,94–108,139–176` and `engine/_inflight.py:255–261`). The new binding makes those steps unreachable when attach fails solely because the cached process is gone.

Use the existing `self._session.alive(opened)` predicate before registering a reloaded instance with the manager in `_hostport.py`. Preserve all persisted entries, model keys, saved file paths and expected units for the existing recovery path. `_keep` still registers a newly launched or restored instance. Keep normal build checks and failure handling for genuine server failures.

The production wiring regression belongs in S.T19a's `tests/workflow/test_build_ports.py`. Reopen through `build_ports` with a cached instance whose process is absent or whose PID has a different observed start time. Assert that server preflight passes for a valid build, that no attach to the stale PID is recorded, and that the saved key still resolves to its file while the old instance reports unloaded. Keep a live-identity control that attaches normally. The current fake accepts `csi_attach` for any configured PID (`tests/fakes/sasaah_csi/server.py:129–139`), so preflight success alone cannot detect the defect. An end-to-end check, if added to the existing S.T19a replay file, should follow the existing engine's `engine.host_state` request and real restore/abandon path on a journal with an eligible save. The source finding concerns identities already stale when loaded. Checking at load time does not guarantee a host cannot exit later.

## Engineering values, binder and preview subset

- `_FrozenTolerance` follows `JournalReader.header().basis_ref` to `StoreBasisPort` and reads `checks.readback_relative_tolerance_ratio` (`adapters/__init__.py:59–81`, `journal/_reader.py:116–118`, `basis/_port.py:28–48`). It retries while no value is present, excludes booleans and keeps a numeric zero. Missing header, invalid basis or absent/nonnumeric field yield no value. The provider has no caller-selected basis or engineering constant fallback. This matches spec 0002 AC44 and §4.5.8. The writing workflow and freeze contract govern required-field confirmation.
- A single provider feeds the host's `ReadBack` and the CSI reconciler (`adapters/__init__.py:149–189`, `adapters/_hostport.py:145–171`, `adapters/csi/_reconcile.py:74–104`). The tool and host share the written-items book, and the tool uses `host.wrote`. Missing tolerance yields `READBACK_UNAVAILABLE` for a quantity and leaves an unresolved setter outcome unknown where numeric comparison is required. Zero requests exact comparison.
- The synthetic quantity oracle requests 8 kN/m, then gives the fake an observed 10 kN/m (`tests/workflow/test_build_ports.py:191–247`). The comparator uses `abs(observed - requested) <= ratio * abs(requested)` (`adapters/csi/_checks.py:181–214`). The error is 2 kN/m, or `2 / 8 = 0.25` relative. The explicit synthetic confirmed ratio `0.25` allows an inclusive `[6,10]` kN/m and passes at equality. A ratio of zero allows only 8 kN/m, so it reports a mismatch. Missing/nonnumeric data supplies no numeric bound. These are fixture values with synthetic engineer provenance (`tests/fakes/sasaah_csi/wiring.py:176–200`).
- Production enables pre-image recording before ledger append and host send. The hand-wired default preserves a supplied binder reference. The pre-image resolves to the earlier read-back's `observed` value. The bound preview uses the bound model identity and revision plus canonical arguments and any observed pre-image, without dispatching the write. The unbound open exception skips the binder and returns no model handle (`adapters/_toolport.py:235–273,297–348,415–424`). The production binder checks live identity and the expected file, locks that process and reads known model state without consuming an outside file edit or installing a new outside-edit baseline. Version comes from the last state read or a model-info read (`adapters/_hostport.py:178–216,254–261`, `adapters/_identity.py:30–43,60–74`). Relevant test source covers these paths in `tests/workflow/test_build_ports.py:60–188,252–347`. No additional high or medium finding in this subset.

## Reviewed snapshot

Git blob IDs below are relative to `packages/eng-harness/` at the head above.

| File | Git blob |
|---|---|
| `docs/plans/0002-servers-and-adapters.md` | `62f6b5bd507fcb30b9534dbab6102a487f6d4972` |
| `docs/specs/0001-engine.md` | `996ebb22aabf7936430ff42083476623d87b7051` |
| `docs/specs/0002-servers-and-adapters.md` | `38609d7dc497b9afc0a992d59603a8eddf9174f9` |
| `src/eng_harness/adapters/__init__.py` | `e68cc4c0ae734dbee00642fbf36325bfdc5a9f5b` |
| `src/eng_harness/adapters/_hostport.py` | `c90e8c60572dba6912c4fd071c0e650060c0ba48` |
| `src/eng_harness/adapters/_identity.py` | `10658cb39b5740f51d9f6f431603e79ffb988676` |
| `src/eng_harness/adapters/_toolport.py` | `9af4c507417d0ab8423b44581cfb2ced9366f08a` |
| `src/eng_harness/adapters/csi/_checks.py` | `e1ae5b190dc7787d1796207a4a9b282148be2866` |
| `src/eng_harness/adapters/csi/_reconcile.py` | `4f3a257167276db9f3cdc771f32542a77fafdf34` |
| `src/eng_harness/adapters/csi/_session_ops.py` | `1a1fd3258f7c41749f152d1c052128bcbf007f5f` |
| `src/eng_harness/basis/_port.py` | `4b80c716765970dc549ad7964577f8804fc1d041` |
| `src/eng_harness/engine/_hostsafety.py` | `0bfc965c35ad4a06fbdf26b523f1f69ae6753dc5` |
| `src/eng_harness/engine/_hoststate.py` | `2a7e39363b13af499e869b44d00e5b8ea3e866c7` |
| `src/eng_harness/engine/_inflight.py` | `2452092e93f9650e590440f9e74bc9e5bf43cac7` |
| `src/eng_harness/engine/_runner.py` | `49d29dd0563e3273f1b4acf0063beb9f09b0b756` |
| `src/eng_harness/journal/_reader.py` | `167524c4cb95ecb9c50f7e1d8f6944c524c3d371` |
| `src/eng_harness/servers/_guard.py` | `40ae93529c4676a8a19877828dfa3c193f5eb3ce` |
| `src/eng_harness/servers/_procinfo.py` | `81aa4839cb448d98e91a31a80146987afb831926` |
| `src/eng_harness/servers/_session.py` | `286134b6f9c5e60d7cc7a319cd7e0ff5b7d03190` |
| `tests/fakes/sasaah_csi/server.py` | `0c882f9c3cf77c6468012181372a35fcd4539c3d` |
| `tests/fakes/sasaah_csi/wiring.py` | `0cb3bf7ea50a4f736efa38bc8e3cb436a1d3f44d` |
| `tests/workflow/adapters/test_csi_session_ops.py` | `ead336e509439fb116717ceec4444bd38d169753` |
| `tests/workflow/test_build_ports.py` | `6acd54af526bb1e072423409f62c09a477292c8d` |

No tests, gates, mutation or live CSI execution were performed in this review. Only this report was written.
