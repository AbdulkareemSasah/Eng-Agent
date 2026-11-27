---
id: workflow-{{name}}
issue: {{issue number}}
status: draft        # draft | approved
size: {{standard | large}}
risk: r1
---

# Workflow spec / مواصفة سير العمل: {{name}}

> Written by the owner in Arabic or English. A developer turns it into a block with tests; the owner approves both
> this spec (G1) and the result (G3).
> يكتبها المالك بالعربية أو الإنجليزية، ويحوّلها المطوّر إلى بلوك مع اختبارات.

Issue: #{{n}} · Owner: {{name}} · Status: Draft | Approved
Source needs: {{task-log need ids only (A24), or none}}

## 1. Goal / الهدف
{{What the workflow produces, and for which kind of project.}}

## 2. Today's manual process and time / الطريقة اليدوية الحالية ووقتها
{{Steps as the engineer does them now, and the measured time. This is the benchmark.}}

## 3. Inputs / المدخلات
| Input | From (template / asked each run / file / model) | Notes |
|---|---|---|

## 4. Steps / الخطوات
| # | Step | Program or check | What is checked after it | If it fails |
|---|---|---|---|---|

## 5. Decisions / القرارات
| Decision point | Options | Rule (if the answer is known) | Who decides when no rule matches (model / engineer) |
|---|---|---|---|

## 6. Approvals / الموافقات
{{Which steps need the engineer's approval in each permission mode.}}

## 7. Outputs / المخرجات
{{Models, reports, results. What "correct" means.}}

## 8. Acceptance / معايير القبول
| Id | Criterion | How it is measured |
|---|---|---|

## 9. Out of scope / خارج النطاق
- {{...}}
