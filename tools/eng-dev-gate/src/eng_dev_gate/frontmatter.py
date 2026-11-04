"""Front matter of specs and plans (spec section 5) and the plan rules of AC13.

A document starts with YAML between two ``---`` lines. Every failure is a :class:`FrontMatterError` (GC005).
"""

from __future__ import annotations

import re
from graphlib import CycleError, TopologicalSorter
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator

from eng_dev_gate.results import ExitCode, GateError

Name = Annotated[str, Field(min_length=1)]
TaskId = Annotated[str, Field(pattern=r"^T\d+[a-z]*$")]  # T<n>; the plan itself uses T2a, T2b
CriterionId = Annotated[str, Field(pattern=r"^AC\d+[a-z]*$")]  # AC<n>; specs use AC15a
Count = Annotated[StrictInt, Field(gt=0)]
_CRITERION_LINE = re.compile(r"^(?:[-*]\s+)?(AC\d+[a-z]*)\.(?:\s|$)", re.MULTILINE)


class FrontMatterError(GateError):
    """A spec or plan whose front matter is invalid (GC005); ``str(error)`` names every problem."""

    exit_code = ExitCode.FAILED


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Spec(_Model):
    """Spec front matter. ``risk`` is a set of classes ``r0`` to ``r3``; one class may be written as a scalar."""

    id: Name
    issue: Name | StrictInt
    status: Literal["draft", "approved"]
    size: Literal["trivial", "small", "standard", "large"]
    risk: Annotated[list[Literal["r0", "r1", "r2", "r3"]], Field(min_length=1)]

    @field_validator("risk", mode="before")
    @classmethod
    def _scalar_risk(cls, value: object) -> object:
        return [value] if isinstance(value, str) else value


def safe_relative_path(path: str) -> bool:
    """Return whether ``path`` is a workspace-relative POSIX path: no backslash, no empty, ``.`` or ``..`` part."""
    return bool(path) and "\\" not in path and all(part not in ("", ".", "..") for part in path.split("/"))


class Task(_Model):
    """One plan task: ``files`` are globs, ``max_changed_lines`` counts lines, ``max_sessions`` counts sessions."""

    id: TaskId
    title: Name
    files: Annotated[list[Name], Field(min_length=1)]
    max_changed_lines: Count
    max_sessions: Count
    tests_first: list[Name] = Field(default_factory=list)
    covers: list[CriterionId] = Field(default_factory=list)
    depends_on: list[TaskId] = Field(default_factory=list)


class Plan(Spec):
    """Plan front matter: the spec it implements and its tasks."""

    spec: Name
    tasks: Annotated[list[Task], Field(min_length=1)]

    @field_validator("spec")
    @classmethod
    def _spec_path(cls, value: str) -> str:
        if not safe_relative_path(value):
            raise ValueError("spec must be a workspace-relative POSIX path")
        return value


def _front_matter(text: str) -> dict[str, Any]:  # Any: YAML is untyped data at this boundary
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    end = lines.index("---", 1) if lines[0] == "---" and "---" in lines[1:] else 0
    if not end:
        raise FrontMatterError("no front matter: the document must start with a YAML block between --- lines")
    try:
        data = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError as error:
        raise FrontMatterError(f"front matter is not valid YAML: {error}") from error
    if not isinstance(data, dict):
        raise FrontMatterError("front matter is not a mapping")
    return data


def _validate[M: BaseModel](model: type[M], data: dict[str, Any]) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as error:
        problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors())
        raise FrontMatterError(f"invalid front matter: {problems}") from error


def parse_spec(text: str) -> Spec:
    """Parse and validate the front matter of a spec.

    Raises:
        FrontMatterError: the block is missing, not YAML, not a mapping, or its fields are invalid.
    """
    return _validate(Spec, _front_matter(text))


def parse_plan(text: str, max_task_lines: int) -> Plan:
    """Parse a plan and apply AC13: unique task ids, known and acyclic ``depends_on``, tasks within the cap.

    Args:
        text: the plan file.
        max_task_lines: the cap on ``max_changed_lines`` of one task (``limits.max_task_lines``, lines).

    Raises:
        FrontMatterError: any rule above is broken, or the front matter is invalid (see :func:`parse_spec`).
    """
    plan = _validate(Plan, _front_matter(text))
    ids = [task.id for task in plan.tasks]
    if repeated := sorted({i for i in ids if ids.count(i) > 1}):
        raise FrontMatterError(f"task ids repeat: {', '.join(repeated)}")
    problems = [f"task {t.id} depends on unknown task {d}" for t in plan.tasks for d in t.depends_on if d not in ids]
    problems += [f"task {t.id}: max_changed_lines {t.max_changed_lines} exceeds {max_task_lines}" for t in plan.tasks
                 if t.max_changed_lines > max_task_lines]  # fmt: skip
    if problems:
        raise FrontMatterError("; ".join(problems))
    try:
        TopologicalSorter({t.id: t.depends_on for t in plan.tasks}).prepare()
    except CycleError as error:
        raise FrontMatterError(f"depends_on is cyclic: {' -> '.join(error.args[1])}") from error
    return plan


def uncovered_criteria(plan: Plan, spec_text: str) -> list[str]:
    """Return the criteria of the spec (``AC<n>.`` at the start of a line) that no task ``covers`` (GC016)."""
    covered = {c for task in plan.tasks for c in task.covers}
    criteria = dict.fromkeys(_CRITERION_LINE.findall(spec_text.replace("\r\n", "\n")))
    return [c for c in criteria if c not in covered]
