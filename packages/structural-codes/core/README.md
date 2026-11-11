# structural-codes-core

Core framework of the structural-codes folder of the Eng-Agent platform (import name `structural_codes`). It holds no
engineering check; code editions live in their own packages. Governing documents: `../docs/specs/0001-core-framework.md`
and `../docs/plans/0001-core-framework.md`.

## Usage

Checks are registered by packs; the core ships none. A check is evaluated with `structural_codes.evaluate`, which
returns an `Evaluation` holding the `verdicts.set/1` payload, the check's lifecycle state and its content hash:

```python
from eng_contract.kinds.verdicts import VerdictSet
from eng_contract.verdicts import Subject, SubjectKind
from structural_codes import Evaluation, evaluate

result: Evaluation = evaluate(
    "<pack>.<clause>.<check>",  # a check_id from an installed pack
    {"<input>": 1.0},  # literal inputs named by the check's input model
    subject=Subject(kind=SubjectKind.FOOTING, id="F1"),
    mode="trial",  # "production" needs an approved check
)
payload: VerdictSet = result.payload
print(result.state, payload.verdicts[0].status)
```

`evaluate_batch(check_id, [BatchItem(subject, inputs), ...])` evaluates many subjects and isolates a failing item as
an `ERROR` verdict. A `draft` check is refused in `production` mode. The public modules are listed in
`[tool.eng-gate] public_modules` of `pyproject.toml`; every other module starts with an underscore.
