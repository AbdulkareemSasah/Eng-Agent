# 10. Engineering Verification

Applies to all R1 work: anything that can change an engineering number, a verdict, a unit, a model write, a template
value, a calc function, or a decision rule or policy.

## 1. Roles

| Role | Who | Responsibility |
|---|---|---|
| Engineering authority | The owner | Approves R1 specs, R1 merges, code-pack approvals, shipped templates and decision policies |
| Author | Person or agent | Writes the spec, tests and implementation |
| Independent verifier | A different person or agent session, preferably a different model family | Checks the work against the source (the clause, the host documentation, the example) without seeing the author's reasoning |

## 2. Sources

Allowed sources for engineering content: the code itself (the owner provides access), recognized textbooks and design
guides, host program documentation, and the owner's approved past projects. Memory is not a source. Every constant and
every expected value in a test cites its source precisely (document, edition, clause or page, table or example).

## 3. Clause conversion pipeline

Converting design-code clauses into checks is done with agents, under these steps:

| Step | Who | Output |
|---|---|---|
| C1 Scope | Owner | The clauses to convert, in priority order, and the sources available (examples, books, program cases) |
| C2 Clause spec | Author agent | [clause-spec.md](templates/clause-spec.md): inputs with units and bounds, applicability, equations as math, constants with citations, outputs, edge cases, verification cases |
| C3 Spec verification | Independent verifier | A line-by-line comparison of the spec against the clause; findings resolved |
| C4 Spec approval (G1) | Owner | Approval on the issue |
| C5 Implementation | Author agent | Tests first (worked examples, boundaries, properties), then the check |
| C6 Program comparison | Author, run by the owner where a host is needed | Recorded host results for defined cases, with assumption differences documented |
| C7 Review (G3) | Independent verifier and owner | Review against the clause spec and the clause; verification record complete |
| C8 Approval | Owner | Entry in `approvals.yaml` bound to the check's content hash |

A check whose verification fails at C6 or C7 does not merge as `verified`; it stays `draft` with the failure recorded.

## 4. Calc functions, templates and rules

- Calc functions in the harness follow the same steps as checks, with "clause" replaced by the method's source (a
  documented engineering procedure, or the owner's documented practice), and the same lifecycle: approval bound to the
  content hash in the harness's `approvals.yaml`, production runs use approved calcs only.
- Shipped templates: every value cites its source (code clause, standard, owner's practice) and changes need owner
  approval.
- Decision rules and policies: reviewed by the owner; each rule has an id, a rationale and tests with typical and
  boundary states.

## 5. Changes to engineering output

- Any pull request that changes the output of a check, a calc function or a template for the same inputs includes a
  **golden diff report**: which cases changed, old and new values, and why.
- The owner approves the change explicitly. For code packs, it is a major version change of the pack, and the
  changelog lists every affected `check_id`.
- Approvals bound to content hashes are lost automatically; the check returns to `verified` until re-approved.

## 6. Records

- Each check's verification record lives with its clause spec: sources, examples and their results, program comparison
  cases and their results, verifier, findings and resolutions.
- `approvals.yaml` entries: `check_id`, content hash, approver, date, links to the verification record and the pull
  request.

## 7. When a wrong result is found after release

1. Open an issue labeled `type/bug`, `risk/r1-engineering`, severity critical.
2. Withdraw the affected check or function immediately through the emergency path ([12](12-operations.md) §1): mark it
   `withdrawn` in a patch release so the harness refuses to use it; publish a security advisory describing the affected
   cases.
3. Add the failing case as a regression test; fix through the full pipeline.
4. Write a short post-mortem within one week: cause, why verification missed it, and the process change that prevents
   it.
