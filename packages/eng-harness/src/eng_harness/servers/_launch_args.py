"""Argv of one server role (spec 0002 section 4.3.2).

Purpose: build `[command, *args, "--call-timeout-sec", <call_timeout_s>]` and, when the section's `audit_log` is
true, `"--audit-log"` plus `run_dir/servers/<server>-<role>-audit.jsonl` (section 4.2 rule 5). The CSI argv is that
list; a server without the option (`audit_log` false) gets neither audit item. The IDEA section (spec 0014 section 4.2
rule 3) adds `"--idea-dir", <idea_dir>` and `"--service-url", <service_url>` after the timeout, each when its key is
set; the configuration refuses both keys for any other adapter. Units: `call_timeout_s` is seconds.
Errors: none; a section that is not valid is refused when the configuration is loaded.
"""

from pathlib import Path

from eng_harness.servers._config import RoleConfig, ServerConfig


def launch_argv(config: ServerConfig, server: str, role_name: str, role: RoleConfig, run_dir: Path) -> list[str]:
    """Return one role's argv. The audit path is omitted, with its flag, when `config.audit_log` is false."""
    argv = [config.command, *config.args, "--call-timeout-sec", str(role.call_timeout_s)]
    if config.audit_log:
        audit = run_dir / "servers" / f"{server}-{role_name}-audit.jsonl"
        argv += ["--audit-log", str(audit)]
    if config.idea_dir is not None:
        argv += ["--idea-dir", config.idea_dir]
    if config.service_url is not None:
        argv += ["--service-url", config.service_url]
    return argv
