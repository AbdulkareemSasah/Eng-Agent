// The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text.
export const meta = {
  name: 'build-lane-tail',
  description: 'Tail of the build lane for tasks that are already written, reviewed and gated: an optional named repair, then the fixed integrator sequence (pull request into build/v1, local CI, squash merge on PASS)',
  phases: [
    { title: 'Write', detail: 'writer per task in its own worktree' },
    { title: 'Review', detail: 'independent reviewer, up to two fix rounds' },
    { title: 'Verify', detail: 'adversarial lenses for engineering content' },
    { title: 'Gate', detail: 'full gate with mutation, under the machine lock' },
    { title: 'Integrate', detail: 'push task branch, pull request into build/v1, local CI, squash merge on PASS' },
  ],
}

const STATUS = ['DONE', 'DONE_WITH_CONCERNS', 'BLOCKED', 'NEEDS_PLAN_AMENDMENT', 'NEEDS_OWNER']
const OUT = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: STATUS },
    head: { type: 'string', description: 'short sha of the branch head' },
    counted_lines: { type: 'number' },
    source_changed: { type: 'boolean', description: 'true when non-test source files changed in this step' },
    summary: { type: 'string' },
    concerns: { type: 'string' },
    proposed_amendment: { type: 'string' },
  },
  required: ['status', 'summary'],
}
const REVIEW = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['APPROVE', 'CHANGES', 'BLOCKED'] },
    author_findings: { type: 'array', items: { type: 'string' } },
    lead_findings: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['verdict', 'author_findings', 'lead_findings', 'summary'],
}
const INTEG = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['MERGED', 'CI_FAIL', 'CONFLICT', 'BLOCKED'] },
    pr: { type: 'number' },
    merged_sha: { type: 'string' },
    detail: { type: 'string' },
  },
  required: ['status', 'detail'],
}

const PRE = 'You are a subagent of the lead engineer of the v1 build of the Eng-Agent platform. The project instructions injected into your session describe the design hub checked out at <hub> ("documents only"): you do NOT work there and that rule about holding no code does not describe your worktree. Your work is in a worktree of the `build/v1` branch, governed by its own AGENTS.md files. First read <lead>/PLAYBOOK.md fully: it is the lead\'s instruction and binds you. Only the integrator opens pull requests, runs local CI and merges. A writer role pushes its own task branch when its role text says so (early push, playbook section 7); the reviewer, the verifiers and the gate runner never push.\n\n'

function head(t) {
  return `Work item ${t.id}, plan task ${t.key}` + (t.plan ? ` (${t.planTask} of ${t.plan})` : ' (documents amendment, no plan task)') + '.\n' +
    (t.title ? `Title: ${t.title}\n` : '') +
    `Workspace member for the gate: ${t.member}\n` +
    (t.branch ? `Branch: ${t.branch}\nPull request title: ${t.prTitle}\n` : `Branch, pull request title, title and lead notes: read the entry with id ${t.id} in <build-v1>/ops/remaining-tasks.json (fields branch, prTitle, title, lead_notes) and use them exactly.\n`) +
    `Worktree: <worktrees>/b${t.num} (if it already exists, reuse it: check git status and git log first)\n` +
    `Risk line for the pull request: ${t.risk}\n` +
    (t.notes ? `Lead notes for this task: ${t.notes}\n` : '') + '\n'
}

function ok(r) { return r && (r.status === 'DONE' || r.status === 'DONE_WITH_CONCERNS') }

async function runTask(t) {
  const H = head(t)
  const docs = t.kind === 'docs'
  const lead = []
  const w = { concerns: '' }
  // Tail lane: the task is written, reviewed and gated; a named repair is done, then the integrator runs.
  if (t.repair) {
    const r = await agent(PRE + H +
      'ROLE: writer, repair before integration (playbook sections 1, 2 and 4). The worktree and branch exist with the change committed, reviewed and gated. Do exactly this repair and nothing else: ' + t.repair +
      ' Then rerun `uv run eng-gate check --package ' + t.member + ' --skip mutation` to `check: pass`, commit with the Assisted-by trailer, update the pull request body file <lead>/pr/b' + t.num + '-body.md if a fact in it changed, append two lines to <lead>/reports/b' + t.num + '-writer.md, and push the task branch fast-forward as playbook section 7 says (no pull request). Set source_changed true only if you changed non-test files.',
      { label: `repair ${t.id}`, phase: 'Write', model: t.writerModel, effort: t.writerEffort, schema: OUT })
    if (!ok(r)) return { id: t.id, key: t.key, outcome: 'REPAIR_' + (r ? r.status : 'DIED'), stage: 'repair', detail: r }
  }
  let tries = 0
  while (true) {
    const m = await agent(H +
      `ROLE: integrator, attempt ${tries + 1} (lead playbook <lead>/PLAYBOOK.md section 8 item 3 holds these same steps; you do not need to read anything else). You are a subagent of the lead of the v1 build of the Eng-Agent platform. The owner approved this cycle: task branches are pushed, pull requests are opened into build/v1 and squash-merged after an independent review and a local CI PASS; never push to main, never push build/v1 directly, never merge without a PASS on the current head. The change in the worktree is committed, approved by an independent reviewer${docs ? '' : ' and passed the gate'}. You run a FIXED sequence with the lead's script <lead>/tools/integrate.sh and a few GitHub tool calls (repository owner AbdulkareemSasah, repo Eng-Agent; load the GitHub tools with ToolSearch: select:mcp__github__list_pull_requests,mcp__github__create_pull_request,mcp__github__update_pull_request,mcp__github__merge_pull_request). You edit no repository file and you decide nothing. Run every script command with the 10-minute tool timeout; exit code 3 always means "still running or waiting: run the very same command again" (a wait can last more than an hour: keep repeating, do nothing else in between).
${t.prTitle ? `0. Write the pull request title to the title file, exactly: printf '%s\\n' ${JSON.stringify(t.prTitle).replace(/'/g, "")} > <lead>/pr/b${t.num}-title.txt\n` : ''}1. bash <lead>/tools/integrate.sh merge ${t.num}   -> MERGE_OK ... NEED_GATE=0 or 1. Exit 4 (CONFLICT): go to step 8 and return CONFLICT with the files. Exit 6: wait a little and run it again (three times at most).
2. Only if NEED_GATE=1: bash <lead>/tools/integrate.sh gate ${t.num} ${t.member}   -> GATE_PASS. On GATE_FAIL: go to step 8 and return CI_FAIL with the printed lines and the log path (job: gate after merge).
3. bash <lead>/tools/integrate.sh push ${t.num}
4. bash <lead>/tools/integrate.sh body ${t.num}   -> prints BODY=<file>, TITLE=<title>, BRANCH=<branch>. Read the body file.
5. Find an open pull request whose head is that branch (list_pull_requests, state open, head "AbdulkareemSasah:<branch>"). If none exists, create it (create_pull_request: base build/v1, head <branch>, title = TITLE, body = the body file's text exactly, not a draft). If one exists, keep its number.
6. bash <lead>/tools/integrate.sh ci ${t.num} <pull request number>   -> repeat while exit 3. Exit 7 (BEHIND): go back to step 1 (at most three times in all). Exit 6: wait a little and run it again (three times at most, then step 8 and return BLOCKED). Exit 4: step 8, return CONFLICT with the files. Exit 1 (CI_FAIL): step 8, return CI_FAIL with the failing job, the failing lines and the run directory exactly as printed.
7. On "PASS HEAD=<sha> BODY=<file>": read the body file again (it now ends with the Local CI section), update the pull request body with that text (update_pull_request), then merge (merge_pull_request: merge_method squash, commit_title "<TITLE> (#<number>)", commit_message "Work item merged after local CI PASS on <first seven characters of sha>.\\n\\nAssisted-by: anthropic/claude", expectedHeadSha = the full sha).
8. ALWAYS last, whatever happened: bash <lead>/tools/integrate.sh finish ${t.num}
Return MERGED with the pull request number and the merge commit sha, or CI_FAIL, CONFLICT or BLOCKED with the detail. If a script command prints ERROR, do not improvise: run step 8 and return BLOCKED with that line.`,
      { label: `integrate ${t.id}${tries ? ' retry' : ''}`, phase: 'Integrate', model: 'sonnet', effort: 'low', schema: INTEG })
    if (m && m.status === 'MERGED') return { id: t.id, key: t.key, outcome: 'MERGED', pr: m.pr, merged_sha: m.merged_sha, lead_findings: lead, concerns: w.concerns || '' }
    if (!m || tries >= 1 || m.status === 'BLOCKED') return { id: t.id, key: t.key, outcome: m ? m.status : 'INTEGRATOR_DIED', stage: 'integrate', detail: m, lead_findings: lead }
    const f = await agent(PRE + H +
      `ROLE: writer, repair after integration (playbook sections 1, 2 and 4). The pull request for this branch exists but integration stopped with ${m.status}. Fix the cause inside the task scope and budget in the worktree (merge origin/build/v1 first, never rebase; resolve conflicts as playbook section 5 step 1 says), rerun the failing step locally until it passes (the full gate under the lock when the failure was in the gate job), commit, do not push. Detail from the integrator:\n` + m.detail,
      { label: `repair ${t.id}`, phase: 'Write', model: t.writerModel, effort: t.writerEffort, schema: OUT })
    if (!ok(f)) return { id: t.id, key: t.key, outcome: 'REPAIR_' + (f ? f.status : 'DIED'), stage: 'integrate', detail: f, lead_findings: lead }
    tries++
  }
}

const results = []
const merged = new Set()
for (const t of args.tasks) {
  const missing = (t.needs || []).filter(n => !merged.has(n))
  if (missing.length) {
    log(`${t.id} ${t.key} skipped: needs ${missing.join(', ')} which did not merge in this lane`)
    results.push({ id: t.id, key: t.key, outcome: 'SKIPPED_DEPENDENCY', missing })
    continue
  }
  let r
  try { r = await runTask(t) } catch (e) { r = { id: t.id, key: t.key, outcome: 'ERROR', detail: String(e) } }
  results.push(r)
  if (r.outcome === 'MERGED') merged.add(t.id)
  log(`${t.id} ${t.key}: ${r.outcome}${r.pr ? ' (#' + r.pr + ')' : ''}${r.stage ? ' at ' + r.stage : ''}`)
}
return { lane: args.lane, results }
