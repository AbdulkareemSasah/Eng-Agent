# Local testing: eng-contract

No host program is involved. The Windows probe (`eng_contract.store`, plan task T13) needs real Windows folders; the
owner checks these on the Windows machine (the rules themselves are tested on every OS over a fake Windows API):

1. Workspace on a OneDrive folder, including a Files On-Demand sync root: set `ENG_WORKSPACE` to a folder inside it
   and start any consumer of `resolve_workspace`; expect `PRECONDITION_FAILED` (`local_workspace`) with `received`
   `cloud_synced`.
2. Workspace on a mapped network drive and on a UNC path: expect the same refusal with `received` `network`.
3. Workspace on a fixed local drive: expect it to resolve with classification `local`. If it is refused as `unknown`,
   report the drive type and file system (spec Q2).
4. `uv run pytest -m windows packages/eng-contract/tests/windows` passes (also run by the Windows CI job).
