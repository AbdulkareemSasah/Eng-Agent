"""The built wheel holds no test code (plan 0002 T4; spec 0002 AC35)."""

import shutil
import subprocess
import zipfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def test_fakes_not_shipped(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    subprocess.run(  # noqa: S603  # B-123: fixed argument list, no shell, the uv found on PATH
        [uv, "build", "--wheel", "--out-dir", str(tmp_path), str(PACKAGE_ROOT)],
        check=True,
        capture_output=True,
        timeout=300,
    )
    wheels = list(tmp_path.glob("eng_harness-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
    assert any(n.startswith("eng_harness/") for n in names)
    assert not [n for n in names if {"tests", "fakes", "sasaah_csi"} & set(n.split("/"))]
