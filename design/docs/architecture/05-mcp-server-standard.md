# 05. MCP Server Standard

Status: Proposed; under ADR-0024 this is the target standard for extending the existing Sasaah servers, not a plan to build new ones · Applies to: the Sasaah servers (as a target) and every future server

A server that does not meet this standard is not released. Reviewers check it with the checklist in §14.

## 1. What a server is

A server is a **pure adapter for one host program** (or one file format). It turns small, typed tool calls into host
API calls and returns raw host data and model-integrity issues through the tool contract.

| A server does | A server never does |
|---|---|
| Read, create, modify, analyze, save, through typed tools | Run workflows or multi-step engineering tasks (blocks) |
| Validate inputs (types, units, bounds, references) | Evaluate design code clauses or return PASS/FAIL for code compliance |
| Convert units at the host boundary | Call a language model or a decision model |
| Report model integrity (`check_model`) | Call another MCP server |
| Return host-native design output as raw data, labeled as host output | Run user-supplied scripts or arbitrary API calls |

## 2. Internal structure (ports and adapters)

```
src/<package>/
  server.py          MCP wiring only: registers toolsets, starts stdio transport
  tools/             One module per toolset. Each tool: Pydantic input model, output kind, annotations, docstring
  service/           Use cases. Validation beyond schema, reference resolution, unit conversion, batching
  host/port.py       HostPort: the abstract interface the service layer calls
  host/<real>.py     Real adapter(s): COM, named pipe, REST, file
  host/fake.py       Fake adapter: in-memory model with the same behavior contract, used by all unit tests
  kinds/             Pydantic payload models for every result kind this server produces
```

Rules: tools call services, services call `HostPort`. Nothing outside `host/` imports a host SDK. The fake adapter is a
first-class product: every behavior the service relies on is implemented in the fake and tested against recordings
from the real host ([process/05](../../process/05-testing-and-verification.md) §4).

## 3. Tool design

1. **Name:** `<prefix>_<verb>_<noun>`, lower snake case. Prefixes: `etabs`, `safe`, `sap`, `revit`, `idea`, `dxf`.
2. **Verbs** come from a fixed vocabulary: `list`, `get`, `read`, `find`, `add`, `create`, `define`, `set`, `assign`,
   `move`, `apply`, `delete`, `run`, `check`, `open`, `save`, `close`, `export`, `import`, `reconcile`. A new verb needs
   an ADR.
3. **One responsibility per tool.** If the description needs "and" or "or" to say what the tool does, split it.
4. **Batch by default.** Write tools accept arrays (for example, many frames in one `etabs_add_frames`) up to a
   declared limit (default 500 items, `LIMIT_EXCEEDED` above it). One batch is one host transaction where the host
   allows it.
5. **Lists are paged and filtered**: `offset`, `limit` (default 200, maximum 5000), and typed filters. Ordering is
   deterministic (by host id), so paging is stable.
6. **Descriptions are short and factual**: what the tool does, its preconditions, and what it returns. Parameter
   meaning lives in the schema (`description`, units, bounds, enums), not in prose.
7. **No hidden behavior.** A tool never changes host settings it does not declare (units, active model, selection,
   view) or leaves them changed.

## 4. Toolsets

Tools are grouped into toolsets so a client loads only what a task needs.

| Toolset | Contents | Enabled by default |
|---|---|---|
| `core` | Standard tools ([04](04-tool-contract.md) §9) | Always |
| `read` | `list_*`, `get_*`, `find_*` on model objects and definitions | Yes |
| `file` | `open_model`, `save_model`, `save_model_as`, `create_model`, `close_model` | No |
| `define` | Materials, sections, load patterns, combinations, stories, grids | No |
| `edit` | Add, assign, set, delete on model objects | No |
| `analysis` | `run_analysis`, analysis status, analysis messages | No |
| `results` | Reactions, forces, displacements, drifts, modal results | Yes |
| `host_design` | Host-native design runs and their raw output | No |

Each toolset has at most 25 tools. A server targets at most 80 tools in total. Clients and the harness enable
toolsets by configuration (`--toolsets read,results,edit` or `ENG_TOOLSETS`).

## 5. Write safety

Every tool that changes a model ([ADR-0007](../adr/0007-write-safety.md)):

- accepts `dry_run: bool`. A dry run validates everything, resolves references, and returns the **change set** it
  would apply, without touching the model.
- requires `op_id`, a caller-generated idempotency key. Repeating a call with the same `op_id` and the same inputs
  returns the first result without applying again. The same `op_id` with different inputs is `CONFLICT`.
- returns a change set result: created, modified and deleted objects with their host ids, plus the new
  `model_revision`.
- marks the model **dirty**. `get_model_status` reports `dirty: true` until `check_model` runs on the new revision.
- for destructive operations (`delete_*`, overwriting saves), requires `confirm: true`, else `CONFIRMATION_REQUIRED`.
- records the operation in a **write-ahead op ledger** (`<workspace>/.eng/state/ops/<model_id>.jsonl`) before the
  first host call (intent, inputs, planned objects) and after it (outcome). The ledger survives server restarts, so
  idempotency and reconciliation do too.
- names every object it creates deterministically from `op_id` and the item index, using the host's own naming
  field (for CSI programs the user-defined name argument of the add methods; for Revit a stamped identifier in
  extensible storage). This makes partial application detectable.
- on timeout, returns `TIMEOUT_UNKNOWN_OUTCOME`. The caller must call `reconcile_operation(op_id)` before anything
  else; the server looks up the planned objects by name and answers `applied`, `partial` (listing the missing items),
  or `not_applied`, with evidence. Hosts without transactions (CSI programs) can be partly applied; the caller decides
  how to complete or roll back, through normal tools.

## 6. `check_model`

Every host server implements `check_model` for its host. It reports **integrity, not code compliance**:
objects without sections or properties, unconnected or duplicate objects, zero-length members, missing supports,
undefined references (combinations pointing at missing patterns), host analysis warnings, and unit or model state
problems. The full check list per host lives in each host document. A host-specific check needs a stable code and a
test with a fake model that triggers it.

## 7. Concurrency and threading

- One server process drives one host instance. The server takes a lock file per instance
  (`<workspace>/.eng/state/locks/<host>-<pid>.lock`) recording its own process id. A second server finds the lock;
  if the owning process is alive it refuses with `HOST_LOCKED` (not retryable); if it is dead, it takes over the lock
  and reconciles the op ledger first.
- Host calls execute on a single dedicated worker in submission order (for COM, an STA thread). Reads do not run in
  parallel with writes.
- The request queue has a fixed depth (default 32). A full queue returns `HOST_BUSY` immediately instead of waiting.
- Every call has a timeout class: `fast` (10 s), `normal` (60 s), `long` (configurable, default 2 h, for analysis
  and design runs). Long calls emit MCP progress notifications and honor cancellation where the host allows it.
- A call that exceeds its timeout cannot be interrupted inside the host. The session enters the **wedged** state:
  every new request returns `HOST_WEDGED` until the hung call returns, after which the op ledger is updated and
  reconciliation answers from it.
- A watchdog detects modal dialogs owned by the host process. While one is open, requests return `HOST_BUSY`
  (`host_code: MODAL_DIALOG`) instead of blocking.

## 8. Configuration

| Setting | Environment variable | CLI flag | Default |
|---|---|---|---|
| Workspace | `ENG_WORKSPACE` | `--workspace` | `%LOCALAPPDATA%\eng\workspaces\default` |
| Require references for engineering quantities | `ENG_REQUIRE_REFS` | `--require-refs` | off (the harness always sets it) |
| Toolsets | `ENG_TOOLSETS` | `--toolsets` | `core,read,results` |
| Host attach mode | `ENG_HOST_MODE` | `--host-mode` | `attach` (to a running instance) |
| Host instance selector | `ENG_HOST_INSTANCE` | `--host-instance` | the only running instance, else error |
| Timeouts | `ENG_TIMEOUT_<CLASS>_S` | `--timeout-<class>` | see §7 |
| Log level | `ENG_LOG_LEVEL` | `--log-level` | `info` |

No configuration file is required. A server never reads configuration from the model or from input files.

## 9. Logging and audit

- Structured JSON lines to `<workspace>/.eng/logs/<server>.jsonl`: timestamp, level, tool, `op_id`, duration,
  result id or error code. Never secrets, never full payloads.
- Every write appends an audit record to `<workspace>/.eng/audit/<server>.jsonl`: `op_id`, tool, input references,
  change set id, model revision before and after, outcome.

## 10. Packaging

- Published to PyPI; runnable with `uvx <server-name>`.
- Python version: pinned per repository with `uv python pin` (currently 3.12 or newer).
- Entry point `<server-name>` starts the stdio server. `<server-name> --version` and `--list-tools` work without
  a host.
- Windows-only servers declare it in package metadata and fail fast with a clear message on other systems.

## 11. Performance

- Server overhead (validation, references, conversion, envelope, store write) must stay below 50 ms per call at
  the 95th percentile for payloads under 1 MB, measured against the fake host.
- No read caching until outside-edit detection is proven reliable for the host (spike S-04). Edits made in the host's
  own window would otherwise be served stale.
- Bulk work uses batch tools and, for CSI hosts, the in-process plugin when it is available ([06](06-csi-servers.md) §2–3).

## 12. Testing

Required for every server ([process/05](../../process/05-testing-and-verification.md)):
unit tests against the fake host for every tool; contract tests that validate every envelope and kind against its
schema; error tests for every declared error path; a live acceptance script per toolset that the owner runs on a real
host and records.

## 13. Documentation

`docs/tools.md` is generated from the tool definitions (names, descriptions, schemas, annotations, toolsets). CI
fails if the committed file differs from the generated one. Hand-written docs explain concepts, never re-state schemas.

## 14. Release checklist for a server

- [ ] Every tool follows §3 naming and vocabulary, and belongs to a toolset within the size limits.
- [ ] Every parameter has type, unit, bounds, and ref-capability declared ([04](04-tool-contract.md) §7).
- [ ] Every write tool supports `dry_run`, `op_id`, the op ledger, deterministic naming, change sets, dirty marking,
      and `reconcile_operation` (including `partial`).
- [ ] Host lock, wedged state and modal-dialog watchdog are implemented and tested with the fake host.
- [ ] No tool runs scripts, evaluates expressions, or forwards arbitrary host API calls.
- [ ] `check_model` covers the host's check list, with a test per issue code.
- [ ] Fake host covers every behavior used; recordings from the real host are up to date.
- [ ] Generated tool catalog is current.
- [ ] Live acceptance record exists for the release's host version.
