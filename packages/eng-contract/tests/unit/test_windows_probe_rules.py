"""Windows probe rules over a fake Windows API, on every OS (plan T13; spec 4.5.2; AC15a).

The numeric constants are written out here from the Windows SDK headers (winbase.h, winnt.h, winerror.h), independently
of the implementation: a wrong value in the implementation fails these tests.
"""

from collections.abc import Mapping
from pathlib import PureWindowsPath

import pytest

from eng_contract.store import LocationClass
from eng_contract.store._probe_windows import WindowsProbe, hresult_from_win32

DRIVE_UNKNOWN, DRIVE_NO_ROOT_DIR, DRIVE_REMOVABLE, DRIVE_FIXED, DRIVE_REMOTE, DRIVE_CDROM, DRIVE_RAMDISK = range(7)
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
ATTR_DIRECTORY = 0x10
ATTR_PINNED = 0x00080000
ATTR_UNPINNED = 0x00100000
ATTR_RECALL_ON_OPEN = 0x00040000
ATTR_RECALL_ON_DATA_ACCESS = 0x00400000
S_OK = 0
HR_MORE_DATA = 0x800700EA  # HRESULT_FROM_WIN32(ERROR_MORE_DATA = 234)
HR_NOT_UNDER_SYNC_ROOT = 0x80070186  # HRESULT_FROM_WIN32(ERROR_CLOUD_FILE_NOT_UNDER_SYNC_ROOT = 390)
HR_ACCESS_DENIED = 0x80070005
E_FAIL = 0x80004005


class FakeWinApi:
    """Configured answers; `calls` records which queries the rules made."""

    def __init__(
        self,
        drive: int = DRIVE_FIXED,
        attributes: int = ATTR_DIRECTORY,
        sync_root: int | None = HR_NOT_UNDER_SYNC_ROOT,
    ) -> None:
        self.drive, self.attributes, self.sync_root = drive, attributes, sync_root
        self.calls: list[tuple[str, str]] = []

    def drive_type(self, root: str) -> int:
        self.calls.append(("drive_type", root))
        return self.drive

    def file_attributes(self, path: str) -> int:
        self.calls.append(("file_attributes", path))
        return self.attributes

    def sync_root_status(self, path: str) -> int | None:
        self.calls.append(("sync_root_status", path))
        return self.sync_root


def _classify(api: FakeWinApi, path: str = r"C:\ws", env: Mapping[str, str] | None = None) -> LocationClass:
    return WindowsProbe(api, env or {}).classify(PureWindowsPath(path))


def _queried(api: FakeWinApi, name: str) -> bool:
    return any(called == name for called, _ in api.calls)


def test_hresult_from_win32() -> None:
    assert hresult_from_win32(234) == HR_MORE_DATA
    assert hresult_from_win32(390) == HR_NOT_UNDER_SYNC_ROOT


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (S_OK, LocationClass.CLOUD_SYNCED),
        (HR_MORE_DATA, LocationClass.CLOUD_SYNCED),
        (HR_NOT_UNDER_SYNC_ROOT, LocationClass.LOCAL),
        (None, LocationClass.LOCAL),  # cldapi.dll or its entry point is missing
        (HR_ACCESS_DENIED, LocationClass.UNKNOWN),
        (E_FAIL, LocationClass.UNKNOWN),
        (0x80070057, LocationClass.UNKNOWN),
    ],
)
def test_result_code_mapping(status: int | None, expected: LocationClass) -> None:
    api = FakeWinApi(sync_root=status)
    assert _classify(api) is expected
    assert ("sync_root_status", r"C:\ws") in api.calls


@pytest.mark.parametrize(
    ("drive", "expected"),
    [
        (DRIVE_REMOTE, LocationClass.NETWORK),
        (DRIVE_FIXED, LocationClass.LOCAL),
        (DRIVE_RAMDISK, LocationClass.LOCAL),
        (DRIVE_REMOVABLE, LocationClass.UNKNOWN),
        (DRIVE_CDROM, LocationClass.UNKNOWN),
        (DRIVE_UNKNOWN, LocationClass.UNKNOWN),
        (DRIVE_NO_ROOT_DIR, LocationClass.UNKNOWN),
    ],
)
def test_drive_types(drive: int, expected: LocationClass) -> None:
    api = FakeWinApi(drive=drive)
    assert _classify(api, r"D:\data\ws") is expected
    assert api.calls[0] == ("drive_type", "D:\\")


@pytest.mark.parametrize("path", [r"\\server\share\ws", r"\\?\UNC\server\share\ws", r"\\?\unc\server\share"])
def test_unc_is_network_without_queries(path: str) -> None:
    api = FakeWinApi()
    assert _classify(api, path) is LocationClass.NETWORK
    assert api.calls == []


def test_extended_length_local_path_uses_its_drive() -> None:
    api = FakeWinApi()
    assert _classify(api, r"\\?\C:\ws") is LocationClass.LOCAL
    assert api.calls[0] == ("drive_type", "C:\\")


@pytest.mark.parametrize(
    "attributes",
    [ATTR_PINNED, ATTR_UNPINNED, ATTR_RECALL_ON_OPEN, ATTR_RECALL_ON_DATA_ACCESS, ATTR_DIRECTORY | ATTR_PINNED],
)
def test_cloud_attributes(attributes: int) -> None:
    api = FakeWinApi(attributes=attributes, sync_root=HR_NOT_UNDER_SYNC_ROOT)
    assert _classify(api) is LocationClass.CLOUD_SYNCED
    assert not _queried(api, "sync_root_status")


def test_failed_attribute_query_is_unknown() -> None:
    api = FakeWinApi(attributes=INVALID_FILE_ATTRIBUTES, sync_root=S_OK)
    assert _classify(api) is LocationClass.UNKNOWN
    assert not _queried(api, "sync_root_status")


@pytest.mark.parametrize("variable", ["OneDrive", "OneDriveCommercial", "OneDriveConsumer"])
def test_onedrive_folder_is_cloud_synced(variable: str) -> None:
    # Rule 3 comes before the attribute and sync-root queries, so their failures cannot hide it.
    api = FakeWinApi(attributes=INVALID_FILE_ATTRIBUTES, sync_root=E_FAIL)
    env = {variable: r"D:\Sync\OneDrive"}
    assert _classify(api, r"d:\SYNC\onedrive\eng\ws", env) is LocationClass.CLOUD_SYNCED
    assert _classify(api, r"D:\Sync\OneDrive", env) is LocationClass.CLOUD_SYNCED
    assert not _queried(api, "file_attributes")


def test_onedrive_lookalikes_and_empty_values_do_not_match() -> None:
    env = {"OneDrive": r"D:\Sync\OneDrive", "OneDriveCommercial": "", "Other": r"C:\ws"}
    assert _classify(FakeWinApi(), r"D:\Sync\OneDrive2\ws", env) is LocationClass.LOCAL
    assert _classify(FakeWinApi(), r"C:\ws", env) is LocationClass.LOCAL


def test_drive_type_rules_come_before_onedrive() -> None:
    env = {"OneDrive": r"D:\OneDrive"}
    assert _classify(FakeWinApi(drive=DRIVE_REMOTE), r"D:\OneDrive\ws", env) is LocationClass.NETWORK
    assert _classify(FakeWinApi(drive=DRIVE_CDROM), r"D:\OneDrive\ws", env) is LocationClass.UNKNOWN


@pytest.mark.parametrize("drive", [DRIVE_UNKNOWN, DRIVE_NO_ROOT_DIR, DRIVE_REMOVABLE, DRIVE_CDROM])
@pytest.mark.parametrize("attributes", [INVALID_FILE_ATTRIBUTES, ATTR_DIRECTORY])
@pytest.mark.parametrize("status", [HR_ACCESS_DENIED, E_FAIL])
def test_failures_never_yield_local(drive: int, attributes: int, status: int) -> None:
    assert _classify(FakeWinApi(drive, attributes, status)) is LocationClass.UNKNOWN
