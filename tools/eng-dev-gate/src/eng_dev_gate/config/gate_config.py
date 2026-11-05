"""The root ``.gate/gate.yml`` and the mode logic (spec 4.4, 4.16).

The mode comes only from ``bootstrap.enabled`` in the gate root's file. The loader takes no environment, option or
package setting, so none of them can switch it (AC4).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, StrictBool, StringConstraints, ValidationError

from eng_dev_gate.report import Finding, Severity
from eng_dev_gate.results import ExitCode, GateError, UsageError

Name = Annotated[str, StringConstraints(min_length=1)]
Globs = list[Name]


class ConfigError(UsageError):
    """A configuration error with its diagnostic ``code`` (CF001, CF006, CF007, CF008); exit 2."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code} {message}")
        self.code = code


class ModeError(GateError):
    """The awaiting-owner path was used outside bootstrap mode: a programming error (AC3)."""

    exit_code = ExitCode.ENVIRONMENT


class Mode(StrEnum):
    """Gate mode: ``bootstrap`` (ADR-0028 section 4) or ``normal``."""

    BOOTSTRAP = "bootstrap"
    NORMAL = "normal"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Bootstrap(_Model):
    """``bootstrap.enabled`` and the integration branch used in its place of ``main`` while it is on."""

    enabled: StrictBool
    gate_branch: Name


class Identities(_Model):
    """Logins of the owner, the agent identities and the reviewer app; all must be set to switch bootstrap off."""

    owner_login: str = ""
    agent_logins: list[str] = Field(default_factory=list)
    reviewer_app: str = ""

    def complete(self) -> bool:
        """Return whether every field is non-empty."""
        return bool(self.owner_login and self.reviewer_app and self.agent_logins and all(self.agent_logins))


class Agents(_Model):
    """``agents.unmanaged_ok``: globs of tracked ``AGENTS.md`` files that no ``agents.yml`` manages."""

    unmanaged_ok: Globs = Field(default_factory=list)


class Limits(_Model):
    """Limits: ``diff_lines``, ``max_task_lines`` (lines), ``test_run_seconds`` (s), ``max_file_bytes`` (bytes),
    ``mutation_run_seconds`` (s, the bound of the mutmut run)."""

    diff_lines: PositiveInt
    max_task_lines: PositiveInt
    test_run_seconds: PositiveInt
    max_file_bytes: PositiveInt
    mutation_run_seconds: PositiveInt


class LicenseException(_Model):
    """An allowed dependency whose license is not on the allow list, with the ADR that accepts it."""

    distribution: Name
    license: Name
    adr: Name


class SecretAllow(_Model):
    """An allowed secret-scan hit: ``rule``, ``path`` and ``fingerprint``."""

    rule: Name
    path: Name
    fingerprint: Name


class Secrets(_Model):
    """``secrets.allow`` entries."""

    allow: list[SecretAllow] = Field(default_factory=list)


class GateConfig(_Model):
    """The whole ``.gate/gate.yml`` (spec section 5)."""

    bootstrap: Bootstrap
    main_branch: Name
    identities: Identities = Field(default_factory=Identities)
    spec_globs: Globs
    plan_globs: Globs
    test_globs: Globs
    generated_globs: Globs
    spike_globs: Globs
    agents: Agents = Field(default_factory=Agents)
    limits: Limits
    license_exceptions: list[LicenseException] = Field(default_factory=list)
    secrets: Secrets = Field(default_factory=Secrets)

    @property
    def mode(self) -> Mode:
        """The mode, from ``bootstrap.enabled`` alone."""
        return Mode.BOOTSTRAP if self.bootstrap.enabled else Mode.NORMAL

    @property
    def gate_branch(self) -> str:
        """The branch plans and specs are loaded from and pull requests target (spec 4.4)."""
        return self.bootstrap.gate_branch if self.bootstrap.enabled else self.main_branch

    def validated(self) -> Self:
        """Return ``self`` if bootstrap is on or the identities are complete.

        Raises:
            ConfigError: CF008, bootstrap is off and ``identities`` is incomplete.
        """
        if self.mode is Mode.NORMAL and not self.identities.complete():
            raise ConfigError(
                "CF008", "bootstrap is off but identities (owner_login, agent_logins, reviewer_app) are incomplete"
            )
        return self


def load_gate_config(gate_root: Path) -> GateConfig:
    """Read ``<gate_root>/.gate/gate.yml``.

    Args:
        gate_root: the workspace root, or the checkout of the base commit in pull-request context (spec 4.16).

    Raises:
        ConfigError: CF007 when the file is missing, unreadable, not YAML or invalid; CF008 when bootstrap is off and
            the identities are incomplete.
    """
    path = gate_root / ".gate" / "gate.yml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError("CF007", f"cannot read {path}: {error}") from error
    return parse_gate_config(text, str(path))


def parse_gate_config(text: str, source: str) -> GateConfig:
    """Parse the text of a ``gate.yml`` (a file, or the file at the base commit); ``source`` names it in errors.

    Raises:
        ConfigError: CF007 when the text is not YAML or invalid; CF008 when bootstrap is off and the identities are
            incomplete.
    """
    try:
        return GateConfig.model_validate(yaml.safe_load(text)).validated()
    except yaml.YAMLError as error:
        raise ConfigError("CF007", f"cannot read {source}: {error}") from error
    except ValidationError as error:
        raise ConfigError("CF007", f"invalid {source}: {error}") from error


def awaiting_finding(config: GateConfig, code: str, message: str, path: str | None = None) -> Finding:
    """Return the ``awaiting`` finding for an owner or identity condition (AW01 to AW09).

    Raises:
        ModeError: the mode is not bootstrap; outside it a check must verify the condition or fail (AC3).
    """
    if config.mode is not Mode.BOOTSTRAP:
        raise ModeError(f"{code}: awaiting owner is only available in bootstrap mode")
    return Finding(code=code, severity=Severity.AWAITING, path=path, message=message)
