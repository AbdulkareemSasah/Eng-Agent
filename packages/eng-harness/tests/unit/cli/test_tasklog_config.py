"""The [tasklog] configuration section (plan 0015 T4a; spec 0015 AC26, section 4.6)."""

from pathlib import Path

import pytest

from eng_harness.cli import ConfigError
from eng_harness.cli._config import load_config


def test_harness_toml_push_key_refused(tmp_path: Path) -> None:
    """A `push` key in `[tasklog]` is refused as an unknown key (spec 0015 4.6, AC26)."""
    path = tmp_path / "harness.toml"
    path.write_text(
        '[tasklog]\nintegration_branch = "build/v1"\npolicy = "full"\nrequire_task = true\npush = true\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    assert caught.value.key == "tasklog.push"
