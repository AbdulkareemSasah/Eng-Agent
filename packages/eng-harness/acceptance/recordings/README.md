# Recordings of the Sasaah servers

Recordings of real sessions with a Sasaah MCP server, made by the owner with record mode (spec 0002 section 4.8.1), one
folder per `<adapter>-<commit>+<exe>/`. They are test data, never packaged: `tests/fakes/recorded/` serves them and
`tests/contract/test_csi_recordings.py` runs them through the adapter and compares the synthetic fake with them.

## Making one (owner only, on a copy that holds nothing you cannot publish)

`uv run python acceptance/scripts/record_csi.py --config harness.toml --model <copy> --analysis --cases <names> --combos <names>`
(without `--analysis` it records launch, open and the model-state read only). The name mapping stays in the run
folder the script prints, never here.

## What record mode did, and what it cannot

Each `tools/list` and `tools/call` request and reply, and the `initialize` result, is a file `<seq>-<tool>.json`.
Replaced: model and file base names (`<model-1>.EDB`, `<file-2>.dxf`, by first appearance, extension kept), paths in the
run folder (`<run>/...`), other absolute paths (`<path>/<name>`), the user name, the home folder. Dropped: reads of the
`Project Information` table. `manifest.json` lists every file with its SHA-256, the adapter, the build, the tool
fingerprint of the recorded `tools/list` (allowlisted tools) and the harness version.

Free text cannot be sanitized mechanically. **Before committing, read every file** for client, project or person names
in messages, table cells, section and load names, and folder names (a path with spaces inside a sentence is only partly
replaced). Delete the exchange or the recording if in doubt.

## After committing

`uv run eng-gate check --package eng-harness` runs the contract tests on the folder. A reply whose fields differ from
what the mappers read fails there: that confirms the fields of local-testing items 5 and 5c, or shows what to fix, in
the mapper or in the synthetic fake first (spec 0002 section 4.8.3), never in the recording. Setting
`fingerprint_source = "recording"` and the recorded fingerprint in `csi/_allowlist.toml` is a separate allowlist change.
