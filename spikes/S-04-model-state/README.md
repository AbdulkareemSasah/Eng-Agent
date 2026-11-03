# Spike S-04: reading the model state through sasaah-csi-mcp (owner's local run)

Question ([19](../../design/docs/architecture/19-roadmap-and-spikes.md) §2): how fast and how reliably can the model state that the edit kinds touch be read through `sasaah-csi-mcp`; does a fingerprint over it come out the same when the same model is read twice; does it catch edits made by hand in the ETABS window; can a model identity be stamped and read back in project information.

The script `s04_run.py` works only on a **copy** of the model you name. Nothing here is a result until you run it: everything is "needs local test". The spike report is written afterwards from the files the script produces.

## What you need

- Windows with ETABS installed and licensed, and no other ETABS window you care about open (the script starts its own ETABS and exits it at the end).
- `uv` installed. The Python scripts run with `uv run --script` only.
- A built `sasaah-csi-mcp.exe` (the build the project pins). Note its path.
- An ETABS model (`.EDB`) that has frames, areas (slab or wall), load patterns and a restraint or two. A model of the size you really work with is best.
- This repository checked out. Run the commands from a scratch folder **outside** the repository.

## Steps

1. Check the plan (nothing starts, nothing is written):

   ```
   uv run --script <repo>\spikes\S-04-model-state\s04_run.py --model "D:\models\test.EDB" --server-exe "D:\build\sasaah-csi-mcp.exe" --dry-run
   ```

   It lists every read and the hand edits you will be asked to make.

2. Close ETABS. Run it for real:

   ```
   uv run --script <repo>\spikes\S-04-model-state\s04_run.py --model "D:\models\test.EDB" --server-exe "D:\build\sasaah-csi-mcp.exe"
   ```

   Options: `--repeats 5` (more baseline reads), `--limit 50000` (if the summary reports truncated reads), `--skip-edits` (no pause), `--skip-reopen`. `--help` lists all.

3. ETABS opens visibly with the copy. The script reads the model several times (this takes a few minutes on a large model), then **stops and prints a numbered list of edits** E1 to E10 and an identity text.

4. In the ETABS window, make as many of the edits as you can, on the copy only. Make **one small change per edit**, as listed. For E10, open Project Information (File menu) and type the printed identity text into the Project Number field. Do **not** save, run analysis or close ETABS. Skipping edits is fine.

5. Go back to the terminal and press Enter. The script reads again, prints the differences it sees, then asks `Did you make E1 ...? [y/N]` for each edit. Answer honestly: this is how it tells "not noticed" from "not made".

6. The script saves the copy, reopens it, reads once more and exits ETABS. It prints a summary and the two files to send back, in `spike-runs\S-04-<time>\`: `record.json` and `summary.md`.

## What to look at in summary.md

- **Time to read the model state**: one full pass and the slowest reads; the "ms per item" column shows how the time grows with model size.
- **Stability**: "Same fingerprint every time" should be `True`. If only the "order included" value is `False`, the server returns the same content in a different order (fine if the fingerprint ignores order). Sections listed as differing are unstable: note them.
- **Failed reads** (a table name this ETABS version does not know) show `False` in the read table; report them, they are findings.
- **Edits made by hand**: which of your edits were noticed and which were not. "NOT noticed" edits are blind spots of the read set; the harness would miss such a manual edit.
- **Identity**: no tool can write project information (known gap S12-G6), so the stamp is written by you. Check "read back after the edit" and "after save and reopen".
- **Save and reopen**: whether the fingerprint stays the same.
- **Original model unchanged** must be `True`.

## Before you send the files back

Check that `summary.md` and `record.json` hold no client or project name. Project Information rows are never written to the record, but object names, section names and messages come from your model: replace anything that identifies a client or project.

## If something fails

Tell the agent (paste into the chat): the command you ran; the last 30 lines printed, or the "Errors" section of `summary.md` if it was written; `server-main.stderr.log` from the run folder; what ETABS showed. A run that stops part-way still writes both files. If ETABS stays open after a failure, close it by hand and do not save.

## What the script does not do

- It never writes to the model through a tool (no table writes, no scripts); the only changes to the copy are your hand edits and the save.
- Fingerprint settings (units token, rounding digits) are spike settings, not engineering values. Rounding keeps 6 decimals by default (`--round-digits`); the units token is taken from the Sasaah units helper.
