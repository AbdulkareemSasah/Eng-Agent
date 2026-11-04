"""The built wheel holds no test code (plan 0002 T4; spec 0002 AC35)."""

import asyncio
import os
import shutil
import zipfile
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


async def _build_wheel(uv: str, out_dir: Path) -> int:
    process = await asyncio.create_subprocess_exec(
        uv,
        "build",
        "--wheel",
        "--out-dir",
        str(out_dir),
        str(PACKAGE_ROOT),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return await asyncio.wait_for(process.wait(), 300)


def test_fakes_not_shipped(tmp_path: Path) -> None:
    if not (PACKAGE_ROOT / "README.md").is_file() and "MUTANT_UNDER_TEST" in os.environ:
        # The mutation step runs the tests in a copy without README.md, which the build needs; any other run fails.
        pytest.skip(
            "the package copy of the mutation step lacks README.md, so it cannot be built (B-369); expires 2026-12-31"
        )
    fake = PACKAGE_ROOT / "tests" / "fakes" / "sasaah_csi"
    assert (fake / "server.py").is_file()
    assert (fake / "schemas.json").is_file()
    uv = shutil.which("uv")
    assert uv is not None
    assert asyncio.run(_build_wheel(uv, tmp_path)) == 0
    wheels = list(tmp_path.glob("eng_harness-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
    assert any(n.startswith("eng_harness/") for n in names)
    assert not [n for n in names if {"tests", "fakes", "sasaah_csi"} & set(n.split("/"))]
