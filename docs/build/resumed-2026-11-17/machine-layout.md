# Machine layout and setup report

Date: 2026-11-17 UTC

## Paths

- Reference checkout (`build/v1`): `<build-v1>` (branch `build/v1`, HEAD `2a2171ea`)
- Worktrees root: `<worktrees>` (created; no task worktrees created)
- Lead scratch: `<lead>`
- Playbook: `<lead>/PLAYBOOK.md`
- Priority list: `<lead>/PRIORITY.txt`
- Lead findings: `<lead>/reports/lead-findings.md`
- Resume material: `<lead>/resume/`
- Lead tools: `<lead>/tools/`
- Workflow scripts: `<lead>/lane-scripts/`
- Scratch directories created: `reports/`, `pr/`, `logs/`, `locks/`, `integ/`

The reference checkout is the existing repository checkout; no additional read-only hub worktree was needed. `.lead/` and `.worktrees/` are excluded through `.git/info/exclude`, preserving the existing entries. Placeholder paths in copied materials were replaced with the real workspace paths; a scan found no remaining `<lead>`, `<build-v1>`, `<worktrees>`, `<hub>`, `<lane-scripts>` or `<session-transcript>` tokens in `.lead/`.

## Machine

- Platform: Linux x86_64, kernel `6.18.57`
- Available processors: 5 (`getconf _NPROCESSORS_ONLN` and `nproc`)
- Memory: 34,906,004 kB total; 34,012,452 kB available after setup
- Python requested by `.python-version` and `pyproject.toml`: 3.14; uv installed CPython 3.14.10
- uv: 0.13.6

## Dependency setup

Ran from `<build-v1>`:

```sh
UV_CACHE_DIR=<lead>/uv-cache \
UV_PYTHON_INSTALL_DIR=<lead>/python \
uv sync --all-packages --locked
```

Result: exit status 0. uv created `.venv`, built the six workspace packages and installed 84 packages from the locked resolution. Cache and Python install data are under `.lead/uv-cache` and `.lead/python`, avoiding the home filesystem. uv emitted two build-system version warnings: package requirements specify `uv-build` `<0.12` while the installed uv is 0.13.6. These did not prevent package builds or installation. TLS and signature settings were not changed.

No tests, gates, services, dry runs, GitHub CLI calls, commits or pushes were run. Repository tracked status remains clean; only `.git/info/exclude` and ignored setup artifacts were added/created.
