# LOCAL-TESTING: how to test v1 on your Windows machine

Status: draft. It is kept current as the build progresses ([BUILD-STATUS.md](BUILD-STATUS.md)).

**Nothing in this guide was run in the build environment.** The build environment has no ETABS, SAFE, SAP2000, Revit
or IDEA StatiCa, and no Sasaah server build. Every step below is something you run. The "what you should see" lines
are what the specs say should happen. They are not results. If what you see differs, that is a finding: report it
(section 6). Do not adjust anything to make it match.

Today you can run section 1, section 2 (the spikes) and the items in section 7 that need no eng-harness code (for example 7.1). Sections 3 to 5 wait for eng-harness to merge; check [BUILD-STATUS.md](BUILD-STATUS.md) §3. Section 6 applies to every section.

## How to read this guide

- **A terminal** is the text window where you type commands. On Windows we use PowerShell. Commands are in grey
  boxes. Type them one at a time and press Enter.
- **uv** is the one tool this project uses to install Python and to run every Python command. You never install
  Python packages by any other route ([AGENTS.md](AGENTS.md) §2).
- **A host program** is ETABS, SAFE, SAP2000, Revit or IDEA StatiCa.
- **An MCP server** is a small program that lets other software drive a host program. The Sasaah ones are
  `sasaah-csi-mcp` (ETABS, SAFE, SAP2000), `sasaah-revit-mcp` and `sasaah-idea-mcp`. The harness (`eng-harness`)
  starts them itself when it needs them.
- **The harness** is `eng-harness`, the program that runs the model edit cycle.
- **Spike**: a small test script that answers one question on your machine (for example S-02 or S-04, section 2).
- **Hash (SHA-256)**: a long code computed from a file. Any change to the file changes the code, so it shows whether
  two files are identical.
- **Pin**: the Sasaah commit and the file hash that the harness expects for each server. The harness refuses a server
  build that does not match. You never edit a pin yourself.
- **Tool-list fingerprint**: a hash of the list of tools a server offers. It shows whether the server offers the
  tested tools.
- **Allowlist**: the harness file that holds the tested pins and fingerprints ([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md)
  §4.3.4). It is not available until the eng-harness code has merged.
- **Journal**: the file `journal.sqlite` in the run folder. It is the record of every step of a run.
- **Exit code**: a number a command leaves behind when it ends. In PowerShell, `$LASTEXITCODE` shows it right after
  the command. The meanings for the harness are in section 6.
- **Placeholders** look like `C:\path\to\Sasaah`. Replace each with your own folder. They never mean a real folder
  from this repository.
- **Availability markers.** The code of `eng-harness` is being built now. Where a command comes from code that is
  not on branch `build/v1` yet, the step says so, for example "(available once eng-harness plan 0006 task T16 has
  merged; check BUILD-STATUS.md)". Open [BUILD-STATUS.md](BUILD-STATUS.md) §3 (task table) to see which tasks have
  merged. A command with no marker is in the repository now.
- **Never invented.** Where a value (a timeout, a limit) is not defined by a document, this guide says "not defined
  yet" and lists it under [Open points](#open-points) at the end.

| Command | Where it comes from | Present on `build/v1` now |
|---|---|---|
| `uv sync`, `uv run pytest`, `uv run eng-gate check` | the workspace root and `tools/eng-dev-gate` | yes |
| `uv run --script spikes/S-02-.../s02_run.py`, same for S-04 (spikes: small test scripts, see 'Spike' above) | [spikes/](spikes/) | yes |
| `eng-harness doctor` | [spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.9, [spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.2.1 | the command exists; it answers "not available in this build" (exit 2) |
| Record mode | [spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.8 | no |
| `eng-harness run`, `resume`, `status`, `stop`, `report` | spec 0006 | the command exists (parser, configuration, exit codes); each answers "not available in this build" (exit 2) |
| The workflow `model_edit_cycle` | [spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) | no |

---

## 1. Prerequisites on Windows

### 1.1 Why everything runs from a normal terminal

Windows gives every program an **integrity level**. A normal program runs at the standard (medium) level. A
program started with "Run as administrator" runs higher. Some sandboxed programs run lower.

The rule of this project ([design/docs/architecture/16-security-safety-privacy.md](design/docs/architecture/16-security-safety-privacy.md)
§6): the MCP servers and the host programs they drive must run at the **same** integrity level, normally your
standard level. The harness starts the servers itself, and a server inherits the level of the program that started it
([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.3.2). Nothing raises or lowers it.
In the past, a low-integrity process could not drive host programs reliably
([design/docs/architecture/01-vision-and-principles.md](design/docs/architecture/01-vision-and-principles.md)).

So:

1. Open a **normal** PowerShell window from the Start menu. Do **not** choose "Run as administrator".
2. Do not start ETABS, SAFE, SAP2000, Revit or IDEA StatiCa as administrator either.
3. Do not run the commands from a sandboxed or restricted shell.
4. Never change Windows security settings, folder permissions (ACLs), file ownership or integrity levels to make a
   step work. If a step fails with "access denied", stop and report it (section 6). The design records that such
   changes broke host plug-in loading before ([16](design/docs/architecture/16-security-safety-privacy.md) §6).

`eng-harness doctor` (3.2) prints a warning when its own level is not medium
([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.9).

### 1.2 What you need

| Item | Notes |
|---|---|
| Windows machine with the host programs you will test | ETABS is needed for sections 2, 4 and 5. SAFE, SAP2000, Revit and IDEA StatiCa are only needed for section 7 items. |
| A copy of this repository on branch `build/v1` | Called `C:\path\to\Eng-Agent` below (replace it with the real folder path; keep the quotation marks in the commands even if the path has no space). Keep it on a normal local drive. |
| uv | See 1.3. |
| Python 3.14 | uv installs it. See 1.3. |
| The Sasaah server builds | See 1.4. |
| An ETABS model copy you can lose | Never your only copy. The spikes copy it themselves; the harness works on copies in the run folder. |
| `harness.toml` | See 3.1. Only the harness needs it; the two spike scripts do not. |

### 1.3 Install uv and Python 3.14

1. In a normal PowerShell window (1.1), not "Run as administrator", open <https://docs.astral.sh/uv/> (the same link as
   [README.md](README.md), Quick start, step 1). Find its installation instructions for Windows and follow the
   standalone installer method there. This guide does not copy the install command, because the uv documentation
   owns it and may change. What you should see: a message from the installer saying uv was installed. If the
   installer asks for administrator rights, or asks you to change a Windows security setting, stop, do not continue,
   and report it to the lead engineer (section 6).
2. Close the PowerShell window and open a new normal one.
3. Check uv is found:

   ```powershell
   uv --version
   ```

   What you should see: a version number. If you see "not recognized", uv is not on your PATH; report it.
4. Go to your copy of the repository and install everything:

   ```powershell
   cd "C:\path\to\Eng-Agent"
   uv sync
   ```

   uv installs Python 3.14 as pinned in [.python-version](.python-version) and
   [pyproject.toml](pyproject.toml) ([ADR-0028](design/docs/adr/0028-build-v1-in-this-repository.md) §5). Never use
   pip, poetry, conda or a hand-made virtual environment.

   What you should see: the first time, uv downloads Python 3.14 and the packages, then ends without a red "error"
   line. If it fails, report it as described in [section 6](#6-how-to-report-a-failure-back-to-an-agent), with the
   last lines of the output.
5. Optional smoke test of the repository itself:

   ```powershell
   uv run pytest
   ```

   What you should see: a last line such as "N passed, M skipped" and no "failed" or "error". Skipped tests are
   normal at this stage: tests marked `windows` or `recorded` are skipped with a reason until their environment or
   the host recordings exist (see section 4), and a skip is not a pass. Nothing in this guide records that the suite
   has passed. Any "failed" or "error" is a repository problem, not a host problem; report it as described in
   [section 6](#6-how-to-report-a-failure-back-to-an-agent).

### 1.4 The Sasaah server builds and their paths

The servers come from the Sasaah repository, built by you. How to build them is described in the Sasaah repository,
not here (see [Open points](#open-points), item 3). You need:

| Server | Used for | Needed from section |
|---|---|---|
| `sasaah-csi-mcp.exe` | ETABS (also SAFE and SAP2000) | 2 onward |
| `sasaah-revit-mcp.exe` | Revit | section 7 only |
| `sasaah-idea-mcp.exe` | IDEA StatiCa | section 7 only |

Rules:

1. Use the Sasaah commit that the project pins. The harness refuses a build that does not match its pin. Spike S-12
   read the sources at one commit, named in the header of
   [spikes/S-12-sasaah-tool-inventory/REPORT.md](spikes/S-12-sasaah-tool-inventory/REPORT.md). The harness adapter
   allowlist will hold the tested commit ([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md)
   §4.3.4).
2. The phase 0 exit needs a Sasaah build in which **design runs and design-result reads work**
   ([19](design/docs/architecture/19-roadmap-and-spikes.md) §1). Note the commit you built.
3. Write down the full path of each `.exe`. Use a placeholder like `C:\path\to\Sasaah\build\sasaah-csi-mcp.exe` in
   anything you send to an agent if the real path has your user name.
4. The harness needs the SHA-256 hash of each `.exe` for its pin. Print it in PowerShell:

   ```powershell
   (Get-FileHash -Algorithm SHA256 "C:\path\to\sasaah-csi-mcp.exe").Hash
   ```

   What you should see: a single line holding only the hash (64 characters, 0-9 and A-F, matching the `<64 hex>` (the `exe_sha256` field of the [spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.2 example) in
   `harness.toml`), with no table and no file path. Copy that whole line into `exe_sha256` in `harness.toml` (3.1).
   If PowerShell says it cannot find the path, the path is wrong: check it in File Explorer and try again.
5. The harness always starts the CSI server with `--disable-script`. It refuses any option that enables scripts, a
   generic invoke, attached writes or read-only mode ([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md)
   §4.2 rule 3). Do not add such options.
6. Close any ETABS window you care about before sections 2, 4 and 5. Two servers never drive the same host instance.

---

## 2. Spikes S-02 and S-04

Both scripts are in the repository now and do not need the harness. Each works on a **copy** of your model, never on
the original, and never clicks a dialog. They start ETABS themselves. Nothing here is a result until you run it.

Common preparation:

1. Normal PowerShell (1.1). Close ETABS.
2. Choose a scratch folder **outside** the repository, for example `C:\path\to\scratch`. The scripts write a
   `spike-runs\` folder in the folder you run them from, so run folders are never committed.
3. Have ready: the path of your model `C:\path\to\model.EDB`, the path of `sasaah-csi-mcp.exe`, and `C:\path\to\Eng-Agent`.
4. The first run of a script downloads the MCP library it lists in its header, so the machine needs internet access
   to the Python package index at that moment.

### 2.1 Spike S-02: analysis and design

Question: how long analysis and design take through the server; what a short call timeout does (the evidence for
`TIMEOUT_UNKNOWN_OUTCOME`); whether saving first avoids a save dialog; whether dialogs are detected; whether the
model is locked after analysis and the unlock step works. Source:
[spikes/S-02-analysis-design/README.md](spikes/S-02-analysis-design/README.md).

**Your model needs** load cases, combinations and a design setup, so that analysis and design can run. Use a
mid-sized model you know and note its size (stories, frames).

1. Go to the scratch folder:

   ```powershell
   cd "C:\path\to\scratch"
   ```

2. Check the plan without starting anything:

   ```powershell
   uv run --script "C:\path\to\Eng-Agent\spikes\S-02-analysis-design\s02_run.py" --model "C:\path\to\model.EDB" --server-exe "C:\path\to\sasaah-csi-mcp.exe" --dry-run
   ```

   What you should see: a list of what would be called, and both files shown as `found`. Nothing is written.

   If a file shows `NOT FOUND` (or the script stops with `error: model file not found` or `error: server executable not found`), the path in that option is wrong. In File Explorer, select the file, then hold Shift and right-click it (on Windows 11, a plain right-click also works) and choose "Copy as path". Paste it in place of the placeholder after the option name, replacing the old path and keeping the quotes. Then run the dry-run again. Do not go on to the real run until both files show `found`.
3. Run it for real (ETABS must be closed):

   ```powershell
   uv run --script "C:\path\to\Eng-Agent\spikes\S-02-analysis-design\s02_run.py" --model "C:\path\to\model.EDB" --server-exe "C:\path\to\sasaah-csi-mcp.exe"
   ```

   Options you may want: `--runs` (more runs), `--design-kind steel` (default is concrete), `--timeout-tests
   analysis,design` (also test a design timeout), `--short-timeout-sec`, `--probe-unsaved`, `--skip-design`. Run it
   with `--help` for all of them.
4. Wait. ETABS opens visibly. **Do not touch the ETABS window.** If a dialog appears and the script seems stuck,
   dismiss it by hand and write down what it said and when.
5. At the end the script prints a summary and the two files to send back, in `spike-runs\S-02-<time>\`:
   `record.json` and `summary.md`.
6. Optional second run with `--probe-unsaved`: it runs one analysis without saving first, to see whether a dialog
   appears. Dismiss any dialog by hand.

In `summary.md`, check:

- **Run times:** analysis, design and save (minimum, median, maximum).
- **Locked after analysis:** `True`. The write probe must show `model_locked`, and after the unlock step it must work.
- **Short timeout:** the code and message returned, how long it took, whether the model is locked afterwards, and
  whether the units are the same as before.
- **Dialogs seen:** title and phase. "None seen" means something only if the summary says dialog detection was
  available.
- **Original model unchanged:** `True`.

Before you send the files: open `summary.md` and `record.json` and remove any client or project name (ETABS messages
and dialog titles can carry them).

If it fails, paste into the chat: the command, the last lines printed, at least down to the first error (or the "Errors" section of `summary.md`),
`server-main.stderr.log` from the run folder, and what you saw in ETABS. A run that stops part-way still writes both
files. If ETABS is left open, close it by hand; the copy in `model-copy\` can be deleted.

The numbers from this spike are what you put into `harness.toml` as the timeouts (3.1, which comes later in this guide). Which number goes into which
key is your decision; the documents do not define a formula (Open points, item 2).

### 2.2 Spike S-04: reading the model state

Question: how fast and reliably the model state can be read; whether a fingerprint over it is the same when the same
model is read twice; whether it catches edits made by hand in ETABS; whether a model identity can be stamped and read
back. Source: [spikes/S-04-model-state/README.md](spikes/S-04-model-state/README.md).

**Your model needs** frames, areas (slab or wall), load patterns and a restraint or two. A model of the size you
really work with is best.

1. Go to the scratch folder (`cd "C:\path\to\scratch"`).
2. Check the plan:

   ```powershell
   uv run --script "C:\path\to\Eng-Agent\spikes\S-04-model-state\s04_run.py" --model "C:\path\to\model.EDB" --server-exe "C:\path\to\sasaah-csi-mcp.exe" --dry-run
   ```

   What you should see: every read, and the hand edits you will be asked to make. The plan also shows the model file
   and the server executable as `found`. If a file shows `NOT FOUND` (or the script stops with `error: model file not found` or `error: server executable not found`), the path in that option is wrong. In File Explorer, select the file, then hold Shift and right-click it (on Windows 11, a plain right-click also works) and choose "Copy as path". Paste it in place of the placeholder after the option name, replacing the old path and keeping the quotes. Then run the dry-run again. Do not go on to the real run until both files show `found`.
3. Close ETABS. Run it for real:

   ```powershell
   uv run --script "C:\path\to\Eng-Agent\spikes\S-04-model-state\s04_run.py" --model "C:\path\to\model.EDB" --server-exe "C:\path\to\sasaah-csi-mcp.exe"
   ```

   Options: `--repeats` (more baseline reads), `--limit` (if the summary reports truncated reads), `--skip-edits`,
   `--skip-reopen`, `--help`.
4. ETABS opens with the copy. The script reads the model several times, then **stops** and prints a numbered list of
   edits E1 to E10 and an identity text.
5. In the ETABS window, on the copy only, make as many of the edits as you can. Make **one small change per edit**,
   as listed. For E10, open Project Information (File menu) and type the printed identity text into the Project
   Number field. Do **not** save, run analysis or close ETABS. Skipping edits is fine.
6. Go back to the terminal and press Enter. The script reads again, prints the differences it sees, then asks `Did
   you make E1 ...? [y/N]` for each edit. Answer honestly: this is how it tells "not noticed" from "not made".
7. The script saves the copy, reopens it, reads once more, exits ETABS and prints the two files to send back, in
   `spike-runs\S-04-<time>\`: `record.json` and `summary.md`.

In `summary.md`, check:

- **Time to read the model state:** one full pass and the slowest reads.
- **Stability:** "Same fingerprint every time" should be `True`. If only the "order included" value is `False`, the
  server returns the same content in a different order. Sections listed as differing are unstable: note them.
- **Failed reads:** in the "Time to read the model state" table, a read whose `ok` column shows `False` (next to its error code) failed, for example a table name this ETABS version does not know. Report each one; they are findings.
- **Edits made by hand:** which edits were noticed. A "NOT noticed" edit is a blind spot: the harness would miss
  such a manual edit.
- **Identity:** no tool can write project information (known gap S12-G6), so you write the stamp. Check "read back
  after the edit" and "after save and reopen".
- **Save and reopen:** whether the fingerprint stays the same.
- **Original model unchanged:** `True`.

Before you send the files: check that `summary.md` and `record.json` hold no client or project name. Object names,
section names and messages come from your model.

If it fails, paste: the command, the last lines, at least down to the first error (or the "Errors" section), `server-main.stderr.log`, and what
ETABS showed. If ETABS stays open, close it by hand and do not save.

Fingerprint settings in the script (units token, rounding) are spike settings, not engineering values.

### 2.3 Other spikes you may run on this machine

These are not required for the edit cycle. See section 7 for the full list: S-10 (the Windows checks and journal
speed, [report](spikes/S-10-replay/REPORT.md)), S-12 (compare the live tool list with the inventory, [report](spikes/S-12-sasaah-tool-inventory/REPORT.md)),
S-05 Revit ([spec 0011](packages/eng-harness/docs/specs/0011-revit-adapter.md) §12), S-07 Jev ([spec 0009](packages/eng-harness/docs/specs/0009-providers.md)),
S-08 IDEA ([spec 0014](packages/eng-harness/docs/specs/0014-idea-adapter.md) §12).

---

## 3. The harness settings and the environment check

*(Everything in this section is used by `eng-harness`. The `eng-harness` command exists on `build/v1` (plan 0006 task T3), but every command answers "not available in this build" until its task has merged. Nothing here is needed for section 2.)*

### 3.1 The workspace and `harness.toml`

**The workspace** is the folder where runs, results and settings are stored. By default it is
`%LOCALAPPDATA%\eng\workspaces\default`. In PowerShell this folder is written `$env:LOCALAPPDATA\eng\workspaces\default`;
to open it in File Explorer, run `explorer "$env:LOCALAPPDATA\eng\workspaces\default"`. To use another folder for
the current PowerShell window only, run `$env:ENG_WORKSPACE = "C:\path\to\workspace"`. This setting is forgotten
when you close the window, so run it again in every new window, or pass `--workspace C:\path\to\workspace` to the
command instead ([spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.2.1,
[eng-contract spec](packages/eng-contract/docs/specs/0001-eng-contract-0.1.md) §4.5.1).

The workspace must be on a **local drive**. The harness refuses a OneDrive folder, a mapped network drive or a UNC
path. The report on the journal speed also warns against a synchronized folder
([spikes/S-10-replay/REPORT.md](spikes/S-10-replay/REPORT.md), Open risks).

**Where `harness.toml` is found**, in this order: the `--config` option, the `ENG_HARNESS_CONFIG` variable, then
`<workspace>\harness.toml` ([spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.2.4).

The example below is the one from [spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.2
with placeholders. A value in angle brackets is for you to fill in. A value you must decide is marked "yours".

```toml
[servers.csi]
adapter = "sasaah-csi-mcp"
command = "C:\\path\\to\\sasaah-csi-mcp.exe"
args = ["--disable-script"]
env = {}
toolsets = []
client_grace_s = <yours>
build = { sasaah_commit = "<40 hex: the commit you built>", exe_sha256 = "<64 hex: from Get-FileHash>" }
host_key = "csi"
mcp_mode = "legacy"

[servers.csi.roles.main]
classes = ["session", "call"]
call_timeout_s = <yours>

[servers.csi.roles.long]
classes = ["long"]
call_timeout_s = <yours>

[host_programs.etabs]
executables = ["ETABS.exe"]
install_dirs = ["C:\\path\\to\\ETABS install folder"]
```

Things to know:

- **No timeout has a default.** `client_grace_s` and every role's `call_timeout_s` are required. The harness refuses
  to load the file without them. They are meant to be sized from spike S-02 (section 2.1, which comes first in this guide). Which provisional values to use for the
  first `doctor` run before S-02 has produced numbers is not defined yet (Open points, item 2). Whatever you choose
  is your decision: write it down as provisional and replace it after S-02.
- All paths are absolute. The file holds no secrets.
- `max_restarts_per_run` and `shutdown_grace_s` are software settings that have defaults; leave them out.
- Other sections ([engine], [progress], [page], [providers.*], [servers.csi_safe], [servers.revit], [servers.idea])
  are described in [spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.2.4,
  [spec 0008](packages/eng-harness/docs/specs/0008-safe-adapter.md), [spec 0011](packages/eng-harness/docs/specs/0011-revit-adapter.md),
  [spec 0014](packages/eng-harness/docs/specs/0014-idea-adapter.md) and [spec 0009](packages/eng-harness/docs/specs/0009-providers.md).
  You need none of them for the model edit cycle on ETABS.

### 3.2 The environment check (`doctor`)

*(Available once eng-harness plan 0002 task T18 and plan 0006 task T16 have merged; check BUILD-STATUS.md.
The `eng-harness` command exists on `build/v1` (plan 0006 task T3), but `doctor` answers "command doctor is not available in this build" with exit code 2 until then.)*

`doctor` checks that the machine is ready. It changes nothing. Per [spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md)
§4.9 it reports one line per check, each `ok`, `warn`, `fail` or `skip`:

| Check | What it looks at |
|---|---|
| uv and Python | `uv` is on the PATH; the interpreter is CPython 3.14 |
| Server executables and hashes | each `.exe` exists and its SHA-256 equals the pin in `harness.toml` |
| Tool-list fingerprints | starts each server briefly and compares its tool list with the tested list. It launches no host program. It asks only for the tool list and `csi_status` |
| Installed host programs | the declared `install_dirs` and the products `csi_status` reports |
| Integrity level | warns when the terminal is not at the standard (medium) level |
| Workspace | fails unless the workspace is on a local drive |
| Timeouts | warns when only one server role serves everything; prints your values next to the Sasaah default |
| Lock directory | writable; lists stale lock files (information only) |
| Unreleased tools | warns about any tool that is not yet released, with its record |
| Page and console (spec 0006) | the approval page can bind to `127.0.0.1`, a browser can be opened, console encoding, locale and calendar |

Steps:

1. Open a normal PowerShell window (1.1).
2. Go to the repository:

   ```powershell
   cd "C:\path\to\Eng-Agent"
   ```

3. Run the check:

   ```powershell
   uv run --package eng-harness eng-harness doctor
   ```

   (Why this form is used: see Open points, item 6.)
4. Read the table. For the machine-readable form, and to see full paths, the options are `--json` and
   `--show-paths`. By default paths are shown as file names only, which is what you want when pasting to an agent.
5. The exit code is 0 when no check is `fail`, and 1 otherwise ([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.9; [spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.2.3). To see it:

   ```powershell
   $LASTEXITCODE
   ```

What you should see: every check `ok`, except that warnings for a single server role (if you configured one) and for
unreleased tools may appear. Reasons a `fail` is expected the first time, and what to do:

- **Fingerprint differs.** The tested tool list in the allowlist was derived from reading the Sasaah sources, not from
  a live server ([spikes/S-12 REPORT](spikes/S-12-sasaah-tool-inventory/REPORT.md); [spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md)
  §12 item 3). A difference is a finding. Send the doctor output (section 6). Do not edit the pin yourself.
- **Hash differs.** The `.exe` is not the build the pin names. Rebuild the pinned commit, or report.
- **Integrity warning.** You are not at the standard level. Close the window and open a normal one (1.1).
- **Workspace fails.** Move the workspace to a local drive (3.1).

v1 detects installed programs from the declared `install_dirs` and the products `csi_status` reports; it does not read
the Windows registry ([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.9, gap H-G6, not
needed while `csi_status` lists installed products). A program installed outside `install_dirs` and not reported by
`csi_status` may show as missing; add its folder to `install_dirs`.

---

## 4. Record mode

**A fixture** is a saved file that a test uses as its input instead of a live program. **Record mode** makes the
harness save every real server reply into fixture files while you do a normal live run. The tests then run against
those fixtures, so the fakes used in CI are checked against what the real servers really said
([ADR-0028](design/docs/adr/0028-build-v1-in-this-repository.md) Pre-mortem: fakes built from tool schemas may behave
differently from the real servers; [process/05](design/process/05-testing-and-verification.md) §4).

*(Available once eng-harness plan 0002 task T17 has merged; check BUILD-STATUS.md. The switch name in
`harness.toml` and the options of the record script are not defined yet, Open points, item 1.)*

What record mode writes ([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.8.1):

- One file per request and reply (`tools/list`, `tools/call` and the `initialize` result) under
  `acceptance/recordings/<adapter>-<build>/`.
- A `manifest.json` with the SHA-256 of every file, the adapter, the build, the tool-list fingerprint and the
  harness version.
- Cleaning on the way in: model and file names become placeholders such as `<model-1>.EDB`; your user name and home
  folder become `<user>` and `<home>`; reads of Project Information are dropped. The mapping from placeholder to real
  name stays only in the run folder, never in a recording.
- Cleaning cannot catch names inside free text (host messages, object names). **You review the files before they are
  committed.**

Steps:

1. Do a normal pass of 3.2 (`doctor`) first, so the build and fingerprint are known.
2. Use a **copy** of a model you are allowed to share in anonymised form. Recordings go into the repository
   history; real project data is never committed ([process/05](design/process/05-testing-and-verification.md) §3).
3. Run the record script for the CSI server, `record_csi.py`
   ([plan 0002](packages/eng-harness/docs/plans/0002-servers-and-adapters.md) task T17 creates it under
   `packages/eng-harness/acceptance/scripts/`). Its options are not defined yet. Run it from a normal terminal.
   Revit and IDEA have their own record scripts under `packages/eng-harness/acceptance/scripts/`: `record_revit.py`
   (available once [plan 0011](packages/eng-harness/docs/plans/0011-revit-adapter.md) task T13 has merged) and
   `record_idea.py` (available once [plan 0014](packages/eng-harness/docs/plans/0014-idea-adapter.md) task T9 has
   merged). Check `BUILD-STATUS.md` for whether each has merged.
4. Open the new folder and the files in it. Search them for any client name, project name, address, person name or
   path. Replace what you find with a neutral placeholder. If you edit a file, the manifest hash no longer matches:
   say so to the agent rather than editing the manifest.
5. Verify the manifest. How to run the verification is not defined yet beyond the unit test
   `test_sanitized_and_manifest` ([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) AC33).
6. The recordings go into the repository history, and `acceptance/recordings/` is a protected path (see
   [.github/CODEOWNERS](.github/CODEOWNERS); recordings are described in
   [process/05](design/process/05-testing-and-verification.md) §4). How you commit them is not defined yet (Open
   points, item 12). Do not improvise: leave the reviewed folder where the record script wrote it, do not delete it,
   and tell the agent the folder name. The agent will state the committing procedure that the repository documents
   and ask you before anything is committed. Tell the agent when the recordings are in the repository.

Then run the tests again on the recordings:

```powershell
cd "C:\path\to\Eng-Agent"
uv run pytest -m recorded
```

What you should see: the contract tests `test_adapter_on_recordings` and `test_synthetic_matches_recordings` pass
([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) AC34). Before recordings exist these
tests are skipped with a reason; a skip is not a pass.

If a test fails: the synthetic fake disagrees with the real server. The rule is that the fake is wrong, and it is
fixed before anything depends on it ([process/05](design/process/05-testing-and-verification.md) §4). Send the test
name and its output to the agent (section 6). Once a recording exists for a build, the allowlist's fingerprint
becomes the recorded one ([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.8.2).

---

## 5. Acceptance A1 to A7 of the model edit cycle

The criteria are in [design/docs/architecture/18-first-slice-dxf-to-etabs.md](design/docs/architecture/18-first-slice-dxf-to-etabs.md)
§5. The workflow in your terms is [packages/eng-harness/docs/workflows/model-edit-cycle.md](packages/eng-harness/docs/workflows/model-edit-cycle.md);
how it is built is [spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md).

*(Everything in this section needs eng-harness plans 0001 to 0007 and 0009 merged; check BUILD-STATUS.md. In
particular: `run`, `resume` (plan 0006 task T14, B-188), basis confirmation (T15), `status`, `stop`, `report` (T16),
the blank template (plan 0004 T9), the workflow itself (plan 0007 tasks T8 and T9), and its report timings,
prompt count, value-source audit and `report\cycle-timings.json` (plan 0007 task T10). None of it is on `build/v1`
yet.)*

CI already tests the workflow against a fake server. What only you can show is behaviour on real ETABS, plus the
time gate A4. If A4 is not met, no release is made until the cause is found ([18](design/docs/architecture/18-first-slice-dxf-to-etabs.md) §5).

### 5.1 Before you start

1. Sections 1 and 3 done; `doctor` (3.2) has no `fail`.
2. Spike S-02 done (2.1), and the timeouts in `harness.toml` are your values from it (3.1).
3. **Benchmark B-1** prepared by you: three past projects ([18](design/docs/architecture/18-first-slice-dxf-to-etabs.md) §5), each with its ETABS model, five to ten typical change
   requests from the real work, and the time those changes took by hand and, where recorded, in agent chats. The
   sheet layout is yours; the documents do not define one. The workflow records its own times so the same requests
   can be compared (spec 0007 §4.9).
4. Work on **copies** of the models. The run writes only to copies in the run folder. The original changes only at
   step 16 (promotion), which asks you first, backs up the original, and stops if the original changed. Even so, use
   files you can replace.
5. A **design basis values file**. The blank template ships **no engineering values**
   ([spec 0004](packages/eng-harness/docs/specs/0004-templates-and-basis.md) §4.8). You supply every value from your
   own project criteria and keep its source in your own records. The values file does not hold a source: the source
   `engineer:<name>@<time>` is recorded when you confirm the values on the page ([spec 0004](packages/eng-harness/docs/specs/0004-templates-and-basis.md)
   §4.4 and §4.6). This guide gives no values. The fields to supply (all required, from
   [spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) §4.8):

   | Group | Fields |
   |---|---|
   | Comparison tolerances | `compare.length`, `compare.angle`, `compare.stress`, `compare.unit_weight`, `compare.line_load`, `compare.area_load`, `compare.ratio` |
   | Read-back | `checks.readback_relative_tolerance` |
   | Report | `report.top_n` |
   | Limits | `limits.ratio_limit`, `limits.drift_ratio` |
   | Change-set bounds | `bounds.thickness_min`, `bounds.thickness_max`, `bounds.line_load_min`, `bounds.line_load_max`, `bounds.area_load_min`, `bounds.area_load_max`, `bounds.ratio_min`, `bounds.ratio_max` |
   | Design | `design.run` (`steel`, `concrete` or `steel_and_concrete`) |
   | Attempts | `attempts.cycles`, `attempts.change_set`, `attempts.approval_void` |

   The file is YAML or JSON with the members `engineer` (the name the page proposes) and `values` (per path, a
   `value` and a `unit`) ([spec 0004](packages/eng-harness/docs/specs/0004-templates-and-basis.md) §4.4, §5). The
   file cannot mark anything confirmed; you confirm on the page. If a value has no source you can cite, stop and ask.
6. An **input file** `input.json` for the run. Its members are `model` (the model file) and `visible_host` (true by
   default: ETABS opens visibly so you can edit by hand). How `model` is written in the JSON is not defined yet (Open
   points, item 4).
7. Run class. The six calcs ship as `draft` until you approve them
   ([spec 0003](packages/eng-harness/docs/specs/0003-calcs.md) Q10). The default run class `production` refuses draft
   calcs ([spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) Q7). For these acceptance
   runs use `--run-class trial`; the results are marked draft. That is your decision to confirm (Open points, item 10).

### 5.2 One cycle, step by step

Use a normal PowerShell window in `C:\path\to\Eng-Agent`.

1. Start the run:

   ```powershell
   uv run --package eng-harness eng-harness run model_edit_cycle --input C:\path\to\input.json --template blank --basis C:\path\to\basis.yaml --run-class trial --answers C:\path\to\change-set.json
   ```

   Options defined for `run` ([spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.2.1):
   `--mode {work_on_copy, approve_each_write, autonomous_logged}` (default `work_on_copy`), `--answers FILE`,
   `--no-wait`, `--wait-timeout`, `--no-browser`, `--progress`, `--json`, `--no-report`. `blank` is the one template
   that ships. `--answers` gives the run your change set for its first change-set request (step 5), so prepare
   `change-set.json` before you start; a file that is missing, not valid JSON or not one JSON object stops the command
   with exit 2 before any run folder exists ([spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) AC64).
   Do not use `--no-wait` for this workflow: a workflow that confirms a basis is started only by a waiting `run`, and
   with `--no-wait` it exits 10 and stores nothing (spec 0006 §4.4.7, AC47; decided by amendment B-354).
2. The **basis confirmation page** opens in your browser (or, with `--no-browser`, the address is printed to this
   terminal only). Check each section's values, units, sources and bounds. Tick each section, enter your name and
   confirm. The page does not let you edit values; edit the values file and run again if something is wrong.
   Rejecting needs a reason and ends the run before it starts (exit 3, no run folder).
3. The terminal shows progress. Steps 1 and 2 of the workflow run once: the server builds and tool lists are
   checked, then a working copy of your model is saved into the run folder. Note the **run id** printed (it starts
   with `run_`).
   What you should see: if a build or tool list differs from the pin, the run stops before any write with a server
   check failure (exit 3, `SERVER_CHECK_FAILED`, [spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.2.3).
4. Steps 3 and 4 read the model and compare it with the last recorded revision. Differences are your own changes;
   they are shown and recorded, never overwritten.
5. Step 5 asks for the **change set**. This is a data request. The first one of the run is answered from the file you
   gave with `--answers`, and no page is shown for it; if the file fails the request's checks, the request is shown
   again on the page (spec 0006 AC64). Prepare `change-set.json` before step 1. Its shape ([spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md)
   §4.3.1) is `{"change_set": {"items": [...], "note": "...", "benchmark_request": "<B-1 request id>"}}`. Each item
   has a unique `id` and a `kind`. The kinds in v1 are `frame_section`, `area_section`, `wall_section`,
   `frame_uniform_load`, `area_uniform_load`, `load_pattern_add`, `load_combination_set`, `load_combination_delete`
   and `joint_restraints`. A value is either `{"source": "basis", "path": "<basis path>"}` or `{"source": "input",
   "value": <number>, "unit": "<unit>"}` with a unit of the right kind (length `mm`, line load `kN/m`, area load
   `kPa`, ratio `1`). Example of one item, with your own names:

   ```json
   {
     "change_set": {
       "items": [
         {"id": "item-1", "kind": "frame_section", "frames": ["<frame name>"], "section": "<section name>"}
       ],
       "benchmark_request": "<your B-1 request label>"
     }
   }
   ```

   Edit kinds **not** in v1 are refused with a gap id: changing a slab thickness, defining a frame or area section
   or a material, point loads and non-gravity directions, changing or deleting a load pattern, seismic parameters
   ([workflow page](packages/eng-harness/docs/workflows/model-edit-cycle.md) §3.1). A B-1 request that needs one of
   them cannot be run through the harness yet; note it as a finding.
6. **Later change sets.** A change set that is asked again (a re-ask, or the next cycle after *more edits*) is never
   taken from the `--answers` file (spec 0006 AC64). The page shows that request read-only and tells you to give it
   with `resume --answers FILE` after the run has paused at the request
   ([spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) §4.3.1; [spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md)
   §4.2.1). How a waiting run is paused for that is not spelled out yet (Open points, item 5). The command is:

   ```powershell
   uv run --package eng-harness eng-harness resume <run_id> --answers C:\path\to\change-set.json
   ```

   `status <run_id>` shows where the run is and prints the next command to run. `status` never changes anything.

7. Step 6, the **change-set approval page**. It shows the items, the differences from the last revision, the model
   state the approval is bound to, and a reject box per item. Approve, reject single items, or reject with a reason.
   Only you can approve; there is no command that approves ([spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md)
   §4.2.1). The approval is single use and ends at the first check of the model after the writes.
8. Steps 7 to 10: the revision is saved as a snapshot, the edits are applied, every written value is read back and
   checked, and the model is saved. If the model changed since your approval, the cycle goes back to step 3 and asks
   again. If a read-back check fails, one screen asks you to continue, restore the revision from step 7, or stop the cycle (this skips to the engineer turn of the same cycle and does not end the run).
9. Steps 11 and 12: analysis and design run on the long-call server. A timeout is not a failure. It is an unknown
   outcome: the run stops and the engine screen asks you whether it was applied, not applied, or to abandon. In v1
   the outcome of an analysis or design that timed out is always yours to decide, because nothing yet proves that
   the abandoned run ended ([workflow page](packages/eng-harness/docs/workflows/model-edit-cycle.md) §5, D-4).
10. Steps 13 and 14: results are read and summarised. Known limits to expect, so you can tell them from defects:
    concrete design results have no single ratio, so verdicts are `NEEDS_ENGINEER` (gap EC-G2); every analysis
    message is `unclassified` until a local test shows the table's columns, so an analysis with messages asks you
    each cycle (gap EC-G3; [spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) §11).
11. Step 15, the **engineer turn**: three buttons. *Accept this revision*, *ask for more edits*, or *I edited by
    hand: continue*. For the last, save in ETABS first. A new cycle then starts at step 3 with an empty change set,
    and your hand edits are recorded as a revision.
12. Steps 16 and 17: promotion (the accepted revision is copied over the original after a backup; always asked) and
    sign-off on the page. Outputs stay `DRAFT` until signed, and keep "DRAFT SOURCES" while calcs and rules are draft.
13. Build the report:

    ```powershell
    uv run --package eng-harness eng-harness report <run_id>
    ```

    It writes `report\report.html` in the run folder and `report\cycle-timings.json` (file names only, for your B-1
    sheet; [spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) §4.9). Open the report in the browser.

The run folder is `<workspace>\runs\<run_id>\`. It holds `journal.sqlite` (the record of every step), `copies\`
(working copies and snapshots), `backups\`, and `servers\` (server logs).

### 5.3 The seven criteria

For each, run the B-1 requests as in 5.2, and keep the run ids.

**A1. After each B-1 request, the model holds exactly the requested changes and nothing else, checked by the difference report against the change set.**
For each B-1 request, after step 9 check the read-back result and the difference report against the change set.
Pass means no value differs and nothing else changed. Also compare in ETABS by eye on a few items. If something
else changed, report the run id and the item. Real-ETABS read-back (unit scale, frame load directions, table reads)
is listed in section 7 ([spec 0003](packages/eng-harness/docs/specs/0003-calcs.md) L-2).

**A2. Every analysis and design run completes, or ends as `TIMEOUT_UNKNOWN_OUTCOME` followed by reconciliation; no
run waits on a dialog; a stale server build is stopped before any write.**
Watch for dialogs in ETABS during steps 10 to 12 (the harness saves before analysis so none should appear). Write
down any. Check a stale build: use a `harness.toml` whose pin names a different build and confirm the run stops
before step 2 with a server check failure and the model untouched. Put the pin back afterwards.

**A3. The audit shows that every engineering value written came from a reference (change set, basis or step result), checked automatically.**
The audit is `audit_value_sources` ([spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) AC25). Run it
on a run folder with `uv run --package eng-harness python -m eng_harness.report audit-sources <run folder>` (spec 0007
AC35, amendment B-354; available once eng-harness plan 0007 task T11 has merged; check BUILD-STATUS.md). It only
reads. The automatic check reports any write step argument at an engineering parameter that is not a reference to
`basis.design_basis/1` or `basis.engineer_input/1`. What you can check by hand: in the report, every value cell names
its source.

**A4. Median time from request to accepted revision, engineer time included, is at most 50% of the B-1 time for the same changes.**
The time is measured only by you, locally. For each B-1 request, take the time from `report\cycle-timings.json`
(first change-set request to the accept decision, with the cycles it took). Compare with your hand time. The median
over the requests is the figure. Both the 50% and the "median" are from [18](design/docs/architecture/18-first-slice-dxf-to-etabs.md)
§5. If this fails, report it as a failure of the gate, with the per-step times.

**A5. A manual edit made between cycles always appears in the next cycle's differences and is never overwritten, tested by a hand edit in every B-1 project.**
In every B-1 project: at step 15 choose *I edited by hand*, or edit in the visible ETABS between cycles. Make one
small change by hand (for example a section on one frame) and save. In the next cycle, step 3 and 4 must list it in
the differences; after the cycle it must still be there. Edits that the read set does not see are blind spots
(S-04 reports them); report any change that did not appear.

**A6. A run interrupted at any step (process killed, or ETABS killed) resumes after the host-state check and ends with the same model as an uninterrupted run.**
Kill at least: the harness process during analysis, during apply and during promotion; and ETABS during a step. Kill
the harness process from Task Manager (End task); kill ETABS the same way. Then:

```powershell
uv run --package eng-harness eng-harness resume <run_id>
```

You answer the host-state or in-flight screen that appears. Pass means the run completes and no write is repeated.
To compare with an uninterrupted run, use the same starting copy and the same change-set file for both and compare
the final revision's fingerprint and file hash in the two reports. The documents do not define a local comparison
procedure (Open points, item 8). Promotion while the original is open in your own ETABS (a file lock) is a separate
check listed in section 7.

**A7. At most one engineer prompt per cycle, besides the change-set approval and the engineer turn.**
One batched screen counts as one. The report shows the prompt count per cycle (spec 0007 §4.9), and
`uv run --package eng-harness python -m eng_harness.report count-prompts <run folder>` prints it for a run folder
(spec 0007 AC35; available once plan 0007 task T11 has merged). A repeated approval,
a re-asked change set and every engine screen count. Failure paths (a timeout, a void approval, a read-back failure)
are counted and shown but are not what the bound measures; it applies to normal paths. Be aware that while every
analysis message is `unclassified` (EC-G3), a cycle with analysis messages asks you once, which uses the prompt
([spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) Q10). Note this separately when you report A7.

### 5.4 After the runs

Keep, per run: the run id, the report, `cycle-timings.json`, and your notes on dialogs and anything odd. The live
acceptance record is meant to be written by the acceptance script itself
([process/05](design/process/05-testing-and-verification.md) §6, [template](design/process/templates/acceptance-record.md)).
No script for A1 to A7 is defined yet (Open points, item 9). Until it exists, send your notes to the agent
(section 6); do not write the record by hand.

---

## 6. How to report a failure back to an agent

Agents work from what you paste into the chat. They do not run host programs, never see your screen, and cannot
approve anything for you ([design/process/08-agent-operating-rules.md](design/process/08-agent-operating-rules.md)
§1, A19). Give them evidence, not a summary.

Paste, in this order:

1. **What you were doing:** the section and step of this guide, and the exact command (with placeholders for folders
   that carry your user name).
2. **What you expected** (the "what you should see" line) and **what happened** (the exact text, not a paraphrase).
3. **The last lines** printed, at least down to the first error, in the terminal.
4. **Evidence files**, by the kind of run:
   - Spike: `summary.md` (the "Errors" section), `record.json`, and `server-main.stderr.log` from the run folder.
   - Doctor: the table, or the `--json` output.
   - Harness run: the run id; the output of `status <run_id> --json`; the exit code; the report; and the server logs
     in `<workspace>\runs\<run_id>\servers\` (`<server>-<role>.stderr.log` and the `-audit.jsonl` files).
     The `journal.sqlite` file holds the full record; send it only if the agent asks.
   - Anything with a host program: what ETABS showed (dialog text, whether it was still running, whether it was
     stuck), and the ETABS version and build.
5. **The exit code** if the command printed none: `$LASTEXITCODE` right after the command. The meanings are in
   [spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.2.3 (for example 2 usage error, 3 refused,
   4 run locked, 5 journal altered, 10 waiting for you, 12 stopped, 70 internal error).

Remove before you paste:

- Client names, project names, addresses, person names (model and object names can carry them).
- Your user name and home folder in paths. `doctor` and the reports already show file names only unless you ask for
  `--show-paths`.
- **The approval page's launch address and its code.** They are for you only. Never paste them, and never ask an
  agent to open the page or click on it ([spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.2.1).
- Any provider key. Keys are never put in files, logs or chat ([16](design/docs/architecture/16-security-safety-privacy.md) §3).

What you can expect back. Every agent session ends with one status ([08](design/process/08-agent-operating-rules.md) §6):

| Status | Meaning |
|---|---|
| `DONE` | Completed, with evidence linked (a CI run, a report) |
| `DONE_WITH_CONCERNS` | Completed; concerns listed with their risk |
| `BLOCKED` | Cannot continue; the blocker and what is needed |
| `NEEDS_CONTEXT` | Missing information; exactly what and from whom |

"Should work" is not evidence. If an agent says a fix works, it should show a CI run; the live check is still yours.

When the failure is a missing capability (a tool, an edit kind, a table key), the agent files a **gap report**
([process/02](design/process/02-work-items.md) §5, template [issue-gap.md](design/process/templates/issue-gap.md))
and reports `BLOCKED`. It does not write a one-off script or add a workaround. A wrong behaviour is a defect
([issue-bug.md](design/process/templates/issue-bug.md)). If a wrong number could have reached a model, say so: it is then
handled as a `type/bug` issue labeled `risk/r1-engineering` ([process/10](design/process/10-engineering-verification.md) §7).

---

## 7. Everything marked "needs local test", by package

Each package keeps its detailed list in its own `docs/local-testing.md`. All four exist now:
[packages/eng-contract/docs/local-testing.md](packages/eng-contract/docs/local-testing.md),
[tools/eng-dev-gate/docs/local-testing.md](tools/eng-dev-gate/docs/local-testing.md),
[packages/eng-harness/docs/local-testing.md](packages/eng-harness/docs/local-testing.md) and
[packages/structural-codes/docs/local-testing.md](packages/structural-codes/docs/local-testing.md). Where a package list does not cover a plan yet, the sources below are the specs and plans (Open points, item 11). If you find an
item in this list that is wrong or missing, tell the agent.

Marker: **[H]** needs a host program, **[N]** needs the network or a key only, **[M]** needs your machine only (disk,
antivirus, browser, language settings).

### 7.0 The two CI steps the build container could not run

GitHub Actions did not run for this repository from 2026-11-04 (billing: [BUILD-STATUS.md](BUILD-STATUS.md) OQ-A13), so
the build ran CI inside its container instead (BUILD-STATUS.md D-23). Each pull request shows that result in its "Local
CI" section. Two steps cannot run there. Run them on your machine before `build/v1` goes to `main`:

- [N] The dependency audit. From the repository folder, run `uv audit --locked`. What you should see: no known
  vulnerability reported. It needs the network: it asks the OSV vulnerability database (osv.dev), which the build
  container may not contact. If it reports a vulnerability, send its output to the agent.
- [M] The windows job. From the repository folder, run `uv sync --all-packages`, then `uv run eng-gate windows-tests`,
  then `uv run --script spikes/S-10-replay/windows_check.py` (the job's second step, the Windows spike checks). What you
  should see: each command ends without a failed test or case (exit code 0). `eng-gate windows-tests` runs the
  Windows-only tests of every package, the ones marked `windows`. A `SKIPPED` line from the spike script means it did
  not run on Windows: it is not a Windows result. If a test or case fails, report it as section 6 describes.
  For eng-harness the job currently stops with ST001 (`windows_tests path 'tests/perf' does not exist`) before running
  anything, and it never runs the run-lock test in `tests/unit`. Until that is fixed, run
  `uv run pytest tests/windows -m windows` and `uv run pytest tests/unit/test_journal_reader.py -m windows` from
  `packages/eng-harness` (7.3).

If GitHub Actions works again, you can instead re-run CI on the final `build/v1` on GitHub: the `windows` job runs on
pushes to `build/v1`.

### 7.1 eng-contract

Source: [packages/eng-contract/docs/local-testing.md](packages/eng-contract/docs/local-testing.md) (exists now).

- [M] The Windows workspace probe: `ENG_WORKSPACE` inside OneDrive (also a Files On-Demand folder) is refused; a
  mapped network drive or UNC path is refused; a fixed local drive resolves as local. From the repository folder (the one where you ran `uv sync`), run
  `uv run pytest -m windows packages/eng-contract/tests/windows`. What you should see: no test reported as failed. A
  local drive that is refused shows up as a failed test: report the drive type and file system. With `ENG_WORKSPACE`
  unset, the default workspace `%LOCALAPPDATA%\eng\workspaces\default` (classified by the real Windows probe) must also
  resolve as local; if it is refused, report the path and the refusal reason.
  See also [spec 0001](packages/eng-contract/docs/specs/0001-eng-contract-0.1.md) Q2 and
  [plan 0001](packages/eng-contract/docs/plans/0001-eng-contract-0.1.md).
- [M] The result store and the model state on a real Windows disk: from the repository folder run
  `uv run pytest packages/eng-contract/tests/unit/test_store.py packages/eng-contract/tests/unit/test_model_state.py`.
  What you should see: no test reported as failed. A record is committed with `os.rename` (refuses an existing file), a
  state file is rewritten with `os.replace`; a virus scanner or indexer holding a freshly written file is retried (0.05,
  0.1, 0.2 s), and a persistent lock gives `StoreWriteError`. If a test fails, report it as section 6 describes.
- [M] The schema snapshots on a Windows clone: from the repository folder run
  `uv run pytest packages/eng-contract/tests/contract/test_schema_snapshots.py`. What you should see: no test reported
  as failed. A clone with `core.autocrlf=true` (the Git for Windows default) has CRLF line endings in `docs/schema`, and
  `test_fresh` then fails; if it does, report it with the output of `git config core.autocrlf`.
- [H] Meaning of `Ton` in the CSI unit names (metric tonne-force or short ton-force). Until confirmed from CSI
  documentation or a live check, those three unit systems (`Ton_mm_C`, `Ton_m_C`, `Ton_cm_C`) are refused:
  [spec 0001](packages/eng-contract/docs/specs/0001-eng-contract-0.1.md), gap G-1;
  [units verification](packages/eng-contract/docs/verification/units.md).

### 7.2 tools/eng-dev-gate

Source: [tools/eng-dev-gate/docs/local-testing.md](tools/eng-dev-gate/docs/local-testing.md). No host program. Most items
need a real GitHub Actions run, not your machine: the composite actions and the jobs (`gate`, `gate-check`,
`risk-floor`, `test-first`, `ci-review`, `security`, `build`, `agents-drift`, `windows`), the base-commit gate, and the
approvals port with bootstrap off (not wired in the CI files yet). GitHub Actions has not run for this repository since
2026-11-04 (7.0). Local CI ran the same commands in the build container ([BUILD-STATUS.md](BUILD-STATUS.md) D-23), so
what is left is how Actions itself runs them. Two items are for your Windows machine:

- [M] The gate on Windows (spec 4.1: it runs on Linux and Windows, the owner's machine). Every test of this package ran
  on Linux only; none carries the `windows` marker and the package declares no `windows_tests`, so neither the
  `windows` job nor `uv run eng-gate windows-tests` covers it. From the repository folder run
  `uv sync --all-packages`, then `uv run eng-gate check --all`, then `uv run pytest tools/eng-dev-gate/tests`. What you
  should see: `check --all` ends without a failed step, and the tests end without a failed test. Differences to watch
  for (spec section 8): path separators in findings; CRLF line endings in the checkout (the repository has no
  `.gitattributes`); the temporary `git worktree` of `test-first`; the `PYTHONPATH` of its base run (joined with
  `os.pathsep`). Report a failing step or test as section 6 describes.
- [M] The mutation step on Windows (ADR-0002). The `windows` job never runs the mutation step, so no CI job can confirm
  the Windows statement. After a change to an R1 or R2 module of a package, run
  `uv run eng-gate mutation --package <name> --base <commit>`. What you should see: the notice MU002 "mutmut has no
  native Windows support (ADR-0002)" without a failure; with the environment variable `CI` set, exit code 3. This shows
  only the gate's own branch; mutmut's own refusal on Windows was not run.

The merge of `build/v1` into `main` is yours after the local tests
([spec](tools/eng-dev-gate/docs/specs/0001-eng-dev-gate-0.1.md) AW06).

### 7.3 eng-harness

Package list: [packages/eng-harness/docs/local-testing.md](packages/eng-harness/docs/local-testing.md) (exists now; so far it holds plans 0001, 0002 and 0004 and the opener of plan 0006). Sources by area, including the plans it does not cover yet:

**Engine** ([plan 0001](packages/eng-harness/docs/plans/0001-engine.md) §4 "Needs local test"; the last item below comes from [spec 0001](packages/eng-harness/docs/specs/0001-engine.md) Q11):
- [M] The overhead benchmark and the fsync cost on your disk with antivirus active, against the engine target.
- [M] The run lock on Windows. From `packages/eng-harness`, run `uv run pytest tests/unit/test_journal_reader.py -m windows`.
  What you should see: no failed test (a second holder is refused, release frees the lock, `is_locked` agrees). This
  test lives in `tests/unit`, so the `windows` job of 7.0 does not run it, and it has never run on Windows. Then kill the
  engine from Task Manager and check that the lock is released (`is_locked` is False and a new `RunLock` can be taken).
- [M] The journal on a Windows run folder whose path has a drive letter, spaces and Arabic characters: `JournalReader` (a
  read-only SQLite URI built from the path) opens a journal that a `JournalWriter` in another process is writing in WAL
  mode, verifies the chain, and sees new events. Only POSIX temporary paths were tested.
- [M] A resume after a forced power-off of a virtual machine.
- [M] File-copy promotion onto a folder you use, including a target file open in another program.
- [H] Reconciliation by model reads after a crash during a write on a Sasaah server, where the repeated write could apply twice without idempotency ([spec 0001](packages/eng-harness/docs/specs/0001-engine.md) §8, Risks; S-10 open risk). Availability: the journal, run lock, ports and result codec are merged; the crash path is [plan 0001](packages/eng-harness/docs/plans/0001-engine.md) (AC30) and the per-tool reconciliation rules are [plan 0002](packages/eng-harness/docs/plans/0002-servers-and-adapters.md) task T14, and neither is merged yet.
- [M] Saving the working copy after every write step may cost seconds on ETABS ([spec 0001](packages/eng-harness/docs/specs/0001-engine.md) Q11; measure with S-02).

**Servers and adapters, CSI/ETABS** ([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §12, items 1 to 13):
1. [H] `csi_launch`: which process is the ETABS parent, the process id in the reply, and that the instance survives
   the server's job closing.
2. [H] A second server (the `long` role) attaching by process id to a server-launched instance.
3. [H] The live `tools/list` fingerprint against the allowlist's.
4. [H] The `serverInfo` the Sasaah server reports.
5. [H] Every table key of §4.6.2 and §4.6.4 and their reply fields.
6. [H] The reply fields of every list tool mapped in §4.6.4.
7. [H] A server timeout during a write and during an analysis; the units afterwards; every reconciliation rule;
   `locked` after a completed analysis; the proof-of-end question for an abandoned analysis (gap H-G7, with S-02).
   7a. [H] After a timeout on a role: the next call re-attaches with `launched: false`, `csi_exit` is refused, and what
   `csi_status` reports as the current target.
8. [H] Fingerprint stability and the blind spots of the read set (S-04).
9. [H] `close_started` closing a hidden launched instance and leaving a visible one.
10. [H] The host-instance lock across two engine processes.
11. [H] `dxf-prep/prepare` and `etabs-model/build` through the adapter, including the configuration rewrite and the
    build-artifact hash (needs AutoCAD and Python; see the [S-12 report](spikes/S-12-sasaah-tool-inventory/REPORT.md)).
12. [H] `eng-harness doctor` on your machine, including the integrity level and installed products.
13. [H] Record mode on a copy, and your review of the recordings before commit.
- [M] The Windows launcher and process inspector (package list, item 13). From `packages/eng-harness`, run
  `uv run pytest tests/windows -m windows`. What you should see: no failed test. These tests start real processes in real
  Job Objects, and they have never run on Windows (the container ran only the fake-kernel32 ones). They cover: suspended
  create, assign and resume; kill-on-close; the breakaway cases (a process started by a server with silent breakaway
  survives the job closing and the engine ending); a tool job refusing breakaway; independent jobs; process identity by
  pid and creation time; `terminate` refusing a wrong start time; children and snapshot. Run them with your antivirus
  and endpoint tools active, from your usual terminal or scheduler (Job Object nesting).
- [H] `ProcessTransport` and `ServerManager` on Windows with the real Sasaah server (package list, item 14): the MCP
  handshake on the launcher's pipes, a complete uncached `tools/list`, a call that outlasts the client backstop, a
  server killed during a call (read and write codes, restart, re-attach by pid), and a shutdown that ends the server on
  end-of-file of its standard input without ending a running host program. Only the Linux fakes have run it.
  Availability: `ServerManager` builds `PosixLauncher()` when no launcher is passed (`servers/_session.py`), and nothing
  in `src` selects the Windows launcher yet, so this check waits for the engine wiring in a later task of plan 0002.
Also: gap H-G2, load directions other than gravity ([spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §11).

**Calcs** ([spec 0003](packages/eng-harness/docs/specs/0003-calcs.md) L-1 to L-3, [plan 0003](packages/eng-harness/docs/plans/0003-calcs.md) §4):
- [H] Fingerprint stability over repeated reads, save and reopen, and detection of the S-04 hand edits E1 to E10.
- [H] Read-back on real ETABS reads, including unit scale, frame load directions and the table reads.
- [H] The design summary against the ETABS design display on a model with failing members.
- Also Q5: object names compared exactly while ETABS may treat names case-insensitively; revisit after the first run.

**Templates and basis** ([plan 0004](packages/eng-harness/docs/plans/0004-templates-and-basis.md) §4):
- [M] A values file and the approval page used on a real template.
- [M] A template written by hand in the user folder (path, encoding, line endings on Windows), and one whose file name
  differs from its `meta.name` only in case (for example `Blank-0.1.0.template.yaml` holding `name: blank`). NTFS ignores
  case, so `TemplateRepository.get` finds that file while `list` refuses it as `meta_invalid`. Report what each does. The
  build tested a case-sensitive file system only.

**Decisions** ([plan 0005](packages/eng-harness/docs/plans/0005-decisions.md) §4):
- [M] The rule-decision timing and the cost of a label write on your disk with antivirus active.
- [M] A decision pending across a forced engine kill and a resume.
- [N] With phase 2, the provider checks (spike S-07, Jev, PydanticAI): the plan does not cover them; see Providers below.

**Command line, pages, report** ([plan 0006](packages/eng-harness/docs/plans/0006-cli-progress-pages-report.md) §4; [spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) G1):
1. [M] The approval page in your real browser: no Content-Security-Policy violation in the console; Arabic and
   mixed-direction text from a real drawing and model displays correctly; forms submit; a second tab opens by cookie.
2. [M] The report opened and printed from disk: the DRAFT watermark and the layout.
3. [M] A workstation with an Arabic regional setting, the Hijri calendar and a cp1256 console: `run`, `status`,
   `report`.
4. [H] Expected times and the heartbeat on a real analysis run (needs spec 0007 and the Sasaah servers).
5. [M] Opening the launch address through the default browser when the default is not Chromium-based.
6. [M] The launch-address opener (spec 0006 AC61): on Windows it opens the address in your default browser
   (`os.startfile`) and ignores a `BROWSER` variable set to another program; the address is written only to your console
   window (`CONOUT$`), and with no console nothing is printed on standard output or error. Only fakes were tested.
   See the package list, item 15.
7. [M] `harness.toml` written by hand on Windows: saved from Notepad as UTF-8 with and without a byte-order mark, and
   with CRLF line endings. `eng-harness status` must not answer `configuration error` (until plan 0006 adds the
   commands it answers that the command is not available in this build). Only UTF-8 files without a mark were tested.

**Model edit cycle** ([spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) §12; section 5 of this guide):
1. [H] A full cycle on a copy of a real model with ETABS 22 and the pinned `sasaah-csi-mcp` build ([plan 0007](packages/eng-harness/docs/plans/0007-model-edit-cycle.md), live acceptance), with the reply fields of `csi_design_results` (steel and concrete) and
   the columns of `Analysis Messages`.
2. [H] `csi_save_model` as a new revision and `csi_open_revision` on a server-launched instance.
3. [H] You editing by hand in the visible launched instance, saving, and pressing "I edited by hand".
4. [H] Acceptance A1 to A7 on benchmark B-1, all of A4, with `cycle-timings.json` filled into your sheet.
5. [H] An ETABS kill and a process kill at analysis, apply and promotion (A6).
6. [H] Promotion when the original is open in your ETABS (file lock).
Related gaps: EC-G2 (concrete design verdicts), EC-G3 (message severity), Q10 (A7 in practice).

**SAFE adapter** ([spec 0008](packages/eng-harness/docs/specs/0008-safe-adapter.md) §12, L1 to L15; SAFE 22, a footing model copy): launch and exit
of a hidden instance; open and save of `.FDB`; new models; the live tool list for SAFE; table fields and rows for
every table of §4.5 (soil pressures, units, truncation); sign conventions of soil pressure and reactions; point-load
semantics; list tools; analysis duration and the save dialog; design run and results; `SuperDead` patterns;
`close_started`; record mode; an ETABS server and a SAFE server in one run.

**Providers** ([spec 0009](packages/eng-harness/docs/specs/0009-providers.md) §9, [plan 0009](packages/eng-harness/docs/plans/0009-providers.md) §4; no host program):
1. [N] Spike S-07 (Jev access, format, batching, latency, confidence, data terms). Until its report exists the Jev
   wire format is an explicit gap (J-G1).
2. [M] Set a key, run, check status, then delete the key, and search the workspace and logs for the key. Uses the
   Windows credential store. See also [ADR 0002](packages/eng-harness/docs/adr/0002-keyring.md).

   ```powershell
   uv run --package eng-harness python -m eng_harness.providers set-key NAME
   uv run --package eng-harness python -m eng_harness.providers status
   uv run --package eng-harness python -m eng_harness.providers delete-key NAME
   ```

   *(Available once eng-harness plan 0009 task T2 has merged; check BUILD-STATUS.md. The key is read with a no-echo
   prompt, per spec 0009 AC8.)*
3. [N] One live structured-output call through OpenRouter with the chosen model, and with a local OpenAI-compatible server.
4. [N] A run with the network disconnected.
5. [M] A shadow-mode run showing the one engineer screen with both suggestions.
6. [M] The first `evaluate` over real labels.

**Revit adapter** ([spec 0011](packages/eng-harness/docs/specs/0011-revit-adapter.md) §12, L1 to L15; spike S-05, an attended Revit session on a copy
of a structural model): the live tool lists of both roles and the add-in hashes; reply fields of every read;
the destructive dialog; transactions and rollback; the server's resend after a broken pipe; column geometry;
specification identifiers; `change_element_type`; active-document behaviour; hashing an open `.rvt`; change
tracking; your column families and shared-parameter GUIDs; two Revit instances; the mapping calc on a real ETABS and
Revit pair; record mode.

**SAP2000 adapter** ([spec 0012](packages/eng-harness/docs/specs/0012-sap2000-adapter.md) §12, L1 to L8; SAP2000 26, a frame model copy): launch,
exit, fingerprint and `csi_status`; `.SDB` open and save; list replies; table fields and rows for each table the
readers need; analysis duration and lock; sign, axes and station semantics of frame forces and reactions; steel and
concrete design results; `csi_frame_details`, `csi_export_joint`, `csi_add_frame_by_coord`, `csi_set_point_load`.

**Column workflows** ([spec 0013](packages/eng-harness/docs/specs/0013-column-workflow.md) §12, items 1 to 8): a full `column_design` run on ETABS (steel
and concrete); a proposal matching an existing section, applied and read back; sign of `P` and the axes of `M2`,
`M3` on a non-square column; a hand edit between cycles; a `column_revit_update` run in an attended Revit session
with your column families; orientation of non-square columns in both models; a process kill during Revit writes;
the column-review benchmark.

**IDEA adapter** ([spec 0014](packages/eng-harness/docs/specs/0014-idea-adapter.md) §12, L1 to L11; spike S-08, an attended session on a copy of a connection
project): the live tool list and `idea_status` per installed version; the unit of loads; reply shapes of loads and
calculate; whether in-memory edits reach a calculation; timeouts; `check_value` scale; licensing behaviour; the stub;
the load map on a hand-verifiable connection; route `rest` file handling; repeated open and close.

### 7.4 packages/structural-codes

No item needs a host program in the core or in the SBC overlay ([plan 0001](packages/structural-codes/docs/plans/0001-core-framework.md),
[plan 0003](packages/structural-codes/docs/plans/0003-sbc304-2018-footing-overlay.md) §4). The comparisons with host
programs (rows marked `PC-1`, "program comparison") are listed here; each clause file also holds its own row:

| Pack and clause | Host | What is compared | Source |
|---|---|---|---|
| ACI 318-14 bearing pressure, service | SAFE | Soil pressure for the footing of HC-2 | [clause](packages/structural-codes/docs/clauses/aci318_14/aci318_14.13_3_1_1.bearing_pressure_service.md) (also sign convention of reactions) |
| One-way shear | SAFE | One-way shear at `d` from the face, if SAFE reports it | [clause](packages/structural-codes/docs/clauses/aci318_14/aci318_14.22_5_5_1.one_way_shear.md) |
| Punching shear | SAFE | Punching ratio of the HC-1 footing | [clause](packages/structural-codes/docs/clauses/aci318_14/aci318_14.22_6_5_2.punching_shear.md) |
| Flexure at the column face | SAFE | Strip moment at the column face | [clause](packages/structural-codes/docs/clauses/aci318_14/aci318_14.13_2_7_1.flexure_at_column_face.md) |
| Minimum flexural reinforcement | SAFE | Minimum steel in footing strips | [clause](packages/structural-codes/docs/clauses/aci318_14/aci318_14.8_6_1_1.min_flexural_reinforcement.md) |
| Development length, bottom bars | SAFE or ETABS | Confirm (from the program documentation or a live look) that neither program reports a development length for footing bars, so the case file may state `program_comparison.not_available` (plan 0002 §6 Q11); if one does, a PC-1 comparison is owed | [clause](packages/structural-codes/docs/clauses/aci318_14/aci318_14.25_4_2_3.development_length_bottom_bars.md) |
| Reaction sign convention | ETABS or SAFE | Signs of `FZ` (positive upward under gravity, so `N = FZ` is compression) and of `FX`, `FY`, `MX`, `MY` in joint reactions, which the merged shared footing statics (`aci318_14._footing`, FS S2 and S3) combine with the reaction height | [plan 0002](packages/structural-codes/docs/plans/0002-aci318-14-footing-checks.md) §4; [bearing clause](packages/structural-codes/docs/clauses/aci318_14/aci318_14.13_3_1_1.bearing_pressure_service.md) §4.1 |
| Maximum axial strength | ETABS | Axial capacity of the common section | [clause](packages/structural-codes/docs/clauses/aci318_14/aci318_14.22_4_2_1.max_axial_strength.md) |
| Axial-flexure, uniaxial | ETABS | Capacity ratio of a short uniaxial column | [clause](packages/structural-codes/docs/clauses/aci318_14/aci318_14.22_4_1_1.axial_flexure_uniaxial.md) |
| Longitudinal reinforcement limits | ETABS | Ratio limits applied by concrete frame design | [clause](packages/structural-codes/docs/clauses/aci318_14/aci318_14.10_6_1_1.longitudinal_reinforcement_limits.md) |
| Force sign convention | ETABS | Sign of `P` and axes of `M2`, `M3` | [plan 0004](packages/structural-codes/docs/plans/0004-aci318-14-column-checks.md) §4 |

These rows exist so that you can compare a worked check with the program. They cannot be run until the pack checks
([plan 0002](packages/structural-codes/docs/plans/0002-aci318-14-footing-checks.md) T3 to T8,
[plan 0004](packages/structural-codes/docs/plans/0004-aci318-14-column-checks.md)) and a way to run a check against a
host model exist. Neither is on `build/v1` yet; only the shared footing statics, the verification runner and the
`needs_local_test` case state are (the `verify` command, core plan T12, is not). The checks stay draft until you approve
them ([BUILD-STATUS.md](BUILD-STATUS.md) owner queue).

A comparison row becomes evidence only through its case file: the case of kind `program_comparison` stays `pending`
("needs local test") while its `source.status` is `needs_local_test`; after your run it names `program`,
`program_version`, a `record` (the path of a live acceptance record, [process/05](design/process/05-testing-and-verification.md)
§6) and its `assumption_differences`, with the program's numbers as the expected values. Until every such case passes,
the check is not reported `verified` (core [spec 0001](packages/structural-codes/docs/specs/0001-core-framework.md)
§4.9.4, condition 2). No acceptance script writes these records yet (Open points, item 14).

### 7.5 Spikes

| Spike | What is yours to run | Source |
|---|---|---|
| S-02 | Section 2.1 of this guide | [README](spikes/S-02-analysis-design/README.md) |
| S-04 | Section 2.2 of this guide | [README](spikes/S-04-model-state/README.md) |
| S-10 | Windows evidence came from a CI run (2026-11-03, `windows-latest`). Open: run `uv run --script spikes/S-10-replay/windows_check.py` on your workstation with antivirus and check that the engine-exit cases of `assign_after` and `suspended` report processes tracked (on the runner they tracked 0, which proves nothing, and the script still passes when nothing is tracked); the journal speed on your disk (`bench.py`); host programs leaving a server's job (no case in `windows_check.py` yet). Power loss and reconciliation on a real Sasaah server: see 7.3, Engine | [report](spikes/S-10-replay/REPORT.md), Open risks |
| S-12 | The static inventory must be compared with a live `tools/list` at the first local run, including the `serverInfo` that MCP initialize returns by default (the CSI server sets none); the poll behaviour during analysis; session state after a worker recycle; the frame load direction codes and the unmapped direction of `csi_set_frame_load_point`; the units left unrestored after a timeout (S12-G9); whether `csi_results_*` marks the model modified (SelectOutput); the late-bound `spec` keys; table keys for read-backs, including `Analysis Messages` and `Project Information`; bridge-plugin unit handling; the double send on a Revit bridge error; the Revit `code` toolset user setting; `tools/dxf-prep/prepare.ps1` (needs AutoCAD 2023 `accoreconsole` and Python on the PATH); regenerate the inventory with the Sasaah Agent tool-manifest exporter and compare it with the static inventory ([BUILD-STATUS.md](BUILD-STATUS.md) OQ-Q5) | [report](spikes/S-12-sasaah-tool-inventory/REPORT.md) |
| S-05, S-07, S-08 | Revit, Jev and IDEA readiness: see 7.3 | specs 0011, 0009, 0014 |

### 7.6 products/

[products/README.md](products/README.md): the analysis of the desktop products was made from reading source; every
statement about behaviour is "needs local test". Nothing is built there in v1, so no step is yours yet.

### 7.7 Whole repository

[SUPPORT.md](SUPPORT.md): tested host versions are "none yet". Each live pass you complete adds the host version it
ran on (the live acceptance record, [process/05](design/process/05-testing-and-verification.md) §6). The merge of
`build/v1` into `main` is yours after these tests ([ADR-0028](design/docs/adr/0028-build-v1-in-this-repository.md) §4).

---

## Open points

Each is something this guide needs but the documents do not define, with the file that should define it.

1. **Record mode switch and record script options.** The `harness.toml` key that turns record mode on, the options of
   `record_csi.py`, how to verify a manifest by hand, and the contents of `acceptance/recordings/README.md`.
   [spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.8.1 (plan task T17).
2. **Timeouts for the first run.** `client_grace_s` and every `call_timeout_s` are required with no default, to be
   sized by S-02, but no document says which provisional values to use to run `doctor` before S-02, or how to turn the
   S-02 times into the two roles' values. [spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md)
   §4.2 rule 1 and OQ-G6.
3. **Building the Sasaah servers and the pinned commit.** The build procedure, the exact pinned commit and the build
   output path are not stated in this repository. The adapter allowlist, which will hold the tested commit, is not
   written yet. [spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.3.4 and §4.5.1.
4. **The `--input` JSON.** How the model file is written in `input.json` (the `harness.file_input/1` reference).
   [spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) §4.2 and [spec 0002](packages/eng-harness/docs/specs/0002-servers-and-adapters.md) §4.7.
5. **Pausing a waiting run for a later change set.** The first change set comes from `run --answers FILE` (decided by
   amendment B-354, spec 0006 AC64). A later one is given with `resume --answers FILE` "after a pause" (spec 0007
   §4.3.1); how the waiting `run` is paused for it is not stated. [spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.2.1.
6. **How to invoke the command from the root.** Resolved by amendment B-354: the supported form is
   `uv run --package eng-harness eng-harness <command>` ([spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.1, AC65);
   the owner confirms it against the uv documentation (spec 0006 Q18).
7. **Running the A3 audit and the A7 prompt counter on real journals.** Resolved by amendment B-354: the read-only
   entry point `python -m eng_harness.report` with `audit-sources` and `count-prompts`
   ([spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) AC35, Q11).
8. **Local comparison procedure for A6 and the B-1 sheet.** How to decide "the same model as an uninterrupted run"
   and the layout of the B-1 time sheet. [18](design/docs/architecture/18-first-slice-dxf-to-etabs.md) §5; [spec 0007](packages/eng-harness/docs/specs/0007-model-edit-cycle.md) §4.9.
9. **The live acceptance script and record for A1 to A7.** [process/05](design/process/05-testing-and-verification.md)
   §6 says the script writes the record; none is planned for the edit cycle. Also the script folder: [AGENTS.md](AGENTS.md)
   §10 says `acceptance/scripts/` at the root; the plans put scripts under `packages/eng-harness/acceptance/scripts/`. Specs 0011 and 0014 (section 12) write only
   `acceptance/scripts/` without the package path ([spec 0011](packages/eng-harness/docs/specs/0011-revit-adapter.md),
   [spec 0014](packages/eng-harness/docs/specs/0014-idea-adapter.md)).
10. **Run class for acceptance.** Calcs ship draft; `production` refuses them; this guide uses `trial`. The owner's
    approval route (`approvals.yaml`) and when to switch to `production` is for the owner.
    [spec 0003](packages/eng-harness/docs/specs/0003-calcs.md) Q10; [spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) Q7.
11. **Package `docs/local-testing.md` files.** All four exist. The eng-harness file holds so far plans 0001, 0002 and
    0004 and the opener of plan 0006; section 7.3 must be reconciled with it as the remaining plan tasks add their parts.
    The structural-codes file lacks the four column rows of section 7.4, which
    [plan 0004](packages/structural-codes/docs/plans/0004-aci318-14-column-checks.md) T5 adds.
12. **Committing recordings.** The repository documents do not say how the owner commits recordings to the protected
    path `acceptance/recordings/` (git installation, branch `build/v1`, the commit message form, the push). Git is not
    listed in 1.2 because no document requires you to use it. Until this is defined, the agent states the procedure at
    the time (section 4, step 6).
13. **`--no-wait` and basis confirmation.** Resolved by amendment B-354: there is no deferred basis confirmation; a
    workflow with required basis fields is started by a waiting `run`, and `--no-wait` exits 10 and stores nothing
    ([spec 0006](packages/eng-harness/docs/specs/0006-cli-progress-pages-report.md) §4.4.7, AC47).
14. **Acceptance records for program comparisons.** A `program_comparison` case points to an acceptance record that a
    live acceptance script writes ([process/05](design/process/05-testing-and-verification.md) §6), but no script or
    procedure for the PC-1 rows of section 7.4 is planned. [plan 0002](packages/structural-codes/docs/plans/0002-aci318-14-footing-checks.md)
    §4 and [plan 0004](packages/structural-codes/docs/plans/0004-aci318-14-column-checks.md) §4.
