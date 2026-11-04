"""Workspace resolution, location probes and the result store (spec 4.5)."""

from eng_contract._fs import StoreIntegrityError, StoreWriteError
from eng_contract.store._results import ResultStore
from eng_contract.store._workspace import (
    FakeLocationProbe,
    LocationClass,
    LocationProbe,
    Workspace,
    default_location_probe,
    resolve_workspace,
)

__all__ = [
    "FakeLocationProbe",
    "LocationClass",
    "LocationProbe",
    "ResultStore",
    "StoreIntegrityError",
    "StoreWriteError",
    "Workspace",
    "default_location_probe",
    "resolve_workspace",
]
