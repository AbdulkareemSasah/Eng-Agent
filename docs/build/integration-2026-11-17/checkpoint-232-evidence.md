# Integration evidence: B-551, B-553 and B-561

Checkpoint: 2026-11-17; build/v1 at `1ec7566c016aacf75c15aacb260435df44f23c67`.

## Merges

| Work item | PR | Squash commit | CI evidence |
|---|---:|---|---|
| B-561 | #414 | `c803dad7f65f1f9a4f3b770dcb12bb080504e02c` | PASS at head `6fda1a2beea771e1223d9acd6c2355247c414f06`; full gate 1249 s |
| B-551 | #415 | `9c26ab3435c9dd3867313bdef2eb60e63633c218` | PASS at head `db65b2a60e7184d68d5c782a252eb83ed06dbf4e`; batch full gate 895 s |
| B-553 | #416 | `1ec7566c016aacf75c15aacb260435df44f23c67` | PASS at head `580fa8881eda103033da6e6c09826d1b93690db3`; same batch full gate |

B-551/#415 and B-553/#416 were locally tested together on batch tree `9db7ea3f93ded33999befc85e126bf9c419fdbdf`; the final build/v1 tree matches that tested tree. Both PRs were merged on their passing heads. Full gate logs and summaries are retained in the lead scratch records referenced in the integration report.

## Mutation evidence

- B-551 per-change mutation passed on authored head `b55b965b0d979b57d1751c07a4403bc74493047d`; configured floor was 80%. The successful output did not emit an exact score, so this record claims only that the floor passed. The mutation report and full log are retained in the lead scratch records.
- B-553 mutation selector passed (exit 0); the eng-dev-gate package has no configured eligible R1/R2 modules. No numerical score is claimed.
- Periodic mutation run 5 passed with six members, exit 0, base `4f1a7e67`, head `d9c19fb`; 11:09:17–11:24:15 UTC (898 seconds). Output: [periodic-mutation-d9c19fb.log](periodic-mutation-d9c19fb.log). Three PR merges (#414–#416) followed this run; the next periodic run is due after seven more merges, based on `d9c19fbd`.

## Limitations and attribution

- Windows was not run on the Linux machine.
- `uv audit --locked` was not run because `api.osv.dev` is outside AGENTS.md §9 allowed services. This describes the repository allowlist, not a claim about current network connectivity.
- The automatic B-561 base merge commit `6fda1a2beea771e1223d9acd6c2355247c414f06` lacked an `Assisted-by` trailer. It was published when detected and history was preserved. The final squash commit `c803dad7f65f1f9a4f3b770dcb12bb080504e02c` carries the required sole trailer.

Source reports checked before writing this archive: B-551/B-553 integration report, B-561 integration report, B-551 mutation report, and B-553 integration-preparation report.
