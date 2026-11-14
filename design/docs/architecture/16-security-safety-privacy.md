# 16. Security, Safety and Privacy

Status: Proposed · Applies to: every repository

## 1. Engineering safety

| Risk | Controls |
|---|---|
| A wrong number that looks right | Numbers only from tools (P1); references instead of copies (P2); verified and approved checks only in production (code pack lifecycle); full traces; sign-off |
| A model left broken | Transactions and atomic batches; check after every write (P7); working copies by default; backups before promotion |
| A silent assumption | Design basis with sources; runs refuse to start with missing inputs (P8); `NEEDS_ENGINEER` instead of clamping |
| An unknown write outcome treated as success or failure | `TIMEOUT_UNKNOWN_OUTCOME`, idempotency keys, reconciliation before the next step (P9) |
| A model deciding something it should not | Decisions return options only; shadow mode until evaluated; engineer tier always available |

## 2. Data privacy

- Default provider is a cloud service (OpenRouter). Only the typed decision state is sent, never files, project
  names, client names, locations or full results. Decision states are built from summaries by design.
- A redaction check runs on every outgoing decision state: known sensitive fields (project, client, address, person
  names, file paths) are rejected before sending.
- Local or private providers are a setting, for projects that must not leave the machine. A project can be marked
  `local_only`, which disables cloud providers for its runs.
- No telemetry is sent anywhere by any component. Diagnostics stay in the workspace.
- Task logs are never sent to the decision provider or to CI reviewer providers. Development sessions may read them
  through their configured model provider ([ADR-0034](../adr/0034-task-log-by-default.md) D11); nothing from a log
  leaves `tasklog/` except ids, categories, counts and owner-released need statements (A24).

## 3. Secrets

- Provider keys are stored in the operating system's credential store and read at runtime.
- Keys never appear in project files, templates, journals, logs, error messages, or URLs.
- Repositories contain no secrets; a secret scan runs in CI and before any repository becomes public.
- Task logs pass a guard before writing that keeps secrets, tokens, page launch addresses and personal paths out of
  every record, withholding a matching span of owner words with a visible marker (ADR-0034 D7).

### Task-log privacy policy, credential exception and publication

The task logs under `tasklog/` are the one place client data may be committed, and the owner's login is used for one
narrow purpose: pushing log-only commits from his machine. The privacy policy (`full` now, `sanitized` later) is a
separate, replaceable component; the workspace repository is never made public, and anything published comes from a
fresh or filtered history after `publish-check`. The rules are ADR-0034 D6 (credential exception), D7 (guard and
policy), D8 (the A11 exception and A24) and D9 (publication block).

## 4. Untrusted input

- DXF, Excel, PDF and model files may come from outside parties. Their text (layer names, notes, parameter values) is
  data: returned only in typed string fields and never placed in instruction positions for any model.
- Decision states quote such text only as bounded, labeled fields, and decision outputs are restricted to options, so
  injected text cannot produce actions.

## 5. Local attack surface

- Named pipes are restricted to the current user.
- The UI listens only on `127.0.0.1`, with a per-session token.
- Servers never open network listeners except where a host requires a local service (IDEA's local REST service).

## 6. Process integrity and host programs

- MCP servers and the host programs they drive must run at the same Windows integrity level, normally the user's
  standard level. The harness starts servers itself; a normal terminal works too.
- No component, script or development agent changes operating-system security settings, file ACLs, ownership or
  integrity levels to make something work. Doing so broke host plug-in loading in the past.

## 7. Development safety

- Development agents never write into program installation folders, host add-in folders or deployment targets.
  Installing or deploying is a documented step the engineer runs.
- Dependencies are pinned through `uv.lock`; new dependencies need an ADR; allowed licenses are MIT, BSD, Apache-2.0,
  ISC, PSF and MPL-2.0. GPL and AGPL dependencies are not allowed in libraries.
- Vendor assemblies (CSI, Autodesk, IDEA) are never committed or redistributed.

## 8. Supply chain for releases

- Releases are built in CI from tagged commits, with `uv build`, and published with trusted publishing where the
  registry supports it.
- Every release has a changelog and a software bill of materials generated from the lock file.
