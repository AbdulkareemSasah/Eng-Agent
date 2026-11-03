# Spike S-02: analysis and design through sasaah-csi-mcp (owner's local run)

Question ([19](../../design/docs/architecture/19-roadmap-and-spikes.md) §2): how long do analysis and design take through `sasaah-csi-mcp`; what happens on a short call timeout (the evidence for `TIMEOUT_UNKNOWN_OUTCOME`); does saving first avoid a save dialog; are dialogs detected; is the model locked after analysis and does the unlock step work.

The script `s02_run.py` works only on a **copy** of the model you name. It never clicks a dialog. Nothing here is a result until you run it: everything is "needs local test". The spike report is written afterwards from the files the script produces.

## What you need

- Windows with ETABS installed and licensed, and no other ETABS window you care about open (the script starts its own ETABS and exits it at the end).
- `uv` installed. The Python scripts run with `uv run --script` only.
- A built `sasaah-csi-mcp.exe` (from the Sasaah repository, the build the project pins). Note its path.
- An ETABS model (`.EDB`) that **already has load cases, combinations and a design setup**, so that analysis and design can run. Use a mid-sized model you know. Keep a note of its size (stories, frames).
- This repository checked out. Run the commands from a scratch folder **outside** the repository, so run folders are never committed.

## Steps

1. Check the plan without starting anything (copy the path of the model and of the server exe):

   ```
   uv run --script <repo>\spikes\S-02-analysis-design\s02_run.py --model "D:\models\test.EDB" --server-exe "D:\build\sasaah-csi-mcp.exe" --dry-run
   ```

   It lists what would be called. It writes nothing. Both files must show `found`.

2. Close ETABS. Run it for real:

   ```
   uv run --script <repo>\spikes\S-02-analysis-design\s02_run.py --model "D:\models\test.EDB" --server-exe "D:\build\sasaah-csi-mcp.exe"
   ```

   Useful options: `--runs 5` (more runs), `--design-kind steel` (default `concrete`), `--timeout-tests analysis,design` (also test a design timeout), `--short-timeout-sec 10` (default: 30 percent of the fastest analysis), `--probe-unsaved` (see below), `--skip-design`. `--help` lists all.

3. Wait. ETABS opens visibly. Do not touch the ETABS window while it runs. If a dialog appears and the script seems stuck, **dismiss it by hand** and write down what it said and when (the script also records dialogs it sees, but only as a list; it never clicks).

4. At the end the script prints a summary and the two files to send back. They are in `spike-runs\S-02-<time>\`:
   - `record.json` (machine readable) and `summary.md` (short).
   - Also in that folder, for you only unless asked: `model-copy\` (the copy), `server-*.stderr.log`, `csi-mcp-audit-*.jsonl`.

5. Optional second run with `--probe-unsaved`: it runs one analysis **without** saving first, to see whether a dialog appears. If ETABS shows a dialog, dismiss it by hand.

## What to look at in summary.md

- **Run times**: analysis, design and save, minimum/median/maximum over the runs.
- **Locked after analysis** should be `True`; the write probe must show `model_locked`; after the unlock step it must work (this is a dry-run call, so the model is not changed).
- **Short timeout**: the code and message the server returned, how long it took, how long the main server then waited for ETABS to answer (analysis still running or not), whether the model is locked afterwards, and whether the units are the same as before.
- **Dialogs seen**: title and phase. "None seen" is only meaningful if the summary says dialog detection was available (Windows, process id known).
- **Original model unchanged** must be `True`.

## Before you send the files back

Open `summary.md` and `record.json` and check that no client or project name appears (the script keeps only file base names and removes folder paths, but ETABS messages and dialog titles may carry names). Remove or replace any you find.

## If something fails

Tell the agent (paste into the chat):

- the command you ran (without personal folders if you prefer);
- the last 30 lines printed, or `summary.md` if it was written (the "Errors" section);
- `server-main.stderr.log` from the run folder;
- what you saw in ETABS (dialog text, whether ETABS was still running, whether it was stuck).

A run that stops part-way still writes `record.json` and `summary.md`. If ETABS is left running after a failure, close it by hand; the copy in `model-copy\` can be deleted.

## What the script does not do

- It does not call `csi_run_script`, `csi_db_tables_apply` or any generic tool; the code refuses them.
- It does not change the original model (its SHA-256 is compared before and after).
- Whether a call that timed out actually finished is shown only by the later state (locked, status codes, how long ETABS stayed busy); the script does not decide, it records.
