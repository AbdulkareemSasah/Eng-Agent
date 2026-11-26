"""Task-log record and triage-line models (spec 0015 sections 4.3, 4.3.1).

Purpose: the frozen stored form of `harness.tasklog_record/1` (13 kinds, closed `not_found` categories) and of
`harness.tasklog_triage/1` (4 kinds, closed outcomes); both `extra="forbid"`, discriminated by `kind`, with no
validation between fields and hashes (a withheld line keeps the original's hash).
Units: `seq` starts at 1; `*_sha256` are lowercase hex; `at` is UTC `YYYY-MM-DDTHH:MM:SSZ`.
Errors: `pydantic.ValidationError` for every violated rule.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StringConstraints, model_validator

__all__ = [
    "OTHER_NEED_MIN",
    "OWNER_TEXT_MAX",
    "TITLE_EN_MAX",
    "AgentInfo",
    "Answered",
    "DidInstead",
    "Handoff",
    "Narration",
    "NotFound",
    "NotFoundDetail",
    "OwnerWords",
    "Problem",
    "PublicReleased",
    "Redaction",
    "RunAttached",
    "RunFact",
    "RunRefused",
    "RunTimings",
    "Searched",
    "SessionInfo",
    "TaskClosed",
    "TaskOpened",
    "TaskRecord",
    "TriageLine",
    "TriageWithheldAfter",
    "Triaged",
    "WithheldAfter",
]

TITLE_EN_MAX = 200
"""Maximum characters of `task_opened.title_en` (spec 0015 4.3)."""
OWNER_TEXT_MAX = 20_000
"""Maximum characters of `owner_words.text` (spec 0015 4.3)."""
NARRATION_MAX = 4_000
"""Maximum characters of `narration.text_en` (spec 0015 4.3)."""
OTHER_NEED_MIN = 40
"""Minimum characters of the `need_en` of category `other` (spec 0015 4.3)."""
SEQ_MIN = 1
"""First sequence number of `records.jsonl` and of a triage file (spec 0015 4.3, 4.3.1)."""

_Sha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
_Commit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
_At = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")]
_Date = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]
_Release = Annotated[str, StringConstraints(pattern=r"^.+==.+$")]
_By = Annotated[str, StringConstraints(pattern=r"^(agent:.+|harness|dev-session:.+)$")]
_Count = Annotated[int, Field(ge=0)]
_Seq = Annotated[int, Field(ge=SEQ_MIN)]
_Title = Annotated[str, StringConstraints(max_length=TITLE_EN_MAX)]
_OwnerText = Annotated[str, StringConstraints(max_length=OWNER_TEXT_MAX)]
_Narration = Annotated[str, StringConstraints(max_length=NARRATION_MAX)]


class _P(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class Redaction(_P):
    """One withheld span: the field, the guard rule, the offsets and the span hash (spec 0015 4.3)."""

    field: str
    rule: str
    start: _Count
    end: _Count
    span_sha256: _Sha


class AgentInfo(_P):
    """The agent that wrote the record: the tool, and the model family and line only (spec 0015 4.3)."""

    tool: str
    model_line: str | None = None


class SessionInfo(_P):
    """The session the record was written in (spec 0015 4.3)."""

    place: Literal["local", "cloud"]
    tool_session_id: str | None = None
    transcript_sha256: _Sha | None = None


class RunTimings(_P):
    """Machine and waiting milliseconds and resume count of an attached run (spec 0015 4.3)."""

    machine_ms: _Count
    waiting_ms: _Count
    resumes: _Count


class NotFoundDetail(_P):
    """The embedded location of a need, so a cloud session needs no workspace (spec 0015 4.3)."""

    kind: str | None = None
    field: str | None = None
    step_path: str | None = None
    message_en: str | None = None


class _Record(_P):
    """Common fields of a task record (spec 0015 4.3); each kind adds `kind` and its own fields."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False, serialize_by_alias=True)

    # `schema` is an alias: the attribute cannot take the name of the deprecated `BaseModel.schema`.
    schema_: Literal["harness.tasklog_record/1"] = Field(alias="schema")
    task_id: str
    seq: _Seq
    at: _At
    by: _By
    policy: Literal["full", "sanitized"]
    redactions: list[Redaction]
    prev_sha256: _Sha


class TaskOpened(_Record):
    """The first record of a task (spec 0015 4.3)."""

    kind: Literal["task_opened"]
    title_en: _Title
    agent: AgentInfo
    session: SessionInfo
    repo_commit: _Commit
    integration_branch: str
    harness_version: str
    continues: str | None = None
    project_label: str | None = None


class OwnerWords(_Record):
    """The owner's verbatim words with the hash of the original bytes (spec 0015 4.3)."""

    kind: Literal["owner_words"]
    role: Literal["request", "correction", "clarification", "answer"]
    lang: str
    text: _OwnerText
    text_sha256: _Sha
    gloss_en: str | None = None


class Narration(_Record):
    """One English sentence of the story (spec 0015 4.3)."""

    kind: Literal["narration"]
    text_en: _Narration


class Searched(_Record):
    """What the agent searched for, where, and what it found (spec 0015 4.3)."""

    kind: Literal["searched"]
    for_en: str
    where: Literal[
        "workflow_registry",
        "allowlist",
        "edit_kinds",
        "calcs",
        "code_pack_checks",
        "cli_tools",
        "project_lane_tools",
        "specs",
        "docs",
        "other",
    ]
    result: Literal["found", "partial", "not_found"]
    detail_en: str
    refs: list[str]
    catalog: Literal["available", "unavailable"]


class NotFound(_Record):
    """A missing capability: `not_implemented` needs a gap id, `other` a long `need_en` (spec 0015 4.3)."""

    kind: Literal["not_found"]
    need_id: str
    category: Literal[
        "no_workflow",
        "tool_not_on_allowlist",
        "no_edit_kind",
        "not_implemented",
        "no_calc",
        "calc_not_approved",
        "no_code_pack_check",
        "host_limitation",
        "server_limitation",
        "value_without_source",
        "harness_unavailable",
        "harness_defect",
        "other",
    ]
    need_en: str
    target: str | None = None
    gap_id: str | None = None
    code: str | int | None = None
    evidence: list[str]
    detail: NotFoundDetail | None = None
    blocking: StrictBool
    words_ref: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.category == "not_implemented" and self.gap_id is None:
            raise ValueError("gap_id is required when category is not_implemented")
        if self.category == "other" and len(self.need_en) < OTHER_NEED_MIN:
            raise ValueError(f"need_en of other holds at least {OTHER_NEED_MIN} characters")
        return self


class DidInstead(_Record):
    """What the agent did instead of the missing capability (spec 0015 4.3)."""

    kind: Literal["did_instead"]
    way: Literal["harness_workflow", "owner_by_hand", "partial", "deferred", "nothing"]
    text_en: str
    refs: list[str]


class Problem(_Record):
    """A defect, not a missing capability (spec 0015 4.3)."""

    kind: Literal["problem"]
    text_en: str
    evidence: list[str]


class Handoff(_Record):
    """What is done, left and why, and to whom the task goes (spec 0015 4.3)."""

    kind: Literal["handoff"]
    to: Literal["owner", "next_session", "dev_session"]
    done_en: str
    left_en: str
    why_en: str


class RunRefused(_Record):
    """A run refused before any run folder existed (spec 0015 4.3)."""

    kind: Literal["run_refused"]
    workflow: str
    exit_code: int
    code: str
    missing: list[str]
    message_en: str


class RunAttached(_Record):
    """A run attached to the task, read from its journal (spec 0015 4.3)."""

    kind: Literal["run_attached"]
    run_id: str
    workflow: str
    status: str  # RunView.status: RUNNING, INTERRUPTED, PAUSED, NEEDS_ENGINEER, COMPLETED or FAILED
    exit_code: int | None = None
    event_count: _Count
    last_seq: _Count
    chain_sha256: _Sha
    report: str
    unreleased_tools: dict[str, JsonValue]
    timings: RunTimings
    model_files: list[str]


class RunFact(_Record):
    """One fact derived from an attached run's journal (spec 0015 4.3, 4.8)."""

    kind: Literal["run_fact"]
    run_id: str
    journal_seq: _Count
    event: str
    summary_en: str
    code: str | None = None
    gap: str | None = None
    field: str | None = None
    reason: str | None = None
    owner_text: str | None = None


class TaskClosed(_Record):
    """The close of a task with its status and open needs (spec 0015 4.3)."""

    kind: Literal["task_closed"]
    status: Literal["DONE", "DONE_WITH_CONCERNS", "BLOCKED", "NEEDS_CONTEXT", "WITHDRAWN"]
    summary_en: str
    open_needs: list[str]
    next_en: str | None = None


class WithheldAfter(_Record):
    """A span withheld after the push, naming the line it changed (spec 0015 4.3, 4.4)."""

    kind: Literal["withheld_after"]
    target_seq: _Seq
    field: str
    rule: str
    span_sha256: _Sha
    line_sha256_before: _Sha
    reason_en: str


TaskRecord = Annotated[
    TaskOpened
    | OwnerWords
    | Narration
    | Searched
    | NotFound
    | DidInstead
    | Problem
    | Handoff
    | RunRefused
    | RunAttached
    | RunFact
    | TaskClosed
    | WithheldAfter,
    Field(discriminator="kind"),
]
"""A task-log record: the closed 13-kind union of spec 0015 4.3."""


class _Triage(_P):
    """Common fields of a triage line (spec 0015 4.3.1); a triage line carries no policy."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False, serialize_by_alias=True)

    # `schema` is an alias: the attribute cannot take the name of the deprecated `BaseModel.schema`.
    schema_: Literal["harness.tasklog_triage/1"] = Field(alias="schema")
    need_id: str
    seq: _Seq
    at: _At
    by: _By
    redactions: list[Redaction]
    prev_sha256: _Sha


class Triaged(_Triage):
    """The triage of a need; `duplicate_of` is set exactly for `duplicate` (spec 0015 4.3.1)."""

    kind: Literal["triaged"]
    outcome: Literal["new_spec", "covered", "host_limitation", "out_of_scope", "duplicate", "defect"]
    public_en: str
    public_en_sha256: _Sha
    work_item: str | None = None
    issue: int | None = None
    spec: str | None = None
    plan: str | None = None
    duplicate_of: str | None = None

    @model_validator(mode="after")
    def _link(self) -> Self:
        if (self.outcome == "duplicate") != (self.duplicate_of is not None):
            raise ValueError("duplicate_of is set exactly when outcome is duplicate")
        return self


class PublicReleased(_Triage):
    """The owner's release of the exact `public_en` its hash names (spec 0015 4.3.1)."""

    kind: Literal["public_released"]
    public_en_sha256: _Sha
    public_en_released: Literal["owner"]
    released_on: _Date
    reply_sha256: _Sha


class Answered(_Triage):
    """The release and commit that answered the need (spec 0015 4.3.1)."""

    kind: Literal["answered"]
    release: _Release
    commit: _Commit


class TriageWithheldAfter(_Triage):
    """A span withheld in a triage line after the push (spec 0015 4.3.1, 4.4)."""

    kind: Literal["withheld_after"]
    target_seq: _Seq
    field: str
    rule: str
    span_sha256: _Sha
    line_sha256_before: _Sha
    reason_en: str


TriageLine = Annotated[
    Triaged | PublicReleased | Answered | TriageWithheldAfter,
    Field(discriminator="kind"),
]
"""A triage-file line: the closed 4-kind union of spec 0015 4.3.1."""
