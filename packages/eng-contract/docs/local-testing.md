# Local testing: eng-contract

No host program is involved. The Windows probe (plan task T13) needs real Windows folders (its rules run on every OS):
1. `ENG_WORKSPACE` inside a OneDrive folder, also a Files On-Demand sync root: refused, `local_workspace`, `cloud_synced`.
2. A mapped network drive or a UNC path: refused with `network`.
3. A fixed local drive: resolves as `local`; if refused as `unknown`, report the drive type and file system (spec Q2).
4. `uv run pytest -m windows packages/eng-contract/tests/windows` passes (the Windows CI job runs it too).

The result store (plan task T14) uses the real disk; its rules run over a fake on every OS, so the owner checks on Windows:
5. `uv run pytest packages/eng-contract/tests/unit/test_store.py packages/eng-contract/tests/unit/test_model_state.py` passes on NTFS (`os.rename` refuses an existing file; `os.replace` overwrites a state file).
6. A virus scanner or indexer holding a freshly written record is retried (0.05, 0.1, 0.2 s); a persistent lock gives `StoreWriteError`.
