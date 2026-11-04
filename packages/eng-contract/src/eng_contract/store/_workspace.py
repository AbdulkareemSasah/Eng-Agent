"""Workspace resolution and the location-probe port (spec 4.5.1, 4.5.2).

Purpose: find the folder that holds results and model state, and refuse a folder that is not plainly local.
Units: none. Errors: `LocalWorkspaceError` (`PRECONDITION_FAILED`, `precondition: local_workspace`).
"""

import importlib
import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from eng_contract.errors import ContractError, ErrorCode, Precondition


class LocationClass(StrEnum):
    """Where a folder lives; only `LOCAL` is accepted for a workspace."""

    LOCAL = "local"
    NETWORK = "network"
    CLOUD_SYNCED = "cloud_synced"
    UNKNOWN = "unknown"


class LocationProbe(Protocol):
    """Classifies a folder; the real probes are per platform, `FakeLocationProbe` is for tests."""

    def classify(self, path: Path) -> LocationClass:
        """Return the class of `path`; never `LOCAL` when the class could not be determined."""
        ...


class FakeLocationProbe:
    """Test double: the configured class of the longest matching path prefix, else `default`."""

    def __init__(
        self, classes: Mapping[Path, LocationClass] | None = None, default: LocationClass = LocationClass.LOCAL
    ):
        self._classes = dict(classes or {})
        self._default = default

    def classify(self, path: Path) -> LocationClass:
        """Return the class configured for the longest prefix of `path`."""
        matches = [prefix for prefix in self._classes if path == prefix or path.is_relative_to(prefix)]
        return self._classes[max(matches, key=lambda prefix: len(prefix.parts))] if matches else self._default


class LocalWorkspaceError(ContractError):
    """The workspace is not configured, not absolute, not creatable or not local (`PRECONDITION_FAILED`)."""

    def __init__(self, message: str, hint: str, received: str | None = None) -> None:
        super().__init__(
            ErrorCode.PRECONDITION_FAILED,
            message,
            precondition=Precondition.local_workspace,
            hint=hint,
            received=received,
        )


class Workspace(BaseModel):
    """A resolved workspace: `root` is absolute; results and model state live under `.eng/`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    root: Path
    classification: LocationClass

    @field_validator("root")
    @classmethod
    def _absolute(cls, root: Path) -> Path:
        if not root.is_absolute():
            raise ValueError("workspace root must be absolute")
        return root

    @property
    def results_dir(self) -> Path:
        """Folder of `<yyyy>/<mm>/<dd>/<result_id>.json` records."""
        return self.root / ".eng" / "results"

    @property
    def models_dir(self) -> Path:
        """Folder of one state file per model."""
        return self.root / ".eng" / "state" / "models"


def _configured_root(env: Mapping[str, str]) -> Path:
    """Rules 1 to 3 of spec 4.5.1; the process working directory is never consulted."""
    explicit = env.get("ENG_WORKSPACE")
    if explicit:
        if not Path(explicit).is_absolute():
            raise LocalWorkspaceError("ENG_WORKSPACE is not an absolute path", "ENG_WORKSPACE must be absolute")
        return Path(os.path.abspath(explicit))
    appdata = env.get("LOCALAPPDATA")
    if appdata and Path(appdata).is_absolute():
        return Path(os.path.abspath(appdata)) / "eng" / "workspaces" / "default"
    raise LocalWorkspaceError("no workspace is configured", "set ENG_WORKSPACE")


def resolve_workspace(env: Mapping[str, str], probe: LocationProbe) -> Workspace:
    """Resolve, create and classify the workspace folder (callers pass `os.environ` at the edge).

    Raises:
        LocalWorkspaceError: not configured, relative, not creatable, or not classified `LOCAL`.
    """
    root = _configured_root(env)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LocalWorkspaceError(
            "the workspace folder cannot be created", "set ENG_WORKSPACE to a writable folder"
        ) from exc
    classification = probe.classify(root)
    if classification is not LocationClass.LOCAL:
        raise LocalWorkspaceError(
            f"the workspace is {classification.value}, not local",
            f"location is {classification.value}; set ENG_WORKSPACE to a folder on a local drive",
            classification.value,
        )
    return Workspace(root=root, classification=classification)


def default_location_probe() -> LocationProbe:
    """The Windows probe on Windows and the POSIX probe elsewhere."""
    if os.name == "nt":  # not sys.platform: the Windows-only code is guarded there, and mypy checks both platforms
        probe: LocationProbe = importlib.import_module("eng_contract.store._probe_windows").system_probe()
        return probe
    from eng_contract.store._probe_posix import PosixProbe

    return PosixProbe()
