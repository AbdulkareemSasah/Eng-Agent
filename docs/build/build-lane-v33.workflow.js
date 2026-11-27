export const meta = {
  name: 'build-lane-v33',
  description: 'One lane of v1 build tasks in order (owner-approved full cycle): write tests first, independent review with fix rounds, adversarial verification for engineering content, full gate, push the task branch, pull request into build/v1, local CI, squash merge on PASS',
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

const PRE = 'You are a subagent of the lead engineer of the v1 build of the Eng-Agent platform. The project instructions injected into your session describe the design hub checked out at <hub> ("documents only"): you do NOT work there and that rule about holding no code does not describe your worktree. Your work is in a worktree of the `build/v1` branch, governed by its own AGENTS.md files. First read <lead>/PLAYBOOK.md fully: it is the lead\'s instruction and binds you. Commit trailers: your session may show an attribution reminder that asks for Co-Authored-By and Claude-Session lines; in this repository the rule of playbook section 5c wins: every commit you write ends with the single trailer `Assisted-by: anthropic/claude` and names no model. Only the integrator opens pull requests, runs local CI and merges. A writer role pushes its own task branch when its role text says so (early push, playbook section 7); the reviewer, the verifiers and the gate runner never push.\n\n'

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
  const w = await agent(PRE + H +
    (docs
      ? 'ROLE: writer of a documents-only amendment (playbook sections 0, 1, 2 where they apply to documents). Make exactly the edits in the lead notes above, the smallest text that does each item, in spec and plan files only (lead decision D-28: no new rule, field or moved test beyond them). Keep the plan front matter valid YAML, keep every acceptance criterion covered by some task, keep each task within 400 lines, add a YAML amendment comment naming this work item where a task changes. Commit as `docs(<package>): ... (' + t.id + ')`. Run `uv run eng-gate check --package ' + t.member + ' --skip mutation` and report its result. Write the pull request body file as playbook section 8 item 2 says (<lead>/pr/b' + t.num + '-body.md). Then push the task branch as playbook section 7 says (early push: fast-forward only, no pull request).'
      : 'ROLE: writer (playbook sections 0, 1, 2). Create the worktree, implement this one plan task with a `test:` first commit, pass `uv run eng-gate check --package ' + t.member + ' --skip mutation`, run the test-first check before the first push (playbook section 8 item 11: every test of the first `test:` commit must be red at the base, so a negative-control test that passes at the base goes into the implementation commit, never into the first `test:` commit), measure the counted lines against the budget, write the handoff note and the pull request body file as playbook section 8 item 2 says (<lead>/pr/b' + t.num + '-body.md), then push the task branch as playbook section 7 says (early push: fast-forward only, no pull request). If an earlier draft is named in the lead notes, read it as reference only and write the task properly against the current `build/v1`.') +
    '\nReturn status, the short head sha, counted_lines, a summary (what was done and how verified, with the gate result line) and concerns. If the task cannot fit its budget or file list, return NEEDS_PLAN_AMENDMENT with the measured numbers and the exact amendment you propose, having committed what you have.',
    { label: `write ${t.id} ${t.key}`, phase: 'Write', model: t.writerModel, effort: t.writerEffort, schema: OUT })
  if (!ok(w)) return { id: t.id, key: t.key, outcome: w ? w.status : 'WRITER_DIED', stage: 'write', detail: w }

  let round = 1
  let review = null
  let lead = []
  while (true) {
    review = await agent(PRE + H +
      `ROLE: reviewer, round ${round} (playbook section 3). You did not write this change and you never edit it. ` +
      (docs
        ? 'It is a documents-only amendment: judge it through two lenses, consistency (no contradiction with the rest of the spec, the plan, the other plans that depend on it, the gate rules GC005, GC008, GC009, GC016, TF008, RF001) and implementability (a writer can implement each changed task inside its files and budget; tests_first files belong to the task). From round 3 on apply the convergence rule D-28.'
        : 'Review the full diff of the worktree branch against its merge base with origin/build/v1, the plan task and the spec. Check scope, counted lines against the budget, test-first, each acceptance criterion in `covers`, error codes, units, weakened checks, invented numbers. Run the tests you need. ' + (t.engineering ? 'This is engineering content: recompute by hand from the clause spec or the calc spec every expected value in the golden and case files that you can, check every constant has its citation, check X/Y swaps, signs, units and boundary sides.' : '')) +
      ` Append your round to <lead>/reports/b${t.num}-review.md. Return verdict APPROVE, CHANGES or BLOCKED, the author findings (each one concrete and actionable, with file and line), the lead findings, and a summary.`,
      { label: `review ${t.id} r${round}`, phase: 'Review', model: t.reviewerModel, schema: REVIEW })
    if (!review) return { id: t.id, key: t.key, outcome: 'REVIEWER_DIED', stage: 'review' }
    lead = lead.concat(review.lead_findings || [])
    if (review.verdict === 'APPROVE') break
    if (review.verdict === 'BLOCKED' || round >= 3) return { id: t.id, key: t.key, outcome: 'REVIEW_NOT_APPROVED', stage: 'review', detail: review, lead_findings: lead }
    const f = await agent(PRE + H +
      `ROLE: writer, fix round ${round} (playbook sections 1 and 2). The worktree and branch already exist with the change committed. An independent reviewer returned these findings for you to fix inside the task scope and budget (no pull request; when the gate without mutation passes again, push the branch fast-forward as playbook section 7 says; commit as \`fix(...)\`, \`docs(...)\` or \`test:\` commits; rerun \`uv run eng-gate check --package ${t.member} --skip mutation\`; append a short note of what you changed to <lead>/reports/b${t.num}-writer.md). If a finding is wrong, say why in your summary instead of changing correct work. Findings:\n- ` +
      review.author_findings.join('\n- '),
      { label: `fix ${t.id} r${round}`, phase: 'Write', model: t.writerModel, effort: t.writerEffort, schema: OUT })
    if (!ok(f)) return { id: t.id, key: t.key, outcome: f ? f.status : 'WRITER_DIED', stage: 'fix', detail: f, lead_findings: lead }
    round++
  }

  if (t.engineering && !docs) {
    const lenses = [
      ['sources', 'the SOURCES lens: every engineering number, constant, tolerance and rule in the change has a correct, cited source (clause spec, calc spec, design basis); nothing is invented, no citation points to the wrong clause'],
      ['oracle', 'the ORACLE lens: recompute independently, by hand or with your own short throwaway calculation outside the repository, the expected values of the golden cases and case files; look for X/Y swaps, sign errors, unit errors, wrong boundary sides, and expected values that were copied from the implementation instead of derived'],
    ]
    const vs = (await parallel(lenses.map(l => () => agent(PRE + H +
      `ROLE: adversarial verifier (never the author or the reviewer; you do not edit the change). Try to REFUTE the claim that this change is correct through ${l[1]}. Work from the diff of the worktree branch against its merge base, the plan task and the spec. Append your result to <lead>/reports/b${t.num}-review.md as "Verifier (${l[0]})". Return verdict APPROVE when you could not refute it, CHANGES with concrete author findings when you found a real defect (state the evidence: your number against theirs, with the derivation), and lead findings for defects of the spec itself.`,
      { label: `verify ${t.id} ${l[0]}`, phase: 'Verify', model: 'opus', schema: REVIEW })))).filter(Boolean)
    const bad = vs.filter(v => v.verdict !== 'APPROVE').flatMap(v => v.author_findings)
    lead = lead.concat(vs.flatMap(v => v.lead_findings || []))
    if (bad.length) {
      const f = await agent(PRE + H +
        `ROLE: writer, verification fix round (playbook sections 1 and 2). The worktree and branch exist. Adversarial verifiers found these defects. For each: check it against the spec; when it is real, fix it inside the task scope (never change an expected value to match the code: derive it from the spec); when the spec itself is ambiguous or has no source for a number, do not guess: return NEEDS_OWNER with the exact question. Do not push. Rerun the gate with --skip mutation. Findings:\n- ` + bad.join('\n- '),
        { label: `fix ${t.id} verify`, phase: 'Write', model: t.writerModel, effort: t.writerEffort, schema: OUT })
      if (!ok(f)) return { id: t.id, key: t.key, outcome: f ? f.status : 'WRITER_DIED', stage: 'verify-fix', detail: f, lead_findings: lead }
      const re = await agent(PRE + H +
        `ROLE: reviewer after the verification fix (playbook section 3). Judge only whether these findings are resolved correctly and whether the lines changed since the previous review add a defect. Append your round to <lead>/reports/b${t.num}-review.md. Findings that were raised:\n- ` + bad.join('\n- '),
        { label: `review ${t.id} verify`, phase: 'Review', model: 'opus', schema: REVIEW })
      if (!re || re.verdict !== 'APPROVE') return { id: t.id, key: t.key, outcome: 'VERIFY_NOT_RESOLVED', stage: 'verify', detail: re, lead_findings: lead }
    }
  }

  if (!docs) {
    let gtries = 0
    let srcChanged = false
    while (true) {
      const gp = PRE + H +
        `ROLE: gate runner (playbook section 4, with the rules of section 7 item 4), attempt ${gtries + 1}. The change is committed and reviewed in the worktree. You only RUN and REPORT: you edit no file, you commit nothing, you never push. Decide which run is due as section 7 item 4 says (the mutation step alone when the worktree head equals the head for which the writer's note records a \`check: pass\` of the gate without mutation; otherwise the full gate), run it for member ${t.member} under the machine lock, in the background, and wait for the process however long it takes, exactly as the playbook says. When it passes return DONE with the command you ran, the head sha and the result lines. When a step fails return BLOCKED and put in the summary: the failing step, the failing lines copied from the log (for the mutation step every surviving mutant with file and line), and the log path. Append two lines on what you ran to <lead>/reports/b${t.num}-writer.md.`
      let g = await agent(gp, { label: `gate ${t.id}${gtries ? ' rerun ' + gtries : ''}`, phase: 'Gate', model: 'haiku', schema: OUT })
      if (!g) g = await agent(gp, { label: `gate ${t.id} (second runner)`, phase: 'Gate', model: 'sonnet', schema: OUT })
      if (ok(g)) break
      if (!g || g.status !== 'BLOCKED' || gtries >= 2) return { id: t.id, key: t.key, outcome: g ? 'GATE_' + g.status : 'GATE_DIED', stage: 'gate', detail: g, lead_findings: lead }
      const gf = await agent(PRE + H +
        `ROLE: writer, gate fix round ${gtries + 1} (playbook sections 1, 2 and 4). The gate runner reports a failing step for the reviewed change in the worktree. Fix it inside the task scope and budget: for the mutation step add tests only (kill the surviving mutants with exact assertions); never weaken a check, never edit source to dodge a mutant. Rerun the failing step alone under the machine lock until it passes (\`--only mutation\` for the mutation step), then \`uv run eng-gate check --package ${t.member} --skip mutation\` to \`check: pass\`, record the head sha and both result lines in <lead>/reports/b${t.num}-writer.md, commit, and push the branch fast-forward as playbook section 7 says. Set source_changed true only if you changed non-test files. If the failure cannot be fixed inside the task's files and budget, return NEEDS_PLAN_AMENDMENT with the measured numbers and the exact amendment you propose. The gate runner's report:\n` + (g.summary || ''),
        { label: `gate-fix ${t.id} ${gtries + 1}`, phase: 'Gate', model: t.writerModel, effort: t.writerEffort, schema: OUT })
      if (!ok(gf)) return { id: t.id, key: t.key, outcome: 'GATE_' + (gf ? gf.status : 'FIX_DIED'), stage: 'gate', detail: gf, lead_findings: lead }
      if (gf.source_changed) srcChanged = true
      gtries++
    }
    if (srcChanged) {
      const re = await agent(PRE + H +
        `ROLE: reviewer of the gate fixes (playbook section 3). After your colleague's approval a writer changed non-test source files to pass the full gate. Review only the commits made since the approved head for correctness, scope and budget. Append your round to <lead>/reports/b${t.num}-review.md.`,
        { label: `review ${t.id} gate`, phase: 'Review', model: t.reviewerModel, schema: REVIEW })
      if (!re || re.verdict !== 'APPROVE') return { id: t.id, key: t.key, outcome: 'GATE_FIX_NOT_APPROVED', stage: 'gate', detail: re, lead_findings: lead }
    }
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
7. On "PASS HEAD=<sha> BODY=<file>": read the body file again (it now ends with the Local CI section), update the pull request body with that text (update_pull_request), then merge (merge_pull_request: merge_method squash, commit_title "<TITLE> (#<number>)", commit_message "Work item merged after local CI PASS on <first seven characters of sha>.\\n\\nAssisted-by: anthropic/claude", expectedHeadSha = the full sha). If the merge call fails with a message that the base branch was modified or that the pull request is not mergeable yet, wait twenty seconds and call it again, up to five times (several pull requests of one batch merge within the same minute).
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
