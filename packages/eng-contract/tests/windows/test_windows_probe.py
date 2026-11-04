"""Windows probe against the real Windows API (plan T13; spec 4.5.2; AC15). Runs in the Windows CI job only.

The tests are defined only on Windows, so the Linux run collects none and records no skip.
"""

import sys

if sys.platform == "win32":
    from pathlib import Path, PureWindowsPath

    import pytest

    from eng_contract.store import LocationClass
    from eng_contract.store._probe_windows import CtypesWinApi, WindowsProbe

    NOT_UNDER_SYNC_ROOT = 0x80070186  # HRESULT_FROM_WIN32(ERROR_CLOUD_FILE_NOT_UNDER_SYNC_ROOT = 390), winerror.h

    @pytest.mark.windows
    def test_classifications(tmp_path: Path) -> None:
        onedrive = tmp_path / "OneDrive"
        onedrive.mkdir()
        probe = WindowsProbe(CtypesWinApi(), {"OneDrive": str(onedrive)})
        assert probe.classify(tmp_path) is LocationClass.LOCAL
        assert probe.classify(PureWindowsPath(r"\\server\share\ws")) is LocationClass.NETWORK
        assert probe.classify(onedrive / "ws") is LocationClass.CLOUD_SYNCED

    @pytest.mark.windows
    def test_real_sync_root_status_of_a_local_folder(tmp_path: Path) -> None:
        # None means cldapi.dll or its entry point is absent on this machine; the rules then continue to LOCAL.
        assert CtypesWinApi().sync_root_status(str(tmp_path)) in (NOT_UNDER_SYNC_ROOT, None)

    @pytest.mark.windows
    def test_real_queries_report_failures(tmp_path: Path) -> None:
        api = CtypesWinApi()
        assert api.file_attributes(str(tmp_path / "missing")) == 0xFFFFFFFF
        assert api.drive_type(tmp_path.anchor) in (3, 6)
