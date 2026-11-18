#!/usr/bin/env bash
# Lead tooling (playbook section 8 item 8): the mutation step over everything merged since the previous periodic run.
# Usage: periodic-mutation.sh <base sha: build/v1 at the previous periodic run>
# It tests origin/build/v1 as it is now, in its own worktree, at low priority, without the local CI lock.
set -u
base=$(git -C <build-v1> rev-parse "${1:?base sha}") || exit 2
git -C <build-v1> fetch -q origin build/v1
head=$(git -C <build-v1> rev-parse origin/build/v1)
WT=<worktrees>/full-ci
git -C <build-v1> worktree remove --force "$WT/.gate-base" 2>/dev/null
git -C <build-v1> worktree remove --force "$WT" 2>/dev/null
git -C <build-v1> worktree prune
git -C <build-v1> worktree add -q --detach "$WT" "$head" || exit 2
git -C <build-v1> worktree add -q --detach "$WT/.gate-base" "$base" || exit 2
ev=<lead>/logs/full-ci-event.json
python3 - "$base" "$head" "$ev" <<'PY'
import json, sys
base, head, out = sys.argv[1:4]
json.dump({"action": "synchronize", "number": 0, "pull_request": {
    "number": 0, "title": "chore(ops): periodic mutation run over the merges since the previous run",
    "body": "Work-Item: B-516\nPlan-Task: trivial\nRisk: r3\n", "draft": False, "user": {"login": "AbdulkareemSasah"},
    "labels": [], "base": {"ref": "build/v1", "sha": base, "repo": {"full_name": "AbdulkareemSasah/Eng-Agent"}},
    "head": {"ref": "build/v1", "sha": head, "repo": {"full_name": "AbdulkareemSasah/Eng-Agent"}}}}, open(out, "w"))
PY
log=<lead>/logs/periodic-mutation-${head:0:7}.log
cd "$WT" || exit 2
uv sync -q --all-packages --locked && uv sync -q --project .gate-base --package eng-dev-gate --locked || { echo "SETUP_FAIL"; exit 2; }
echo "periodic mutation: base ${base:0:7} head ${head:0:7} started $(date -u +%H:%M:%S)" | tee "$log"
GITHUB_ACTIONS=true CI=true GITHUB_EVENT_NAME=pull_request GITHUB_EVENT_PATH=$ev GITHUB_REPOSITORY=AbdulkareemSasah/Eng-Agent \
  chrt -i 0 nice -n 19 uv run -q --project .gate-base --package eng-dev-gate eng-gate --root . --gate-root .gate-base check --all --only mutation >>"$log" 2>&1
rc=$?
echo "finished $(date -u +%H:%M:%S) exit=$rc" | tee -a "$log"
tail -20 "$log"
exit $rc
