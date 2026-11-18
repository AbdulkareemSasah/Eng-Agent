#!/usr/bin/env bash
# Lead tooling (playbook section 8, work item B-514): the mechanical steps of the integrator role, so that the
# integrator agent runs a fixed sequence instead of composing every step itself. It changes no rule of playbook
# section 5: same lock, same merge rules, same local CI, same "never merge without a PASS on the current head".
# Usage: integrate.sh <merge|gate|push|body|ci|finish|status> <NNN> [args]
# Exit codes: 0 done, 1 failed (gate or CI), 3 still running or waiting (call the same command again),
#             4 conflict, 6 try again shortly (head mismatch or fetch error), 7 behind (start again from `merge`).
set -u
L=<lead>
B=<build-v1>
cmd=${1:-}; N=${2:-}
[ -n "$cmd" ] && [ -n "$N" ] || { echo "usage: integrate.sh <merge|gate|push|body|ci|finish|status> <NNN> [args]"; exit 2; }
WT=<worktrees>/b$N
ST=$L/integ; LK=$L/locks
mkdir -p "$ST" "$L/pr" "$L/logs"
BODY=$L/pr/b$N-body.md
OWNER=$LK/integrate.owner.b$N
REL=$LK/integrate.release.b$N
WAIT=520   # seconds one call may block (the tool timeout is 600)

# Batch mode (owner decision of 2026-11-16, work item B-539): when the file $L/BATCH_MODE exists, local CI itself
# queues the runs, tests on the newest base and tests waiting pull requests as one batch, so the lead's integration
# lock is not taken: several integrators prepare their pull requests and wait at local CI at the same time.
batch_mode() { [ -f "$L/BATCH_MODE" ]; }

have_lock() { batch_mode && return 0; [ -f "$OWNER" ] && pgrep -f "integrate.owner.b$N;" >/dev/null 2>&1; }

take_lock() {
  if have_lock; then return 0; fi
  if ! pgrep -f "integrate.owner.b$N;" >/dev/null 2>&1; then
    rm -f "$REL" "$OWNER"
    touch "$LK/prio-wait.b$N"
    nohup flock "$LK/integrate.lock" -c "echo held > $OWNER; while [ ! -f $REL ] && [ \$SECONDS -lt 14400 ]; do sleep 5; done; rm -f $OWNER" >/dev/null 2>&1 &
  fi
  local t=0
  while [ $t -lt $WAIT ]; do
    if [ -f "$OWNER" ]; then rm -f "$LK/prio-wait.b$N"; return 0; fi
    sleep 5; t=$((t + 5))
  done
  return 1
}

title() {
  if [ -s "$L/pr/b$N-title.txt" ] && ! grep -q '^__REGISTRY__$' "$L/pr/b$N-title.txt"; then head -1 "$L/pr/b$N-title.txt"; return; fi
  python3 - "$N" <<'PY'
import json, sys
n = sys.argv[1]
for x in json.load(open('<build-v1>/ops/remaining-tasks.json'))['tasks']:
    if x['id'] == 'B-' + n:
        print(x['prTitle']); break
PY
}

branch() { git -C "$WT" branch --show-current; }

case "$cmd" in
merge)
  [ -d "$WT" ] || { echo "ERROR no worktree $WT"; exit 2; }
  [ -z "$(git -C "$WT" status --porcelain)" ] || { echo "ERROR the worktree is not clean:"; git -C "$WT" status --short | head; exit 2; }
  # The lead holds a task back until something it depends on has merged (for example its plan amendment).
  h=0; while [ -f "$LK/hold.b$N" ] && [ $h -lt $WAIT ]; do sleep 10; h=$((h + 10)); done
  [ ! -f "$LK/hold.b$N" ] || { echo "WAITING_HOLD the lead holds this task until a dependency merges: run this command again"; exit 3; }
  take_lock || { echo "WAITING_LOCK another integration holds the lock: run this command again"; exit 3; }
  cd "$WT" || exit 2
  br=$(branch)
  git fetch -q origin build/v1 || { echo "RETRY git fetch failed"; exit 6; }
  need=0
  if ! git merge-base --is-ancestor origin/build/v1 HEAD; then
    before=$(git rev-parse HEAD)
    msg="merge: origin/build/v1 into $br

Assisted-by: anthropic/claude"
    if ! git merge --no-ff -m "$msg" origin/build/v1 >"$L/logs/b$N-merge.log" 2>&1; then
      ok=1; files=$(git diff --name-only --diff-filter=U)
      for f in $files; do
        case "$f" in
          */CHANGELOG.md|CHANGELOG.md|*/docs/local-testing.md)
            git show ":1:$f" >"$ST/b$N.base" 2>/dev/null || : >"$ST/b$N.base"
            git show ":2:$f" >"$ST/b$N.ours"; git show ":3:$f" >"$ST/b$N.theirs"
            git merge-file --union -p "$ST/b$N.ours" "$ST/b$N.base" "$ST/b$N.theirs" >"$f"; git add "$f" ;;
          *) ok=0 ;;
        esac
      done
      if [ $ok = 1 ]; then
        git commit -q --no-edit || { git merge --abort; echo "CONFLICT could not complete the merge: $files"; exit 4; }
        echo "MERGED_WITH_UNION kept both sides in: $files"
      else
        git merge --abort
        echo "CONFLICT $(echo $files)"; exit 4
      fi
    fi
    own=$(git diff --name-only "$(git merge-base origin/build/v1 "$before")" "$before" | grep -Ev '\.md$' | head -1)
    brought=$(git diff --name-only "$before" HEAD | grep -Ev '\.md$' | head -1)
    # Since B-516 the local CI run of a pull request IS the gate without mutation on the merged head (all packages),
    # so a second run of the same gate in the worktree under the lock only doubles the time the lock is held.
    # NEED_GATE stays 0; `gate` remains available for a manual check.
    : "$own" "$brought"
  fi
  rm -f "$ST/b$N.gate.rc" "$ST/b$N.gate.pid" "$ST/b$N.rundir"
  echo "MERGE_OK branch=$br head=$(git rev-parse HEAD) NEED_GATE=$need"
  ;;
gate)
  member=${3:?member}
  have_lock || { echo "ERROR lock not held: run merge first"; exit 2; }
  log=$L/logs/b$N-gate-int.log
  if [ ! -f "$ST/b$N.gate.rc" ] && ! { [ -f "$ST/b$N.gate.pid" ] && kill -0 "$(cat "$ST/b$N.gate.pid")" 2>/dev/null; }; then
    ( cd "$WT" && nohup bash -c "uv run eng-gate check --package $member --skip mutation > $log 2>&1; echo \$? > $ST/b$N.gate.rc" >/dev/null 2>&1 & echo $! >"$ST/b$N.gate.pid" )
  fi
  t=0
  while [ $t -lt $WAIT ] && [ ! -f "$ST/b$N.gate.rc" ]; do sleep 5; t=$((t + 5)); done
  [ -f "$ST/b$N.gate.rc" ] || { echo "RUNNING gate after merge: run this command again"; exit 3; }
  rc=$(cat "$ST/b$N.gate.rc")
  tail -6 "$log"
  if [ "$rc" = 0 ] && grep -q "check: pass" "$log"; then echo "GATE_PASS log=$log"; exit 0; fi
  echo "GATE_FAIL log=$log"; exit 1
  ;;
push)
  have_lock || { echo "ERROR lock not held: run merge first"; exit 2; }
  br=$(branch)
  for i in 1 2 3 4; do
    if git -C "$WT" push -q -u origin "$br" 2>"$L/logs/b$N-push.log"; then echo "PUSHED branch=$br head=$(git -C "$WT" rev-parse HEAD)"; exit 0; fi
    sleep $((2 ** i))
  done
  tail -3 "$L/logs/b$N-push.log"; echo "PUSH_FAILED"; exit 1
  ;;
body)
  [ -s "$BODY" ] || { echo "ERROR no pull request body file $BODY (the writer writes it)"; exit 2; }
  if ! grep -q '^## Review' "$BODY"; then
    { printf '\n## Review\n\n- Written by a subagent of the lead.\n\n'; cat "$L/reports/b$N-review.md" 2>/dev/null || echo "(no review record found)"; } >>"$BODY"
  fi
  for k in '^Work-Item: B-' '^Plan-Task: ' '^Risk: '; do grep -q "$k" "$BODY" || { echo "ERROR the body lacks the line $k"; exit 2; }; done
  echo "BODY=$BODY"; echo "TITLE=$(title)"; echo "BRANCH=$(branch)"
  ;;
ci)
  PR=${3:?pull request number}
  have_lock || { echo "ERROR lock not held: run merge first"; exit 2; }
  T=$(title); [ -n "$T" ] || { echo "ERROR no title: write it to $L/pr/b$N-title.txt"; exit 2; }
  head=$(git -C "$WT" rev-parse HEAD); br=$(branch)
  if [ ! -s "$ST/b$N.rundir" ]; then
    python3 - "$PR" "$T" "$BODY" "$br" "$head" "$L/pr/b$N-pr.json" <<'PY'
import json, sys
n, title, body, ref, sha, out = sys.argv[1:7]
json.dump({"number": int(n), "title": title, "body": open(body, encoding="utf-8").read(), "draft": False,
           "user": {"login": "AbdulkareemSasah"}, "labels": [], "head": {"ref": ref, "sha": sha},
           "base": {"ref": "build/v1"}}, open(out, "w", encoding="utf-8"))
PY
    out=$(cd "$B" && python3 ops/localci.py start --pr-json "$L/pr/b$N-pr.json" 2>&1); rc=$?
    echo "$out" | tail -4
    case $rc in
      0) echo "$out" | sed -n 's/^RUN_DIR=//p' | tail -1 >"$ST/b$N.rundir" ;;
      4) echo "BEHIND build/v1 moved since the merge step: start again from: integrate.sh merge $N"; exit 7 ;;
      5) exit 4 ;;
      *) exit 6 ;;
    esac
  fi
  rd=$(cat "$ST/b$N.rundir")
  out=$(cd "$B" && python3 ops/localci.py wait --run-dir "$rd" --max $WAIT 2>&1); rc=$?
  case $rc in
    3) echo "$out" | tail -1; exit 3 ;;
    4) echo "$out" | tail -2; rm -f "$ST/b$N.rundir"; echo "BEHIND start again from: integrate.sh merge $N"; exit 7 ;;
    5) echo "$out" | tail -2; exit 4 ;;
    0)
      phead=$(echo "$out" | sed -n 's/^LOCAL-CI PASS head=\([0-9a-f]*\).*/\1/p' | tail -1)
      [ -n "$phead" ] || phead=$head
      if [ "$phead" != "$head" ]; then git -C "$WT" fetch -q origin "$br" && git -C "$WT" merge -q --ff-only "origin/$br" 2>/dev/null; fi
      if ! grep -q '^## Local CI' "$BODY"; then
        { printf '\n## Local CI\n\n'; cat "$rd/summary.md"
          grep -q 'Not run in the container' "$rd/summary.md" || printf '\nNot run in the container: the dependency audit (`uv audit --locked`; api.osv.dev is outside AGENTS.md section 9 allowed services) and the windows job (no Windows here). Both are owner local-test items (LOCAL-TESTING.md).\n'; } >>"$BODY"
      fi
      echo "PASS HEAD=$phead BODY=$BODY RUN_DIR=$rd TITLE=$T"; exit 0 ;;
    *) echo "$out" | tail -40; echo "CI_FAIL run_dir=$rd"; exit 1 ;;
  esac
  ;;
finish)
  if [ -s "$ST/b$N.rundir" ]; then (cd "$B" && python3 ops/localci.py release --run-dir "$(cat "$ST/b$N.rundir")" 2>&1 | tail -1); rm -f "$ST/b$N.rundir"; fi
  git -C "$B" fetch -q origin build/v1 && git -C "$B" checkout -q --detach origin/build/v1 2>/dev/null
  touch "$REL"; rm -f "$OWNER" "$LK/prio-wait.b$N" "$ST/b$N.gate.rc" "$ST/b$N.gate.pid"
  echo "FINISHED lock released; build/v1 is at $(git -C "$B" rev-parse --short origin/build/v1)"
  ;;
status)
  echo "lock_held=$(have_lock && echo yes || echo no) rundir=$(cat "$ST/b$N.rundir" 2>/dev/null) head=$(git -C "$WT" rev-parse --short HEAD 2>/dev/null) branch=$(branch 2>/dev/null)"
  ;;
*) echo "unknown command $cmd"; exit 2 ;;
esac
