"""Workspace resolution and location probes (plan T13; spec 4.5.1, 4.5.2; AC13, AC14).

Expected paths and classifications come from the spec text, not from the implementation.
"""

import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import ValidationError

from eng_contract.errors import ContractError, ErrorCode, Precondition
from eng_contract.store import (
    FakeLocationProbe,
    LocationClass,
    Workspace,
    default_location_probe,
    resolve_workspace,
)
from eng_contract.store._probe_posix import PosixProbe
from eng_contract.store._probe_windows import WindowsProbe

LOCAL_PROBE = FakeLocationProbe()


def _refused(env: Mapping[str, str], probe: FakeLocationProbe = LOCAL_PROBE) -> ContractError:
    with pytest.raises(ContractError) as info:
        resolve_workspace(env, probe)
    assert info.value.detail.code is ErrorCode.PRECONDITION_FAILED
    assert info.value.detail.precondition is Precondition.local_workspace
    assert info.value.detail.retryable is False
    return info.value


def test_resolution_order(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    appdata = tmp_path / "appdata"
    # ENG_WORKSPACE wins over LOCALAPPDATA.
    both = {"ENG_WORKSPACE": str(explicit), "LOCALAPPDATA": str(appdata)}
    assert resolve_workspace(both, LOCAL_PROBE).root == explicit
    assert explicit.is_dir()
    assert not appdata.exists()
    # Unset or empty ENG_WORKSPACE falls through to <LOCALAPPDATA>/eng/workspaces/default.
    for env in ({"LOCALAPPDATA": str(appdata)}, {"ENG_WORKSPACE": "", "LOCALAPPDATA": str(appdata)}):
        ws = resolve_workspace(env, LOCAL_PROBE)
        assert ws.root == appdata / "eng" / "workspaces" / "default"
        assert ws.root.is_dir()
    # The path is used as given: "~" is not expanded, so it is relative and refused; ".." is only normalized.
    assert _refused({"ENG_WORKSPACE": "~/ws"}).detail.hint == "ENG_WORKSPACE must be absolute"
    assert resolve_workspace({"ENG_WORKSPACE": str(explicit / "x" / ".." / "y")}, LOCAL_PROBE).root == explicit / "y"


def test_never_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert _refused({}).detail.hint == "set ENG_WORKSPACE"
    assert _refused({"ENG_WORKSPACE": "relative/ws"}).detail.hint == "ENG_WORKSPACE must be absolute"
    # A relative LOCALAPPDATA is not "set and absolute", so rule 3 applies.
    assert _refused({"LOCALAPPDATA": "relative"}).detail.hint == "set ENG_WORKSPACE"
    assert _refused({"LOCALAPPDATA": ""}).detail.hint == "set ENG_WORKSPACE"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("cls", [LocationClass.NETWORK, LocationClass.CLOUD_SYNCED, LocationClass.UNKNOWN])
def test_refuses_non_local(tmp_path: Path, cls: LocationClass) -> None:
    probe = FakeLocationProbe({tmp_path: cls})
    error = _refused({"ENG_WORKSPACE": str(tmp_path / "ws")}, probe)
    assert error.detail.received == cls.value
    assert cls.value in (error.detail.hint or "")
    assert "ENG_WORKSPACE" in (error.detail.hint or "")


def test_classification_follows_creation(tmp_path: Path) -> None:
    seen: list[bool] = []

    class Probe:
        def classify(self, path: Path) -> LocationClass:
            seen.append(path.is_dir())
            return LocationClass.LOCAL

    ws = resolve_workspace({"ENG_WORKSPACE": str(tmp_path / "a" / "b")}, Probe())
    assert seen == [True]
    assert ws.classification is LocationClass.LOCAL


def test_uncreatable_folder_is_a_precondition_failure(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    assert _refused({"ENG_WORKSPACE": str(blocker / "ws")}).detail.hint is not None


def test_workspace_layout(tmp_path: Path) -> None:
    ws = Workspace(root=tmp_path, classification=LocationClass.LOCAL)
    assert ws.results_dir == tmp_path / ".eng" / "results"
    assert ws.models_dir == tmp_path / ".eng" / "state" / "models"
    with pytest.raises(ValidationError):
        Workspace(root=Path("relative"), classification=LocationClass.LOCAL)
    with pytest.raises(ValidationError):
        Workspace.model_validate({"root": tmp_path, "classification": "local", "extra": 1})


def test_fake_probe_longest_prefix(tmp_path: Path) -> None:
    probe = FakeLocationProbe(
        {tmp_path / "share": LocationClass.NETWORK, tmp_path / "share" / "sync": LocationClass.CLOUD_SYNCED},
        default=LocationClass.UNKNOWN,
    )
    assert probe.classify(tmp_path / "share" / "a") is LocationClass.NETWORK
    assert probe.classify(tmp_path / "share" / "sync" / "a") is LocationClass.CLOUD_SYNCED
    assert probe.classify(tmp_path / "share2") is LocationClass.UNKNOWN
    assert FakeLocationProbe().classify(tmp_path) is LocationClass.LOCAL


def test_default_probe_matches_platform() -> None:
    expected = WindowsProbe if sys.platform == "win32" else PosixProbe
    assert isinstance(default_location_probe(), expected)


MOUNTINFO = r"""22 28 0:21 / /proc rw,nosuid - proc proc rw
28 1 8:1 / / rw,relatime shared:1 - ext4 /dev/sda1 rw
40 28 0:35 / /mnt/share rw,relatime - nfs4 server:/export rw,vers=4.2
41 40 8:2 / /mnt/share/scratch rw,relatime - ext4 /dev/sdb1 rw
42 28 0:36 / /mnt/with\040space rw,relatime - cifs //srv/s rw
"""


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/data/ws", LocationClass.LOCAL),
        ("/mnt/share", LocationClass.NETWORK),
        ("/mnt/share/ws", LocationClass.NETWORK),
        ("/mnt/share/scratch/ws", LocationClass.LOCAL),
        ("/mnt/share2/ws", LocationClass.LOCAL),
        ("/mnt/with space/ws", LocationClass.NETWORK),
    ],
)
def test_posix_probe_mounts(tmp_path: Path, path: str, expected: LocationClass) -> None:
    info = tmp_path / "mountinfo"
    info.write_text(MOUNTINFO, encoding="utf-8")
    assert PosixProbe(info).classify(Path(path)) is expected


@pytest.mark.parametrize("fstype", ["nfs", "nfs4", "cifs", "smb3", "smbfs", "afs", "fuse.sshfs", "9p"])
def test_posix_probe_network_types(tmp_path: Path, fstype: str) -> None:
    info = tmp_path / "mountinfo"
    info.write_text(f"40 28 0:35 / /data rw - {fstype} src rw\n", encoding="utf-8")
    assert PosixProbe(info).classify(Path("/data/ws")) is LocationClass.NETWORK


def test_posix_probe_unreadable_or_odd_input_is_local(tmp_path: Path) -> None:
    assert PosixProbe(tmp_path / "missing").classify(Path("/data/ws")) is LocationClass.LOCAL
    info = tmp_path / "mountinfo"
    info.write_text("garbage line\n\n40 28 0:35 / /data rw\n", encoding="utf-8")
    assert PosixProbe(info).classify(Path("/data/ws")) is LocationClass.LOCAL
