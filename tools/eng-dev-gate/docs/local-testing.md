# Local testing: eng-dev-gate

Nothing in the skeleton (plan task T1) needs a host program. Items below are added by later tasks.

- Real GitHub Actions runs of the composite actions (task T6) and the Windows CI job: needs a CI run.
- The `check` command runs real `uv`, ruff and mypy; only its integration tests (toy workspace in a temporary directory, no network, no host program) cover that, so nothing here needs a host program (task T5).
- Base-commit gate (task T26, needs a real CI run once T6 has wired the jobs): that `uv run --project <gate-root> --package eng-dev-gate eng-gate --root . --gate-root <gate-root> <command>` runs the base gate in its own environment while the head environment runs the code under test; that `hashFiles` in a step `if:` sees `.gate-base`; that `PYTHONPATH` puts the base plugin ahead of an editable install of the head; and that the event file's `base.sha` equals `git rev-parse HEAD` of the `.gate-base` checkout (the CF009 provenance rule). The tests use temporary repositories and a redirected running package; they do not show any of this.
