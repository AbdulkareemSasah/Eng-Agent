"""Windows location probe (spec 4.5.2): the rules over a `WinApi` port, importable on every OS (`ctypes` only).

Units: none. Errors: none raised; a failed query gives `UNKNOWN`, never `LOCAL`. The constants are software constants
of the SDK headers `winbase.h`, `winnt.h` and `winerror.h` and the Win32 pages named in the comments.
"""

import os
import sys
from collections.abc import Mapping
from pathlib import PurePath, PureWindowsPath
from typing import Protocol

from eng_contract.store._workspace import LocationClass

DRIVE_FIXED, DRIVE_REMOTE, DRIVE_RAMDISK = 3, 4, 6  # winbase.h; 0, 1, 2 and 5 are not local disks
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF  # fileapi.h, GetFileAttributesW failure
# winnt.h: FILE_ATTRIBUTE_PINNED, _UNPINNED, _RECALL_ON_OPEN and _RECALL_ON_DATA_ACCESS
_CLOUD_ATTRIBUTES = 0x00080000 | 0x00100000 | 0x00040000 | 0x00400000
S_OK, ERROR_MORE_DATA, ERROR_CLOUD_FILE_NOT_UNDER_SYNC_ROOT = 0, 234, 390  # winerror.h, "System Error Codes"
_ONEDRIVE_VARIABLES = ("OneDrive", "OneDriveCommercial", "OneDriveConsumer")


def hresult_from_win32(code: int) -> int:
    """`HRESULT_FROM_WIN32` (winerror.h) as an unsigned 32-bit value, for a positive Win32 error code."""
    return (code & 0xFFFF) | 0x80070000


class WinApi(Protocol):
    """The three Windows queries the rules need; `CtypesWinApi` is real, tests pass a fake."""

    def drive_type(self, root: str) -> int:
        """`GetDriveTypeW(root)`."""

    def file_attributes(self, path: str) -> int:
        """`GetFileAttributesW(path)`; `INVALID_FILE_ATTRIBUTES` when the call fails."""

    def sync_root_status(self, path: str) -> int | None:
        """`CfGetSyncRootInfoByPath` HRESULT as unsigned; `None` when `cldapi.dll` or its export is missing."""


class WindowsProbe:
    """Rules 1 to 6 of spec 4.5.2, first match wins, over a `WinApi` and the process environment."""

    def __init__(self, api: WinApi, env: Mapping[str, str]) -> None:
        self._api = api
        self._env = env

    def classify(self, path: PurePath) -> LocationClass:
        """Classify `path` (a folder); a failed query gives `UNKNOWN`, never `LOCAL`."""
        text = str(PureWindowsPath(path))
        if text.upper().startswith("\\\\?\\UNC\\") or (text.startswith("\\\\") and text[2:3] not in ("?", ".")):
            return LocationClass.NETWORK
        local = PureWindowsPath(text.removeprefix("\\\\?\\"))
        drive = self._api.drive_type(local.drive + "\\")
        if drive == DRIVE_REMOTE:
            return LocationClass.NETWORK
        if drive not in (DRIVE_FIXED, DRIVE_RAMDISK):
            return LocationClass.UNKNOWN
        for variable in _ONEDRIVE_VARIABLES:
            if (folder := self._env.get(variable)) and local.is_relative_to(PureWindowsPath(folder)):
                return LocationClass.CLOUD_SYNCED
        attributes = self._api.file_attributes(str(local))
        if attributes == INVALID_FILE_ATTRIBUTES:
            return LocationClass.UNKNOWN
        if attributes & _CLOUD_ATTRIBUTES:
            return LocationClass.CLOUD_SYNCED
        status = self._api.sync_root_status(str(local))
        if status in (S_OK, hresult_from_win32(ERROR_MORE_DATA)):
            return LocationClass.CLOUD_SYNCED
        if status is None or status == hresult_from_win32(ERROR_CLOUD_FILE_NOT_UNDER_SYNC_ROOT):
            return LocationClass.LOCAL
        return LocationClass.UNKNOWN


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class CtypesWinApi:
        """The real `WinApi` over `kernel32.dll` and `cldapi.dll`; its tests carry the `windows` marker."""

        def __init__(self) -> None:
            self._kernel32 = ctypes.WinDLL("kernel32")
            self._kernel32.GetFileAttributesW.restype = wintypes.DWORD  # 0xFFFFFFFF must not read as -1

        def drive_type(self, root: str) -> int:
            return int(self._kernel32.GetDriveTypeW(root))

        def file_attributes(self, path: str) -> int:
            return int(self._kernel32.GetFileAttributesW(path))

        def sync_root_status(self, path: str) -> int | None:
            """`CfGetSyncRootInfoByPath(path, CF_SYNC_ROOT_INFO_BASIC, ...)` as an unsigned HRESULT."""
            try:
                query = ctypes.WinDLL("cldapi").CfGetSyncRootInfoByPath
            except OSError, AttributeError:
                return None  # the Cloud Files API is absent: no sync root can exist (spec 4.5.2 rule 5)
            info, returned = ctypes.c_int64(), wintypes.DWORD()  # CF_SYNC_ROOT_BASIC_INFO (cfapi.h) is one int64
            result = query(path, 0, ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(returned))
            return int(result) & 0xFFFFFFFF

    def system_probe() -> WindowsProbe:
        """The probe over the real API and the process environment (the edge of the package)."""
        return WindowsProbe(CtypesWinApi(), os.environ)
