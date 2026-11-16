#!/usr/bin/env python3
"""Local CI for the v1 build (lead decision D-23, owner instruction 2026-11-04: GitHub Actions is unavailable without a
paid plan, so CI runs in the container and the result goes to GitHub). It reproduces .github/workflows/ci.yml:

  pull request mode: the head commit checked out with the base commit at .gate-base, each composite action's command
  (the base variant when the base has the action, the head variant otherwise), GITHUB_ACTIONS=true and a pull_request
  event file, so the gate is as strict as in GitHub Actions. Jobs: gate-check, risk-floor, test-first, agents-drift,
  ci-review, security (secret scan), build, gate (check --all --skip mutation and the spike checks).
  push mode: build/v1 after merges: gate, agents-drift, security (secrets --tree), build.
  Mutation step (owner decision 2026-11-15): a pull request run does not run it (it ran on the same code before the pull
  request was opened); the push run on build/v1, done after every ten merges, runs the full check --all with it.

Not run here, reported in every summary: the dependency audit (uv audit contacts api.osv.dev, which is outside the
allowed services of AGENTS.md section 9 and is denied by the container's network policy) and the windows job.

Commands (all print KEY=VALUE lines and a final verdict line):
  start --pr-json FILE   FILE: the pull request as returned by the GitHub API (number, title, body, draft, user.login,
                         labels, head.ref, head.sha, base.ref). Fetches the head and build/v1, refuses when the head is
                         not on GitHub yet (HEAD_MISMATCH), is behind build/v1 (BEHIND: update the branch first) or
                         conflicts with it (CONFLICT); otherwise starts the run in the background (STARTED), or reports
                         one already running or done for the same head and base.
  wait --run-dir DIR [--max SECONDS]   waits up to SECONDS (default 100) and prints LOCAL-CI PASS|FAIL|RUNNING.
                         Exit 0 PASS, 1 FAIL, 3 still running.
  run --event FILE --out DIR           the run itself (start calls it); one run at a time (a lock).
  push --sha SHA --out DIR             push mode on a build/v1 commit (foreground).

Batches (owner decision of 2026-11-16, work item B-539): the run that takes the lock (the leader) looks for companions,
other pull request runs that wait for the lock (status.txt, a live pid, no `single` marker; the newest run of each pull
request number, oldest first, up to LOCALCI_BATCH_MAX - 1; default 3, 1 switches batching off). With none it is the
classic single run, unchanged. With companions every member gets the single run's pre-steps and every job but gate on its
own merged tree; the members that pass are merged one after the other onto the base (the batch tree, the tree build/v1
has after their squash merges) and the gate job runs once on it (leader folder, subfolder batch/). PASS: every member
gets PASS with a `batch` object in result.json and one more sentence in summary.md, and the leader holds the lock until
every member merged or was released (ten minutes at most). The batch guarantees that the final tree passed the gate only
when every member of the batch merges: all PASS members of one batch are merged or none is (a member left out puts on
build/v1 a tree the gate never saw as a whole; the hold then writes `batch-incomplete.txt`). The states between the
squash merges of one batch are not tested singly. The batch tree is built with plain merges, without the union merge
that auto_union uses for CHANGELOG.md, because GitHub's squash merges use plain merges too (the repository has no
.gitattributes): two members that append to the same CHANGELOG.md do not merge plainly, would conflict on GitHub at the
second squash merge, and so are never batched together. A member that does not merge plainly onto the base and the
members before it is taken out before its jobs run; a member whose merge into the batch tree conflicts after the jobs,
every companion after a batch gate FAIL, and every companion after an error in the batch code goes back to waiting with
the `single` marker and is tested alone by its own process; the leader then runs alone. A leader with a CONFLICT verdict
does not look for companions, and a leader that fails a job gives every companion back untested (without `single`).
Marker files in a run folder: `batched` (a leader took the run into its batch; with result.json, the verdict it wrote,
which the run's own process takes over when it gets the lock: a PASS stands while batch_current() holds, else the run
tests again; a PASS of a pull request that has merged or has `released` is printed and never tested again), `single`
(never batch this run), `released` (the merge step is done), `batch-verified` and `batch-tree-mismatch.txt` (build/v1's
tree after the members' squash merges against the batch tree), `batch-incomplete.txt` (the hold ended with a member not
merged; with a LOCAL-CI BATCH_INCOMPLETE line), `batch-error.log` (leader folder: an error in the batch code, after which
the leader ran alone). A companion counts as waiting only when its `pid` names a live `localci.py run` process for its
own folder (a reused pid does not count) and it is the newest run folder of its pull request number.
"""
import argparse, fcntl, hashlib, json, os, pathlib, re, subprocess, sys, time

REPO = pathlib.Path(__file__).resolve().parent.parent  # the repository root (this file lives in ops/)
HERE = pathlib.Path(os.environ.get("LOCALCI_HOME", REPO / ".localci"))  # run state, outside version control
HERE.mkdir(parents=True, exist_ok=True)
LOCK = HERE / "localci.lock"
RUNS = HERE / "runs"
PR_JOBS = ["gate-check", "risk-floor", "test-first", "agents-drift", "ci-review", "security", "build", "gate"]
PUSH_JOBS = ["agents-drift", "security", "build", "gate"]
WAITING = "waiting for the local CI lock (another run is in progress)\n"
# a lead state commit (subject "docs(build)...") that touches only these files does not change what the gate tests
STATE_FILES = ("BUILD-STATUS.md", "HANDOFF.md", "LOCAL-TESTING.md", "ops/remaining-tasks.json")
STATE_DIRS = ("docs/build/",)
NOT_RUN = ("Not run in the container: the dependency audit (`uv audit --locked`; api.osv.dev is outside AGENTS.md "
           "section 9 and denied by the network policy) and the windows job (no Windows here). Both are owner "
           "local-test items (LOCAL-TESTING.md).")


def git(*args, check=True):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=check)


def sh(cmd, cwd, env, log, timeout):
    t0 = time.time()
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n$ {cmd}\n")
        f.flush()
        try:
            code = subprocess.run(["bash", "-c", cmd], cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT,
                                  timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            f.write(f"\nTIMEOUT after {timeout} s\n")
            code = 124
    return code, round(time.time() - t0)


def tail(path, n=60):
    lines = pathlib.Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    keep = [l for l in lines if any(k in l for k in ("[error]", "error", "Error", "FAIL", "fail", "TIMEOUT", "assert"))]
    return "\n".join((keep or lines)[-n:])


def ci_env(out, event_name, event_path):
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "GITHUB_STEP_SUMMARY", "GITHUB_TOKEN")}
    env.update(GITHUB_ACTIONS="true", CI="true", GITHUB_EVENT_NAME=event_name, GITHUB_REPOSITORY="AbdulkareemSasah/Eng-Agent",
               GITHUB_STEP_SUMMARY=str(out / "step-summary.md"), TMPDIR_BUILD=str(out / "dist"))
    if event_path:
        env["GITHUB_EVENT_PATH"] = str(event_path)
    (out / "step-summary.md").touch()
    return env


def commands(wt, base, push, skip_mutation=False):
    def has(job):
        return (wt / ".gate-base" / "tools/eng-dev-gate/actions" / job / "action.yml").is_file()

    def gate(job, sub):
        if not push and has(job):
            return f"uv run -q --project .gate-base --package eng-dev-gate eng-gate --root . --gate-root .gate-base {sub}"
        return f"uv run -q eng-gate {sub}"

    scan = "secrets --tree" if push else f"secrets --range {base}..HEAD"
    return {
        "gate-check": gate("gate-check", "gate-check"),
        "risk-floor": gate("risk-floor", "risk-floor"),
        "test-first": gate("test-first", "test-first"),
        "agents-drift": gate("agents-drift", "agents drift"),
        "ci-review": gate("ci-review", "review"),
        "security": gate("security", scan),
        "build": f"names=$({gate('build', 'packages --names')}) && [ -n \"$names\" ] && while IFS= read -r name; do "
                 "uv build -q --package \"$name\" -o \"$TMPDIR_BUILD\" || exit 1; done <<< \"$names\"",
        "gate": gate("gate", "check --all --skip mutation" if skip_mutation else "check --all") +
                " && shopt -s nullglob && for f in spikes/*/check.py; do "
                "echo \"== $f\"; uv run -q --script \"$f\" || exit 1; done",
    }


def execute(out, head, base, event_name, event_path, jobs, timeout):
    """Check out head (and base at .gate-base in pull request mode), run the jobs, clean up; return the results."""
    tag = f"localci-{event_name}-{head[:10]}-{os.getpid()}"
    wt = HERE / "worktrees" / tag
    env = ci_env(out, event_name, event_path)
    results = {}
    try:
        git("worktree", "add", "-q", "--detach", str(wt), head)
        if base and git("merge-base", "--is-ancestor", base, head, check=False).returncode != 0:
            # the squash merge applies the pull request onto the latest build/v1: test exactly that tree, as a local
            # merge commit (never pushed); the event names it as the head, so every job judges the merged tree
            subprocess.run(["git", "-C", str(wt), "-c", "user.name=localci", "-c", "user.email=localci@localhost", "merge",
                            "--no-ff", "--no-edit", "-q", base], check=True, capture_output=True, text=True)
            tested = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], check=True, capture_output=True,
                                    text=True).stdout.strip()
            ev = json.loads(pathlib.Path(event_path).read_text(encoding="utf-8"))
            ev["pull_request"]["head"]["sha"], ev["pull_request"]["base"]["sha"] = tested, base
            event_path = out / "event-tested.json"
            event_path.write_text(json.dumps(ev, indent=1), encoding="utf-8")
            env["GITHUB_EVENT_PATH"] = str(event_path)
            results["merged"] = dict(exit=0, seconds=0, tail="", tested=tested)
        if base:
            git("worktree", "add", "-q", "--detach", str(wt / ".gate-base"), base)
        setup = "uv sync --all-packages --locked -q"
        if base:
            setup += " && uv sync --project .gate-base --package eng-dev-gate --locked -q"
        code, secs = sh(setup, wt, env, out / "setup.log", 1800)
        results["setup"] = dict(exit=code, seconds=secs, tail=tail(out / "setup.log") if code else "")
        if code == 0:
            cmds = commands(wt, base, event_name == "push", skip_mutation=event_name != "push")
            for job in jobs:
                (out / "status.txt").write_text(f"running {job}\n")
                code, secs = sh(cmds[job], wt, env, out / f"{job}.log", timeout)
                results[job] = dict(exit=code, seconds=secs, tail=tail(out / f"{job}.log") if code else "")
    except subprocess.CalledProcessError as e:
        results["setup"] = dict(exit=1, seconds=0, tail=(e.stderr or str(e))[-2000:])
    finally:
        if base:
            git("worktree", "remove", "--force", str(wt / ".gate-base"), check=False)
        git("worktree", "remove", "--force", str(wt), check=False)
        git("worktree", "prune", check=False)
    return results


def finish(out, mode, head, base, results, jobs, started, batch=None, note=None):
    failing = [j for j, r in results.items() if r.get("exit", 1) != 0]
    verdict = "PASS" if not failing and all(j in results for j in jobs) else "FAIL"
    tested = (results.get("merged") or {}).get("tested")
    doc = dict(verdict=verdict, mode=mode, head=head, base=base, jobs=results, failing=failing,
               started_at=started, finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    if batch:
        doc["batch"] = batch
    (out / "result.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    against = f" against base {base[:7]}" if base else ""
    if tested:
        against += f" (merged locally with that base as {tested[:7]}, the tree the squash merge produces)"
    lines = [f"Local CI in the build container (lead decision D-23): **{verdict}** on head {head[:7]}{against}, "
             f"{mode} mode, finished {doc['finished_at']}.", "", "| Job | Result | Seconds |", "|---|---|---|"]
    lines += [f"| {j} | {'pass' if r.get('exit') == 0 else 'FAIL (exit %s)' % r.get('exit')} | {r.get('seconds', '-')} |"
              for j, r in results.items() if j != "merged"]
    if note:
        lines += ["", note]
    mutation = ("Mutation step: run" if mode == "push" else "Mutation step: not run in this pull request run (owner "
                "decision of 2026-11-15); it runs on build/v1 after every ten merges")
    lines += ["", mutation, "", NOT_RUN]
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "status.txt").write_text(f"done {verdict}\n")
    return verdict, failing


def conflicts(head, base):
    """None when head merges cleanly with base (or contains it), else the conflicting paths."""
    if git("merge-base", "--is-ancestor", base, head, check=False).returncode == 0:
        return None
    mt = subprocess.run(["git", "-C", str(REPO), "merge-tree", "--write-tree", "--name-only", "--no-messages", base, head],
                        capture_output=True, text=True)
    return [l for l in mt.stdout.splitlines()[1:] if l.strip()] if mt.returncode == 1 else None


UNION_ATTRS = HERE / "union.attributes"
if not UNION_ATTRS.exists():  # git union merge for the files every task appends a line to
    UNION_ATTRS.write_text("**/CHANGELOG.md merge=union\nCHANGELOG.md merge=union\n**/docs/local-testing.md merge=union\n", encoding="utf-8")


def auto_union(event, base):
    """Merge base into a pull request head whose only conflicts are CHANGELOG.md files, keeping both sides' lines (git's
    union merge), and push the merge commit to the pull request's branch. Returns the new head, or None when another file
    conflicts, the merge fails or the branch moved (the conflict then goes to a writer)."""
    pr = event["pull_request"]
    head, branch = pr["head"]["sha"], pr["head"].get("ref", "")
    files = conflicts(head, base)
    both = ratchet_changed_on_both_sides(head, base)
    if not branch or (not files and not both):
        return None
    if files and not all(mechanical(f) for f in files):
        return None
    files = files or [".gate/ratchet.json (changed on both sides)"]
    m = re.search(r"\((B-\d{3}[a-z]?)\)", pr.get("title", ""))
    item = m.group(1) if m else "the pull request's work item"
    wt = HERE / "worktrees" / f"localci-union-{pr['number']}-{os.getpid()}"
    message = (f"Merge build/v1 into {branch} ({item}): CHANGELOG lines of both sides kept\n\n"
               f"The lead's local CI (D-23) merged build/v1 {base[:7]} into the head {head[:7]}; the only conflicts were in "
               f"{', '.join(files)}: CHANGELOG.md and docs/local-testing.md by keeping both sides' lines (git union merge), .gate/ratchet.json by the three-way sum "
               "of each count, a member pyproject.toml by appending the pull request's new module or dependency list items to build/v1's lists; "
               "confirmed by the gate's ratchet and config steps. No other file changed.\n\n"
               + os.environ.get("LOCALCI_TRAILERS", "Assisted-by: local CI (ops/localci.py)") + "\n")
    try:
        git("worktree", "add", "-q", "--detach", str(wt), head)
        r = subprocess.run(["git", "-C", str(wt), "-c", f"core.attributesFile={UNION_ATTRS}", "-c", f"user.name={os.environ.get('LOCALCI_GIT_NAME', 'Local CI')}", "-c",
                            f"user.email={os.environ.get('LOCALCI_GIT_EMAIL', 'noreply@localhost')}", "merge", "--no-ff", "-q", "-m", message, base],
                           capture_output=True, text=True)
        if r.returncode != 0:
            # the CHANGELOGs merged by union; a ratchet conflict gets the three-way sum of each count, checked by the gate
            left = subprocess.run(["git", "-C", str(wt), "diff", "--name-only", "--diff-filter=U"], capture_output=True,
                                  text=True).stdout.split()
            done = []
            for f in left:
                if f.endswith("pyproject.toml") and resolve_pyproject(wt, f):
                    done.append(f)
            if ".gate/ratchet.json" in left:
                if resolve_ratchet(wt):  # runs uv sync and the gate's ratchet step on the merged tree
                    done.append(".gate/ratchet.json")
            if sorted(done) != sorted(left) or not config_ok(wt, [f for f in done if f.endswith("pyproject.toml")]):
                subprocess.run(["git", "-C", str(wt), "merge", "--abort"], capture_output=True)
                return None
            subprocess.run(["git", "-C", str(wt), "add", *done], check=True, capture_output=True)
            c = subprocess.run(["git", "-C", str(wt), "-c", f"user.name={os.environ.get('LOCALCI_GIT_NAME', 'Local CI')}", "-c", f"user.email={os.environ.get('LOCALCI_GIT_EMAIL', 'noreply@localhost')}", "commit",
                                "-q", "--no-edit"], capture_output=True, text=True)
            if c.returncode != 0:
                subprocess.run(["git", "-C", str(wt), "merge", "--abort"], capture_output=True)
                return None
        if both and r.returncode == 0:
            # a clean merge of two count changes keeps one side's line: put the three-way sum in the merge commit
            mb = git("merge-base", head, base).stdout.strip()
            if not resolve_ratchet(wt, (mb, head, base)):
                return None
            subprocess.run(["git", "-C", str(wt), "add", ".gate/ratchet.json"], check=True, capture_output=True)
            amend = subprocess.run(["git", "-C", str(wt), "-c", f"user.name={os.environ.get('LOCALCI_GIT_NAME', 'Local CI')}", "-c", f"user.email={os.environ.get('LOCALCI_GIT_EMAIL', 'noreply@localhost')}", "commit",
                                    "-q", "--amend", "--no-edit"], capture_output=True, text=True)  # the local merge commit, not yet pushed
            if amend.returncode != 0:
                return None
        new = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        changed = subprocess.run(["git", "-C", str(wt), "diff", "--name-only", f"{head}..{new}", "--", "."], capture_output=True,
                                 text=True).stdout.split()
        pushed = subprocess.run(["git", "-C", str(wt), "push", "-q", "origin", f"{new}:refs/heads/{branch}"], capture_output=True, text=True)
        if pushed.returncode != 0:
            return None
        return new
    finally:
        git("worktree", "remove", "--force", str(wt), check=False)
        git("worktree", "prune", check=False)


LIST_KEYS = ("public_modules", "r1_modules", "r2_modules", "block_modules", "rule_modules", "calc_modules", "windows_tests")


def mechanical(path):
    """Conflicts the run resolves itself: lists of lines, the ratchet counts and a member's pyproject.toml lists."""
    return (path.endswith("CHANGELOG.md") or path.endswith("docs/local-testing.md") or path == ".gate/ratchet.json"
            or (path.endswith("/pyproject.toml") and path.count("/") >= 2))


def _flat(doc, prefix=()):
    out = {}
    for k, v in doc.items():
        key = prefix + (k,)
        out.update(_flat(v, key) if isinstance(v, dict) else {key: v})
    return out


def resolve_pyproject(wt, path):
    """A member pyproject.toml where the pull request only added items to the gate's module lists or to the project
    dependencies: keep build/v1's file and append the pull request's new items to those lists. Anything else, or a
    result that does not parse to exactly that, leaves the conflict to a writer."""
    import tomllib
    def stage(n):
        r = subprocess.run(["git", "-C", str(wt), "show", f":{n}:{path}"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None
    base_t, ours_t, theirs_t = stage(1), stage(2), stage(3)
    if not (base_t and ours_t and theirs_t):
        return False
    try:
        base, ours, theirs = (tomllib.loads(t) for t in (base_t, ours_t, theirs_t))
    except tomllib.TOMLDecodeError:
        return False
    fb, fo, ft = _flat(base), _flat(ours), _flat(theirs)
    listkeys = {k for k in set(fb) | set(fo) if (k[-1] in LIST_KEYS and k[:2] == ("tool", "eng-gate")) or k == ("project", "dependencies")}
    for k in set(fb) | set(fo):
        if k not in listkeys and fb.get(k) != fo.get(k):
            return False  # the pull request changed something other than a list: a writer's job
    text, expected = theirs_t, dict(ft)
    for k in sorted(listkeys):
        added = [x for x in fo.get(k, []) if x not in fb.get(k, [])]
        if fo.get(k, []) and set(fb.get(k, [])) - set(fo.get(k, [])):
            return False  # the pull request removed list items
        new = [x for x in added if x not in ft.get(k, [])]
        if not new:
            continue
        m = re.search(rf"(?m)^(\s*{re.escape(k[-1])}\s*=\s*\[)(.*?)(\])", text, re.S)
        if not m or k not in ft:
            return False
        inner = m.group(2)
        items = ", ".join(json.dumps(x) for x in new)
        if "\n" in inner:
            indent = re.search(r"\n(\s*)\S", inner)
            pad = indent.group(1) if indent else "    "
            body = inner.rstrip()
            sep = "" if body.endswith(",") else ","
            joined = body + sep + "\n" + "".join(f"{pad}{json.dumps(x)},\n" for x in new) + inner[len(inner.rstrip()):].lstrip(",")
            replacement = m.group(1) + joined + m.group(3)
        else:
            replacement = m.group(1) + (inner.rstrip() + ", " if inner.strip() else "") + items + m.group(3)
        text = text[:m.start()] + replacement + text[m.end():]
        expected[k] = list(ft.get(k, [])) + new
    try:
        if _flat(tomllib.loads(text)) != expected:
            return False
    except tomllib.TOMLDecodeError:
        return False
    (wt / path).write_text(text, encoding="utf-8")
    return True


def config_ok(wt, pyprojects):
    """The gate's lock and config steps accept every resolved member pyproject.toml (public modules exist, globs valid)."""
    import tomllib
    for path in pyprojects:
        member = tomllib.loads((wt / path).read_text(encoding="utf-8"))["project"]["name"]
        r = subprocess.run(["bash", "-c", f"uv sync -q --all-packages && uv run -q eng-gate check --package {member} --only config"],
                           cwd=str(wt), capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            return False
    return True


def ratchet_changed_on_both_sides(head, base):
    """Whether the pull request and build/v1 both changed .gate/ratchet.json since their merge base."""
    mb = git("merge-base", head, base, check=False).stdout.strip()
    if not mb:
        return False
    def changed(a, b):
        return git("diff", "--quiet", a, b, "--", ".gate/ratchet.json", check=False).returncode == 1
    return changed(mb, head) and changed(mb, base)


def resolve_ratchet(wt, commits=None):
    """Write the three-way sum of every count into .gate/ratchet.json (base, ours, theirs: from the index after a conflict,
    or from the given merge-base, head and build/v1 commits after a clean merge of identical edits) in the one-line form
    of build/v1, then require the gate's ratchet step to pass; False leaves it to a writer."""
    def stage(n):
        spec = f"{commits[n - 1]}:.gate/ratchet.json" if commits else f":{n}:.gate/ratchet.json"
        r = subprocess.run(["git", "-C", str(wt), "show", spec], capture_output=True, text=True)
        return json.loads(r.stdout)["counts"] if r.returncode == 0 else {}
    try:
        base, ours, theirs = stage(1), stage(2), stage(3)
    except ValueError:
        return False
    merged = {}
    for package in sorted(set(base) | set(ours) | set(theirs)):
        b, o, t = base.get(package, {}), ours.get(package, {}), theirs.get(package, {})
        counts = {key: o.get(key, 0) + t.get(key, 0) - b.get(key, 0) for key in sorted(set(b) | set(o) | set(t))}
        if any(v < 0 for v in counts.values()):
            return False
        merged[package] = {k: v for k, v in counts.items() if v or k in t or k in o}
    order = list(theirs) + [p for p in merged if p not in theirs]  # build/v1's order, new packages after it
    doc = {"version": 1, "counts": {p: merged[p] for p in order if p in merged}}
    (wt / ".gate" / "ratchet.json").write_text(json.dumps(doc), encoding="utf-8")
    sync = subprocess.run(["bash", "-c", "uv sync -q --all-packages --locked && uv run -q eng-gate ratchet"], cwd=str(wt),
                          capture_output=True, text=True, timeout=900)
    return sync.returncode == 0


def tip():
    for attempt in range(4):
        if git("fetch", "-q", "origin", "build/v1", check=False).returncode == 0:
            break
        time.sleep(2 ** (attempt + 1))
    return git("rev-parse", "origin/build/v1").stdout.strip()


def prepare(out, event_path, base, started):
    """The pre-steps of a run under the lock, against base: a mechanical conflict (CHANGELOG.md, the ratchet, a member's
    pyproject.toml lists) merged and pushed by auto_union, the event's base sha set to base. Returns (head, files): files
    is None when the head merges with base, else the conflicting paths (the CONFLICT verdict is then in out)."""
    head = json.loads(event_path.read_text(encoding="utf-8"))["pull_request"]["head"]["sha"]
    files = conflicts(head, base)
    if files is not None or ratchet_changed_on_both_sides(head, base):
        ev0 = json.loads(event_path.read_text(encoding="utf-8"))
        new = auto_union(ev0, base)
        if new is not None:
            head = new
            ev0["pull_request"]["head"]["sha"] = new
            event_path.write_text(json.dumps(ev0, indent=1), encoding="utf-8")
            (out / "auto-merge.txt").write_text(f"CHANGELOG-only conflict merged with build/v1 {base} and pushed {new}\n")
            files = conflicts(head, base)
    if files is not None:
        doc = dict(verdict="CONFLICT", mode="pull_request", head=head, base=base, tip=base, files=files, jobs={},
                   failing=[], started_at=started, finished_at=started)
        (out / "result.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
        (out / "status.txt").write_text("done CONFLICT\n")
        return head, files
    ev = json.loads(event_path.read_text(encoding="utf-8"))
    if ev["pull_request"]["base"]["sha"] != base:  # build/v1 moved since the start: the event names what is tested
        ev["pull_request"]["base"]["sha"] = base
        event_path.write_text(json.dumps(ev, indent=1), encoding="utf-8")
    return head, None


def hold(out, number, base):
    """Keep the lock until this pull request has merged (build/v1 moves), the merge step releases it, or ten minutes
    pass, so the next run is tested on top of this merge. A lead commit to build/v1 (BUILD-STATUS, D-4) moves the tip
    without merging this pull request: keep holding until a commit of this pull request is on build/v1 (its squash title
    ends with "(#N)")."""
    deadline = time.time() + 600
    while time.time() < deadline and not (out / "released").exists():
        time.sleep(15)
        now = tip()
        if now != base and f"(#{number})" in git("log", "--format=%s", f"{base}..{now}", check=False).stdout:
            break


def cmd_run(a):
    out = pathlib.Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    event_path = pathlib.Path(a.event).resolve()
    with open(LOCK, "w") as lock:
        (out / "status.txt").write_text(WAITING)
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (out / "batched").is_file():  # a batch leader wrote this run's verdict while it waited
            code = stored(out, event_path)
            if code is not None:
                return code
        # the event is read under the lock: a batch leader may have pushed a merge to this pull request's branch
        pr = json.loads(event_path.read_text(encoding="utf-8"))["pull_request"]
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        base = tip()  # test on top of the latest build/v1, also when it moved while this run waited
        head, files = prepare(out, event_path, base, started)
        if files is not None:
            print(f"LOCAL-CI CONFLICT with build/v1 {base[:7]} in: {' '.join(files[:20])}")
            return 5
        verdict, failing = test(a, out, event_path, int(pr["number"]), head, base, started)
    print(f"LOCAL-CI {verdict} {' '.join(failing)}".strip())
    return 0 if verdict == "PASS" else 1


def test(a, out, event_path, number, head, base, started):
    """The tests of a run that holds the lock: a batch when other runs wait (see the module docstring), else, and after
    an error in the batch code, the classic single run (every job on the merged tree, the hold after a PASS)."""
    mates, outcome = [], None
    try:
        mates = [] if (out / "single").exists() else companions(out, number, batch_max() - 1)
        outcome = run_batch(a, out, event_path, number, head, base, started, mates) if mates else None
    except Exception:  # never lose the leader's own result to the batch code: log it and run alone
        import traceback
        with open(out / "batch-error.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n{traceback.format_exc()}\n")
        for d in mates:
            if not status_of(d).startswith("done"):
                try:
                    leave(d)
                except OSError:
                    pass
        outcome = None
    if outcome is not None:
        verdict, failing, keep = outcome
        keep()
        return verdict, failing
    (out / "status.txt").write_text("running\n")
    results = execute(out, head, base, "pull_request", event_path, PR_JOBS, a.timeout)
    verdict, failing = finish(out, "pull_request", head, base, results, PR_JOBS, started)
    if verdict == "PASS":
        hold(out, number, base)
    return verdict, failing


def batch_max():
    """LOCALCI_BATCH_MAX: the most pull requests one gate job tests (default 3; 1, or a value that is not a number,
    switches batching off)."""
    try:
        return max(1, int(os.environ.get("LOCALCI_BATCH_MAX", "3")))
    except ValueError:
        return 1


def status_of(d):
    try:
        return (d / "status.txt").read_text()
    except OSError:
        return ""


def run_alive(d):
    """Whether d's `pid` file names a live `localci.py run ... --out d` process (a reused pid or a zombie does not count)."""
    try:
        args = pathlib.Path(f"/proc/{int((d / 'pid').read_text().strip())}/cmdline").read_bytes().decode(
            errors="replace").split("\0")
        return (any(x.endswith("localci.py") for x in args) and "--out" in args[:-1]
                and pathlib.Path(args[args.index("--out") + 1]).resolve() == d.resolve())
    except (OSError, ValueError):
        return False


def companions(out, number, limit):
    """The newest run folder of each other pull request number under RUNS (any status), taken when it waits for the lock
    with a live process of its own and no `single` marker; oldest first, at most limit. Each gets the `batched` marker
    (a superseded run that still waits is never batched)."""
    found = {}
    for d in sorted(RUNS.iterdir()) if limit > 0 and RUNS.is_dir() else []:
        try:
            n = int(json.loads((d / "event.json").read_text(encoding="utf-8"))["pull_request"]["number"])
            since = (d / "pid").stat().st_mtime
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if n != number and (n not in found or since > found[n][0]):
            found[n] = (since, d)
    mates = [d for _, d in sorted(found.values()) if d.resolve() != out and status_of(d).startswith(WAITING.split(" (")[0])
             and not (d / "single").exists() and run_alive(d)][:limit]
    for d in mates:
        (d / "batched").write_text(f"{out.name}\n")
    return mates


def leave(d, single=True):
    """Give a companion back to its own process with its waiting status; with single it carries the `single` marker and
    is tested alone when that process gets the lock."""
    if single:
        (d / "single").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
    (d / "batched").unlink(missing_ok=True)
    (d / "status.txt").write_text(WAITING)


def passed(results, jobs):
    return all(j in results for j in jobs) and all(r.get("exit", 1) == 0 for r in results.values())


def run_batch(a, out, event_path, number, head, base, started, mates):
    """Test the leader (out, already through its pre-steps) and its companions as one batch. Returns None when no
    companion is left after the pre-steps (the caller runs the classic single run), else (verdict, failing, keep): the
    leader's verdict, already written, and the hold to do before the lock goes."""
    jobs = [j for j in PR_JOBS if j != "gate"]
    leader = dict(out=out, event=event_path, number=number, head=head)
    members = []
    for d in mates:  # the pre-steps of a single run against the same base; a CONFLICT verdict leaves the batch
        m_head, files = prepare(d, d / "event.json", base, started)
        if files is None:
            n = int(json.loads((d / "event.json").read_text(encoding="utf-8"))["pull_request"]["number"])
            members.append(dict(out=d, event=d / "event.json", number=n, head=m_head))
    if members:  # plain merges as GitHub's squash merges do (see the module docstring): no jobs for a member left out
        fit = batch_tree([leader] + members, base)[2]
        for m in members:
            if m not in fit:
                leave(m["out"])
        members = [m for m in members if m in fit]
    if not members:
        return None
    (out / "status.txt").write_text("running\n")
    leader["results"] = execute(out, head, base, "pull_request", event_path, jobs, a.timeout)
    if not passed(leader["results"], jobs):  # the leader fails a job: no batch, the companions wait on untested
        for m in members:
            leave(m["out"], single=False)
        verdict, failing = finish(out, "pull_request", head, base, leader["results"], PR_JOBS, started)
        return verdict, failing, lambda: None

    def alone():  # the leader's gate job on its own merged tree (its other jobs ran), then a single run's hold
        (out / "status.txt").write_text("running\n")
        gate = execute(out, head, base, "pull_request", event_path, ["gate"], a.timeout)
        results = dict(leader["results"])
        results.update({k: v for k, v in gate.items() if k == "gate" or (k == "setup" and v.get("exit"))})
        verdict, failing = finish(out, "pull_request", head, base, results, PR_JOBS, started)
        return verdict, failing, (lambda: hold(out, number, base)) if verdict == "PASS" else (lambda: None)

    kept = [leader]
    for m in members:  # every job but gate, in the member's own worktree with its own event file
        (m["out"] / "status.txt").write_text("running\n")
        m["results"] = execute(m["out"], m["head"], base, "pull_request", m["event"], jobs, a.timeout)
        if passed(m["results"], jobs):
            kept.append(m)
        else:
            finish(m["out"], "pull_request", m["head"], base, m["results"], PR_JOBS, started)
    commit, tree, inside = batch_tree(kept, base) if len(kept) > 1 else ("", "", kept)
    if not inside or inside[0] is not leader:
        raise RuntimeError(f"the leader's head {head} did not merge onto {base} in the batch tree")
    for m in kept[1:]:
        if m not in inside:
            leave(m["out"])
    if len(inside) < 2:
        return alone()
    refs = ", ".join(f"#{m['number']}" for m in inside)
    bdir = out / "batch"
    bdir.mkdir(exist_ok=True)
    info = dict(members=[m["number"] for m in inside], heads={str(m["number"]): m["head"] for m in inside},
                commit=commit, tree=tree, base=base, leader=number)
    (bdir / "batch.json").write_text(json.dumps(dict(info, taken_out=[m["number"] for m in kept if m not in inside]),
                                                indent=1), encoding="utf-8")
    for f in bdir.glob("*.log"):  # a restarted folder: the logs describe this batch only
        f.unlink()
    for m in inside:
        (m["out"] / "status.txt").write_text(f"running gate in the batch of {refs} (leader {out.name})\n")
    ev = json.loads(event_path.read_text(encoding="utf-8"))
    ev["pull_request"]["head"]["sha"], ev["pull_request"]["base"]["sha"] = commit, base
    (bdir / "event.json").write_text(json.dumps(ev, indent=1), encoding="utf-8")
    gate = execute(bdir, commit, base, "pull_request", bdir / "event.json", ["gate"], a.timeout)
    if not passed(gate, ["gate"]):  # nobody gets the batch's failure: the companions are tested alone later
        for m in inside[1:]:
            leave(m["out"])
        return alone()
    note = (f"The gate job ran once on the batch tree of pull requests {refs} merged onto base {base[:7]}, tree {tree}, "
            "which is the tree build/v1 has after these squash merges.")
    for m in inside[1:] + [leader]:
        verdict, failing = finish(m["out"], "pull_request", m["head"], base, dict(m["results"], gate=gate["gate"]),
                                  PR_JOBS, started, batch=info, note=note)
    return verdict, failing, lambda: hold_batch(inside, info)


def batch_tree(members, base):
    """A worktree at base into which the members' heads are merged one after the other (--no-ff, no edit); a member whose
    merge conflicts is taken out again (merge aborted). Returns the batch commit, its tree and the members merged. Plain
    merges, never the union attributes of auto_union: GitHub squash-merges the members with plain merges."""
    wt = HERE / "worktrees" / f"localci-batch-{base[:10]}-{os.getpid()}"
    inside = []

    def g(*args, check=True):
        return subprocess.run(["git", "-C", str(wt), "-c", "user.name=localci", "-c", "user.email=localci@localhost",
                               *args], capture_output=True, text=True, check=check)
    try:
        git("worktree", "add", "-q", "--detach", str(wt), base)
        for m in members:
            if g("merge", "--no-ff", "--no-edit", "-q", m["head"], check=False).returncode == 0:
                inside.append(m)
            else:
                g("merge", "--abort", check=False)
        return g("rev-parse", "HEAD").stdout.strip(), g("rev-parse", "HEAD^{tree}").stdout.strip(), inside
    finally:
        git("worktree", "remove", "--force", str(wt), check=False)
        git("worktree", "prune", check=False)


def log_commits(rng):
    """(sha, parents, subject) of every commit in rng, newest first, or None when git log fails. NUL-separated records
    (git log -z): no character of a subject splits a record."""
    r = git("log", "-z", "--format=%H%x00%P%x00%s", rng, check=False)
    if r.returncode != 0:
        return None
    f = r.stdout.split("\0")
    return [tuple(f[i:i + 3]) for i in range(0, len(f) - 2, 3)]


def merged_numbers(base, now):
    """The pull request numbers with a commit in base..now whose subject ends with "(#N)" (the squash merge title)."""
    if not now or now == base:
        return set()
    return {int(m.group(1)) for _, _, s in log_commits(f"{base}..{now}") or [] if (m := re.search(r"\(#(\d+)\)$", s.strip()))}


def hold_batch(members, info):
    """The leader's hold after a batch PASS: until every member's pull request has merged or has `released`, at most
    ten minutes. When every member merged, build/v1's tree after the last member's squash merge is compared with the
    batch tree: `batch-verified`, or `batch-tree-mismatch.txt` and a LOCAL-CI BATCH_TREE_MISMATCH line."""
    base, numbers = info["base"], [m["number"] for m in members]
    deadline = time.time() + 600
    done = set()
    while time.time() < deadline and not all(m["number"] in done or (m["out"] / "released").exists() for m in members):
        time.sleep(15)
        done = merged_numbers(base, tip())
    now = tip()
    merged = merged_numbers(base, now)
    refs = ", ".join(f"#{n}" for n in numbers)
    missing = [n for n in numbers if n not in merged]
    if missing:  # all PASS members of one batch are merged or none is: say so in every member folder
        text = (f"batch of {refs} on base {base}, batch tree {info['tree']}: when the hold ended "
                f"{', '.join(f'#{n}' for n in numbers if n in merged) or 'no member'} had merged and "
                f"{', '.join(f'#{n}' for n in missing)} had not; until every member merges, build/v1 holds a tree "
                "the gate did not test as a whole\n")
        for m in members:
            (m["out"] / "batch-incomplete.txt").write_text(text)
        print(f"LOCAL-CI BATCH_INCOMPLETE not merged: {', '.join(f'#{n}' for n in missing)} (batch {refs}, base {base[:7]})")
        return
    last = ""
    for sha, _, subject in log_commits(f"{base}..{now}") or []:
        m = re.search(r"\(#(\d+)\)$", subject.strip())
        if m and int(m.group(1)) in numbers:
            last = sha  # the newest member squash merge: build/v1 after all of them
            break
    tree = git("rev-parse", f"{last}^{{tree}}", check=False).stdout.strip()
    for m in members:
        if tree == info["tree"]:
            (m["out"] / "batch-verified").write_text(f"build/v1 {last} after the squash merges of {refs} has tree "
                                                     f"{tree}, the batch tree\n")
        else:
            (m["out"] / "batch-tree-mismatch.txt").write_text(
                f"batch tree {info['tree']} (batch commit {info['commit']} on base {base})\n"
                f"build/v1 tree {tree} at {last} after the squash merges of {refs}\n")
    if tree != info["tree"]:
        print(f"LOCAL-CI BATCH_TREE_MISMATCH batch tree {info['tree']}, build/v1 tree {tree} at {last[:7]} ({refs})")


def batch_current(doc, now):
    """Whether a batch PASS (a result with a `batch` object) still stands on the build/v1 commit now. The rule, kept
    conservative: now descends from the batch base and every commit in base..now has one parent and is either
      1. the squash merge of a member of the batch: its subject ends with "(#N)" for a member N not seen before in the
         range, and its tree is exactly the merge of that member's tested head into its parent (git merge-tree), or
      2. a lead state commit: its subject starts with "docs(build)" and it touches only STATE_FILES or files under
         STATE_DIRS, which the gate does not test (the author is not checked: the files are what matters).
    Anything else (another pull request, a merge commit, a member merged at another head, a rewritten build/v1) makes the
    result stale."""
    batch, base = doc.get("batch") if doc.get("verdict") == "PASS" else None, doc.get("base") or ""
    if not batch or not now or not base:
        return False
    if now == base:
        return True
    if git("merge-base", "--is-ancestor", base, now, check=False).returncode != 0:
        return False
    heads, seen = {int(n): h for n, h in (batch.get("heads") or {}).items()}, set()
    log = log_commits(f"{base}..{now}")
    if log is None:
        return False
    for sha, parents, subject in log:
        if len(parents.split()) != 1:
            return False
        m = re.search(r"\(#(\d+)\)$", subject.strip())
        n = int(m.group(1)) if m else None
        if n in heads and n not in seen:
            mt = git("merge-tree", "--write-tree", parents, heads[n], check=False)
            if mt.returncode != 0 or mt.stdout.split()[:1] != [git("rev-parse", f"{sha}^{{tree}}").stdout.strip()]:
                return False
            seen.add(n)
            continue
        paths = git("diff-tree", "--no-commit-id", "--name-only", "-r", sha, check=False).stdout.splitlines()
        if not (subject.startswith("docs(build)") and paths
                and all(p in STATE_FILES or p.startswith(STATE_DIRS) for p in paths)):
            return False
    return True


def stored(out, event_path):
    """The run's own process got the lock after a batch leader wrote its verdict (marker `batched`, which the process
    takes over and removes). CONFLICT and FAIL stand as written. A batch PASS for the event's head stands while
    batch_current() holds: the verdict is printed and, when the pull request has not merged yet, the lock is held as a
    single run holds it; nothing is tested again. A PASS of a pull request that has merged or has `released` stands as
well (printed, no hold, no test). Otherwise the result is stale: it is removed and None returned (the
    caller goes on as a normal run on the new base)."""
    (out / "batched").unlink(missing_ok=True)
    try:
        doc = json.loads((out / "result.json").read_text(encoding="utf-8"))
        pr = json.loads(event_path.read_text(encoding="utf-8"))["pull_request"]
    except (OSError, ValueError, KeyError):
        return None
    if doc.get("head") == pr["head"]["sha"]:
        if doc.get("verdict") == "CONFLICT":
            print(f"LOCAL-CI CONFLICT with build/v1 {doc['base'][:7]} in: {' '.join(doc.get('files', [])[:20])}")
            return 5
        if doc.get("verdict") == "FAIL":
            print(f"LOCAL-CI FAIL {' '.join(doc.get('failing', []))}".strip())
            return 1
        now = tip()
        # staleness matters only before the merge: a pull request that has merged or was released is not tested again
        done = int(pr["number"]) in merged_numbers(doc["base"], now) or (out / "released").exists()
        if done or batch_current(doc, now):
            if not done:
                hold(out, int(pr["number"]), doc["base"])
            print("LOCAL-CI PASS")
            return 0
    (out / "status.txt").write_text("running\n")
    (out / "result.json").unlink(missing_ok=True)
    return None


def cmd_push(a):
    out = pathlib.Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    git("fetch", "-q", "origin", "build/v1")
    sha = git("rev-parse", a.sha).stdout.strip()
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        results = execute(out, sha, None, "push", None, PUSH_JOBS, a.timeout)
        verdict, failing = finish(out, "push", sha, None, results, PUSH_JOBS, started)
    print(f"LOCAL-CI {verdict} {' '.join(failing)}".strip())
    return 0 if verdict == "PASS" else 1


def cmd_start(a):
    pr = json.loads(pathlib.Path(a.pr_json).read_text(encoding="utf-8"))
    n, head = int(pr["number"]), pr["head"]["sha"]
    base_ref = pr.get("base", {}).get("ref", "build/v1")
    if base_ref != "build/v1":
        print(f"LOCAL-CI REFUSED base is {base_ref}, not build/v1")
        return 2
    for attempt in range(4):
        r = subprocess.run(["git", "-C", str(REPO), "fetch", "-q", "origin", "build/v1", f"+refs/pull/{n}/head:refs/localci/pr-{n}"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            break
        time.sleep(2 ** (attempt + 1))
    else:
        print(f"LOCAL-CI ERROR git fetch failed: {r.stderr.strip()[-500:]}")
        return 2
    fetched = git("rev-parse", f"refs/localci/pr-{n}").stdout.strip()
    if fetched != head:
        print(f"LOCAL-CI HEAD_MISMATCH GitHub's pull/{n}/head is {fetched}, the pull request JSON says {head}: read the pull request again")
        return 2
    base = git("rev-parse", "origin/build/v1").stdout.strip()
    files = conflicts(head, base)
    # start stays fast: conflicts in CHANGELOG.md and .gate/ratchet.json only (and two count changes git would merge
    # silently) are resolved by the run itself, under the lock, before it tests; anything else is a writer's conflict
    if files is not None and not all(mechanical(f) for f in files):
        print(f"LOCAL-CI CONFLICT with build/v1 {base[:7]} in: {' '.join(files[:20])}")
        return 5
    # the title and body are gate inputs (test-first reads the type, gate-check the Work-Item, Plan-Task and Risk lines)
    inputs = hashlib.sha256((pr.get("title", "") + "\n" + (pr.get("body") or "")).encode("utf-8")).hexdigest()[:8]
    run_dir = RUNS / f"pr{n}-{head[:10]}-{inputs}"
    print(f"RUN_DIR={run_dir}")
    status = (run_dir / "status.txt").read_text().strip() if (run_dir / "status.txt").is_file() else ""
    pid_file = run_dir / "pid"
    alive = False
    if pid_file.is_file():
        try:
            os.kill(int(pid_file.read_text().strip()), 0)
            alive = True
        except (OSError, ValueError):
            alive = False
    if status.startswith("done") and status.split()[1] in ("PASS", "FAIL"):
        prior = json.loads((run_dir / "result.json").read_text(encoding="utf-8")) if (run_dir / "result.json").is_file() else {}
        if prior.get("base") == base or batch_current(prior, base):
            print(f"LOCAL-CI ALREADY_DONE {status.split()[1]}")
            return 0
    if alive and not status.startswith("done"):
        print("LOCAL-CI ALREADY_RUNNING")
        return 0
    if alive and (run_dir / "batched").is_file():
        # a batch leader wrote this verdict while the run's own process still waits for the lock, and build/v1 has moved
        # past it: that process tests again when it gets the lock (never a second process for one folder)
        (run_dir / "status.txt").write_text(WAITING)
        for f in ("result.json", "batched"):
            (run_dir / f).unlink(missing_ok=True)
        print("LOCAL-CI ALREADY_RUNNING")
        return 0
    for f in ("result.json", "released", "single", "batched", "batch-verified", "batch-tree-mismatch.txt",
              "batch-incomplete.txt"):
        (run_dir / f).unlink(missing_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    event = {"action": "synchronize", "number": n, "pull_request": {
        "number": n, "title": pr.get("title", ""), "body": pr.get("body") or "", "draft": bool(pr.get("draft")),
        "user": {"login": (pr.get("user") or {}).get("login", "")},
        "labels": [{"name": l["name"] if isinstance(l, dict) else l} for l in pr.get("labels") or []],
        "base": {"ref": "build/v1", "sha": base, "repo": {"full_name": "AbdulkareemSasah/Eng-Agent"}},
        "head": {"ref": pr["head"].get("ref", ""), "sha": head, "repo": {"full_name": "AbdulkareemSasah/Eng-Agent"}}}}
    (run_dir / "event.json").write_text(json.dumps(event, indent=1), encoding="utf-8")
    (run_dir / "status.txt").write_text("queued\n")
    with open(run_dir / "run.stdout", "w") as f:
        p = subprocess.Popen([sys.executable, str(pathlib.Path(__file__).resolve()), "run", "--event", str(run_dir / "event.json"),
                              "--out", str(run_dir)], stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True, cwd=str(HERE))
    pid_file.write_text(str(p.pid))
    print("LOCAL-CI STARTED")
    return 0


def cmd_wait(a):
    run_dir = pathlib.Path(a.run_dir)
    deadline = time.time() + a.max
    while True:
        status = (run_dir / "status.txt").read_text().strip() if (run_dir / "status.txt").is_file() else "missing"
        if status.startswith("done"):
            break
        alive = False
        try:
            os.kill(int((run_dir / "pid").read_text().strip()), 0)
            alive = True
        except (OSError, ValueError):
            pass
        if not alive and not status.startswith("done"):
            print(f"LOCAL-CI FAIL the run stopped without a result (status: {status}); start it again")
            return 1
        if time.time() >= deadline:
            print(f"LOCAL-CI RUNNING ({status}); call wait again")
            return 3
        time.sleep(10)
    doc = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    if doc["verdict"] == "CONFLICT":
        print(f"LOCAL-CI CONFLICT with build/v1 {doc['base'][:7]} in: {' '.join(doc.get('files', [])[:20])}")
        return 5
    if doc["verdict"] == "BEHIND":
        print(f"LOCAL-CI BEHIND build/v1 moved to {doc['tip'][:7]} while this run waited: update the branch "
              "(mcp__github__update_pull_request_branch), read the pull request again, and start again")
        return 4
    print(f"SUMMARY_FILE={run_dir / 'summary.md'}")
    print((run_dir / "summary.md").read_text(encoding="utf-8"))
    for j in doc["failing"]:
        print(f"--- {j} (failing lines; full log {run_dir / (j + '.log')})")
        print(doc["jobs"][j].get("tail", ""))
    print(f"LOCAL-CI {doc['verdict']} head={doc['head']} {' '.join(doc['failing'])}".strip())
    return 0 if doc["verdict"] == "PASS" else 1


def cmd_release(a):
    run_dir = pathlib.Path(a.run_dir)
    (run_dir / "released").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
    print("LOCAL-CI RELEASED")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("--pr-json", required=True)
    w = sub.add_parser("wait"); w.add_argument("--run-dir", required=True); w.add_argument("--max", type=int, default=100)
    rl = sub.add_parser("release"); rl.add_argument("--run-dir", required=True)
    r = sub.add_parser("run"); r.add_argument("--event", required=True); r.add_argument("--out", required=True)
    r.add_argument("--timeout", type=int, default=10800)
    p = sub.add_parser("push"); p.add_argument("--sha", default="origin/build/v1"); p.add_argument("--out", required=True)
    p.add_argument("--timeout", type=int, default=10800)
    a = ap.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    return {"start": cmd_start, "wait": cmd_wait, "run": cmd_run, "push": cmd_push, "release": cmd_release}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
