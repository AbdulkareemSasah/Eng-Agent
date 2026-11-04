# Local testing: eng-contract

No host program is involved. The Windows probe (plan task T13) needs real Windows folders (its rules run on every OS):
1. `ENG_WORKSPACE` inside a OneDrive folder, also a Files On-Demand sync root: refused, `local_workspace`, `cloud_synced`.
2. A mapped network drive or a UNC path: refused with `network`.
3. A fixed local drive: resolves as `local`; if refused as `unknown`, report the drive type and file system (spec Q2).
4. `uv run pytest -m windows packages/eng-contract/tests/windows` passes (the Windows CI job runs it too).
