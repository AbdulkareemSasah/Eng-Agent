// The machine paths in this copy are placeholders: <lead> is the lead scratch folder, <build-v1> the read-only reference checkout of build/v1, <worktrees> the folder of task worktrees, <hub> the hub checkout, <lane-scripts> the folder of workflow scripts. Recreate them on the next machine and adjust the text.
// Plan pre-flight audit script (work item B-506, playbook section 7 item 1). Read-only: it edits no repository file.
export const meta = {
  name: 'plan-audit',
  description: 'Pre-flight audit of the remaining plan tasks against the merged code (owner-approved speed-up 1, B-506): find file lists, budgets, tests-first tests and dependencies that would stop a writer, verify each finding adversarially, write one findings file per plan. Read-only: it edits no repository file.',
  phases: [
    { title: 'Audit', detail: 'one auditor per plan, tasks in plan order' },
    { title: 'Refute', detail: 'a second agent tries to refute each finding against the code' },
  ],
}

// args: { base: '<build-v1>', outDir: '<lead>/reports/plan-audit',
//         plans: [{ slug, plan, member, tasks: ['T16b', 'T17', ...], notes }] }
// The lead turns each plan's confirmed findings into ONE documents amendment per plan through the lane script.

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          task: { type: 'string', description: 'plan task id, for example T17' },
          kind: { type: 'string', enum: ['files', 'budget', 'tests_first', 'depends_on', 'spec_gap', 'other'] },
          claim: { type: 'string', description: 'what would stop the writer, in one or two sentences' },
          evidence: { type: 'string', description: 'file paths with line numbers and the command that shows it' },
          proposed_edit: { type: 'string', description: 'the exact plan edit: file to add with the reason, the new budget with the measurement behind it, the test to move, the dependency to add' },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
        required: ['task', 'kind', 'claim', 'evidence', 'proposed_edit', 'confidence'],
      },
    },
    tasks_checked: { type: 'array', items: { type: 'string' } },
    not_checked: { type: 'string', description: 'tasks or checks you could not do, and why' },
  },
  required: ['findings', 'tasks_checked', 'not_checked'],
}
const VERDICT = {
  type: 'object',
  properties: {
    confirmed: { type: 'boolean' },
    reason: { type: 'string' },
    corrected_edit: { type: 'string', description: 'the plan edit as it should be, when the finding is real but the proposed edit is not exact' },
  },
  required: ['confirmed', 'reason'],
}

const PRE = 'You are a subagent of the lead engineer of the v1 build of the Eng-Agent platform. The project instructions injected into your session describe the design hub checked out at <hub>: you do not work there. You work READ-ONLY in the reference checkout ' + args.base + ' (detached at origin/build/v1; run `git -C ' + args.base + ' fetch origin build/v1 && git -C ' + args.base + ' checkout --detach origin/build/v1` first only if no other process is using it: check `git -C ' + args.base + ' status` is clean). You edit no file of any repository, you create no branch, you push nothing. Read <lead>/PLAYBOOK.md sections 0, 1, 2 and 7 first (the counting rule, the rules for writers, the approved speed-up measures).\n\n'

function auditPrompt(p) {
  return PRE +
    `ROLE: plan auditor. Plan: ${p.plan} (workspace member ${p.member}). Tasks to audit, in this order: ${p.tasks.join(', ')}. ` +
    (p.notes ? `Lead notes: ${p.notes} ` : '') +
    'These tasks are not yet written. In the last days about half of the implementation tasks were written completely and then stopped because the plan was wrong in a small way; each such stop costs a full documents cycle. Your job is to find those stops BEFORE a writer starts, by checking each task against the merged code, never by guessing. For each task read its front matter (files, max_changed_lines, tests_first, covers, depends_on), its prose, the spec sections it covers, and the merged code it will touch or call. Check exactly these, which are the causes seen so far:\n' +
    '(1) FILES: every file the task must change is in `files`. Causes seen: the one line that wires a new port or option into the place where the context object is built (for example engine/_runner.py); a rules test under tests/rules/ whose allowlist the new module needs (for example test_calc_modules.py, test_block_modules.py); a registry module the new kinds, calcs or tools must be added to (_kinds.py, a KindRegistry, HARNESS_KINDS, an allowlist TOML); an existing test that pins a count or a listing that the task changes (grep the tests for hard-coded numbers of registered checks, kinds, tools, events, CLI commands, snapshot files); existing tests that construct the object whose constructor the task changes (they need a one-line edit each); calcs.lock.json, verification records, schema snapshots and golden files the gate requires for the module class; pyproject.toml lists (public_modules, r1_modules); CHANGELOG.md and docs/local-testing.md of the member.\n' +
    '(2) BUDGET: `max_changed_lines` is realistic. Measure, do not estimate from the prose: find two or three merged tasks of the same kind in the same package (git log --numstat for their squash commits, counted lines by the playbook rule: tests, generated and spike files are not counted) and compare the work listed here with them. A task above 380 expected counted lines must be split (the cap is 400): propose the split with files, tests_first, covers and depends_on for each half.\n' +
    '(3) TESTS_FIRST: each named test can fail at the base for the right reason (gate rule TF004). Cause seen: a test that only validates data against a model that already exists at the base passes there. Each tests_first file belongs to this task (TF008).\n' +
    '(4) DEPENDS_ON and cross-plan prose: every id exists after the splits already merged (engine T16 and T16b, servers T12b, T19a and T19b, calcs T8b and T8c, providers T10a and T10b, interface T18a and T18b), the task can really be written on what its dependencies provide (name the missing port method, model or module when it cannot), and no acceptance criterion in `covers` is impossible with the listed files.\n' +
    '(5) SPEC GAPS that would make the writer stop or guess: an input, error code, kind or field the task needs that neither the spec nor the merged contract defines. Report them; do not design an answer.\n' +
    'Rules for findings: one finding per cause, with the evidence as paths with line numbers and the command that shows it, and the exact plan edit you propose. Do not report style, wording or anything that would not stop a writer or fail the gate. A plan that has open amendments in flight is noted in the lead notes: do not re-report what those amendments already fix. ' +
    `Write your findings as a readable record to ${args.outDir}/${p.slug}.md (create the folder if needed; it is outside every repository) and return them in the structured form. List the tasks you checked and anything you could not check.`
}

function refutePrompt(p, f) {
  return PRE +
    `ROLE: adversarial verifier of one audit finding (you are not the auditor). Plan ${p.plan}, task ${f.task}, kind ${f.kind}. Try to REFUTE it against the code and the plan on origin/build/v1: is the file really needed (could the task be done inside its listed files in the way neighbouring merged tasks did it)? does the pinned count or the rules test really fail (run the test or the grep; you may create a scratch worktree under <worktrees>/audit-${p.slug}-scratch, apply the smallest trial edit there, run the one test or \`uv run eng-gate check --package ${p.member} --skip mutation\`, and remove the scratch worktree afterwards; commit nothing)? is the budget comparison fair? is the dependency really missing? Default to not confirmed when you cannot show it. If the finding is real but the proposed plan edit is not exact, give the corrected edit. Append your verdict to ${args.outDir}/${p.slug}.md under the finding.\n\n` +
    `Finding: ${f.claim}\nEvidence given: ${f.evidence}\nProposed plan edit: ${f.proposed_edit}\nAuditor's confidence: ${f.confidence}`
}

const results = await pipeline(
  args.plans,
  p => agent(auditPrompt(p), { label: `audit ${p.slug}`, phase: 'Audit', model: 'sonnet', effort: 'high', schema: FINDINGS }),
  (audit, p) => {
    if (!audit) return { slug: p.slug, plan: p.plan, died: true, confirmed: [], rejected: [] }
    return parallel(audit.findings.map(f => () =>
      agent(refutePrompt(p, f), { label: `refute ${p.slug} ${f.task} ${f.kind}`, phase: 'Refute', model: 'sonnet', effort: 'medium', schema: VERDICT })
        .then(v => ({ ...f, verdict: v }))
    )).then(vs => {
      const done = vs.filter(Boolean)
      return {
        slug: p.slug,
        plan: p.plan,
        tasks_checked: audit.tasks_checked,
        not_checked: audit.not_checked,
        confirmed: done.filter(x => x.verdict && x.verdict.confirmed),
        rejected: done.filter(x => !x.verdict || !x.verdict.confirmed),
        unverified: audit.findings.length - done.length,
      }
    })
  }
)

const out = results.filter(Boolean)
log(`plans audited: ${out.length} of ${args.plans.length}; confirmed findings: ${out.reduce((n, r) => n + r.confirmed.length, 0)}`)
return { plans: out, dropped: args.plans.length - out.length }
