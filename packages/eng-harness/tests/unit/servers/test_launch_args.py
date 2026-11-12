"""Role argv of spec 0002 section 4.3.2 (plan 0002 T20; AC40)."""

from pathlib import Path

from eng_harness.servers import load_servers_config

COMMIT = "a" * 40
SHA = "b" * 64


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "harness.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _section(extra: str = "") -> str:
    return f"""
[servers.csi]
adapter = "sasaah-csi-mcp"
command = "/opt/x"
args = ["--disable-script"]
client_grace_s = 5
build = {{ sasaah_commit = "{COMMIT}", exe_sha256 = "{SHA}" }}
host_key = "csi"
{extra}
[servers.csi.roles.main]
classes = ["call"]
call_timeout_s = 10
"""


def test_audit_log_default_and_off(tmp_path: Path) -> None:
    """AC40: the default argv carries --audit-log; audit_log false omits the flag and its path."""
    from eng_harness.servers._launch_args import launch_argv

    run_dir = tmp_path / "run"
    audit = str(run_dir / "servers" / "csi-main-audit.jsonl")
    default = load_servers_config(_write(tmp_path, _section())).servers["csi"]
    assert launch_argv(default, "csi", "main", default.roles["main"], run_dir) == [
        "/opt/x",
        "--disable-script",
        "--call-timeout-sec",
        "10",
        "--audit-log",
        audit,
    ]
    off = load_servers_config(_write(tmp_path, _section("audit_log = false"))).servers["csi"]
    assert launch_argv(off, "csi", "main", off.roles["main"], run_dir) == [
        "/opt/x",
        "--disable-script",
        "--call-timeout-sec",
        "10",
    ]
