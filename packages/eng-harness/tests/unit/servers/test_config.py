"""`harness.toml` server and tool sections (plan 0002 T1, T20; spec 0002 AC1 to AC3, AC40, section 4.2)."""

import tomllib
from pathlib import Path

import pytest

from eng_harness.servers import ConfigError, ServersConfig, load_servers_config, servers_config

COMMIT = "a" * 40
SHA = "b" * 64

FULL = f"""
[engine]
anything = "owned by spec 0006, ignored here"

[servers.csi]
adapter = "sasaah-csi-mcp"
command = "/opt/sasaah/sasaah-csi-mcp"
args = ["--disable-script"]
env = {{ EXTRA = "1" }}
toolsets = []
client_grace_s = 15
max_restarts_per_run = 2
shutdown_grace_s = 7
build = {{ sasaah_commit = "{COMMIT}", exe_sha256 = "{SHA}", server_info_version = "1.2" }}
host_key = "csi"
product = "ETABS"
mcp_mode = "legacy"
audit_log = false

[servers.csi.roles.main]
classes = ["session", "call"]
call_timeout_s = 30

[servers.csi.roles.long]
classes = ["long"]
call_timeout_s = 900

[host_programs.etabs]
executables = ["ETABS.exe"]
install_dirs = ["/opt/etabs"]

[cli_tools."dxf-prep/prepare"]
shell = "/usr/bin/pwsh"
script = "/opt/tools/dxf-prep/prepare.ps1"
inputs = ["dxf"]
outputs = ["out.json"]
timeout_s = 60
build_artifacts = [{{ path = "/opt/tools/prep", sha256 = "{SHA}" }}]
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "harness.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _minimal(extra_args: str = '"--disable-script"', extra: str = "") -> str:
    return f"""
[servers.csi]
adapter = "sasaah-csi-mcp"
command = "/opt/x"
args = [{extra_args}]
client_grace_s = 5
build = {{ sasaah_commit = "{COMMIT}", exe_sha256 = "{SHA}" }}
host_key = "csi"
product = "ETABS"
{extra}
[servers.csi.roles.main]
classes = ["call"]
call_timeout_s = 10
"""


def _without(text: str, line_start: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith(line_start))


def test_load_full(tmp_path: Path) -> None:
    config = load_servers_config(_write(tmp_path, FULL))
    assert isinstance(config, ServersConfig)
    server = config.servers["csi"]
    assert server.command == "/opt/sasaah/sasaah-csi-mcp"
    assert server.args == ("--disable-script",)
    assert dict(server.env) == {"EXTRA": "1"}
    assert server.toolsets == ()
    assert server.client_grace_s == 15
    assert (server.max_restarts_per_run, server.shutdown_grace_s) == (2, 7)
    assert server.build.sasaah_commit == COMMIT
    assert server.build.exe_sha256 == SHA
    assert server.build.server_info_version == "1.2"
    assert (server.host_key, server.mcp_mode, server.audit_log) == ("csi", "legacy", False)
    assert server.roles["main"].classes == ("session", "call")
    assert server.roles["main"].call_timeout_s == 30
    assert server.roles["long"].call_timeout_s == 900
    assert config.host_programs["etabs"].executables == ("ETABS.exe",)
    tool = config.cli_tools["dxf-prep/prepare"]
    assert (tool.shell, tool.script, tool.timeout_s) == ("/usr/bin/pwsh", "/opt/tools/dxf-prep/prepare.ps1", 60)
    assert (tool.inputs, tool.outputs) == (("dxf",), ("out.json",))
    assert tool.build_artifacts[0].path == "/opt/tools/prep"
    assert tool.build_artifacts[0].sha256 == SHA


def test_defaults_for_software_settings(tmp_path: Path) -> None:
    server = load_servers_config(_write(tmp_path, _minimal())).servers["csi"]
    assert (server.max_restarts_per_run, server.shutdown_grace_s) == (1, 10)
    assert (server.audit_log, server.mcp_mode, server.route) == (True, "legacy", None)


@pytest.mark.parametrize(
    ("text", "key"),
    [
        (_without(_minimal(), "client_grace_s"), "client_grace_s"),
        (_without(_minimal(), "call_timeout_s"), "call_timeout_s"),
        (_minimal().replace("client_grace_s = 5", "client_grace_s = 0"), "client_grace_s"),
        (_minimal().replace("call_timeout_s = 10", 'call_timeout_s = "10"'), "call_timeout_s"),
        (_minimal().replace("call_timeout_s = 10", "call_timeout_s = 1.5"), "call_timeout_s"),
        (_without(FULL, "timeout_s"), "timeout_s"),
    ],
)
def test_timeouts_required(tmp_path: Path, text: str, key: str) -> None:
    with pytest.raises(ConfigError, match=key):
        load_servers_config(_write(tmp_path, text))


@pytest.mark.parametrize(
    ("text", "key"),
    [
        (_minimal('"--disable-script", "--enable-script"'), "args"),
        (_minimal('"--disable-script", "--enable-generic-invoke"'), "args"),
        (_minimal('"--disable-script", "--allow-attached-writes"'), "args"),
        (_minimal('"--disable-script", "--read-only"'), "args"),
        (_minimal('"--disable-script", "--read-only=true"'), "args"),
        (_minimal('"--disable-script", "--call-timeout-sec", "5"'), "args"),
        (_minimal('"--disable-script", "--audit-log"'), "args"),
        (_minimal('"--other"'), "--disable-script"),
        (_minimal(extra='env = { SASAAH_CSI_ENABLE_SCRIPT = "0" }'), "SASAAH_CSI_ENABLE_SCRIPT"),
        (_minimal(extra='env = { SASAAH_CSI_DISABLE_SCRIPT = "false" }'), "SASAAH_CSI_DISABLE_SCRIPT"),
        (_minimal(extra='env = { SASAAH_CSI_CALL_TIMEOUT_SEC = "5" }'), "SASAAH_CSI_CALL_TIMEOUT_SEC"),
        (_minimal(extra='env = { sasaah_csi_enable_script = "1" }'), "SASAAH_CSI_ENABLE_SCRIPT"),
        (_minimal(extra='env = { Sasaah_Csi_Disable_Script = "false" }'), "SASAAH_CSI_DISABLE_SCRIPT"),
        (_minimal(extra='env = { sasaah_csi_call_timeout_sec = "5" }'), "SASAAH_CSI_CALL_TIMEOUT_SEC"),
        (
            _minimal(extra='env = { sasaah_csi_disable_script = "false", SASAAH_CSI_DISABLE_SCRIPT = "true" }'),
            "SASAAH_CSI_DISABLE_SCRIPT",
        ),
        (_minimal(extra='toolsets = ["csi_run_script"]'), "toolsets"),
        (_minimal(extra='toolsets = ["csi_db_tables_apply"]'), "toolsets"),
    ],
)
def test_forbidden_options(tmp_path: Path, text: str, key: str) -> None:
    with pytest.raises(ConfigError, match=key):
        load_servers_config(_write(tmp_path, text))


def test_disable_script_env_true_allowed(tmp_path: Path) -> None:
    text = _minimal(extra='env = { SASAAH_CSI_DISABLE_SCRIPT = "True" }')
    assert load_servers_config(_write(tmp_path, text)).servers["csi"].env["SASAAH_CSI_DISABLE_SCRIPT"] == "True"


@pytest.mark.parametrize(
    ("old", "new", "key"),
    [
        ('command = "/opt/x"', 'command = "relative/x"', "command"),
        (f'exe_sha256 = "{SHA}"', 'exe_sha256 = "zz"', "exe_sha256"),
        (f'sasaah_commit = "{COMMIT}"', 'sasaah_commit = "abc"', "sasaah_commit"),
        ('host_key = "csi"', 'host_key = "csi"\nunknown_key = 1', "unknown_key"),
        ('classes = ["call"]', "classes = []", "classes"),
    ],
)
def test_invalid_values_name_the_key(tmp_path: Path, old: str, new: str, key: str) -> None:
    with pytest.raises(ConfigError, match=key):
        load_servers_config(_write(tmp_path, _minimal().replace(old, new)))


def test_unreadable_and_malformed_files(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"harness\.toml"):
        load_servers_config(tmp_path / "harness.toml")
    with pytest.raises(ConfigError, match=r"harness\.toml"):
        load_servers_config(_write(tmp_path, "[servers\n"))


def test_empty_file_has_no_servers(tmp_path: Path) -> None:
    config = load_servers_config(_write(tmp_path, ""))
    assert (config.servers, config.cli_tools, config.host_programs) == ({}, {}, {})


def _cli(extra: str = "") -> str:
    return f"""
[cli_tools."dxf-prep/prepare"]
shell = "/usr/bin/pwsh"
script = "/opt/tools/prepare.ps1"
timeout_s = 60
{extra}
"""


RECORD = 'release_record = "docs/gaps/dxf-prep.md"'


def test_cli_tools_release_marks(tmp_path: Path) -> None:
    """AC38: unreleased [cli_tools.*] entries are exposed with their records; inconsistent marks are refused."""
    plain = load_servers_config(_write(tmp_path, _cli()))
    assert plain.cli_tools["dxf-prep/prepare"].release == "released"
    assert plain.unreleased_tools() == {}
    marked = load_servers_config(_write(tmp_path, _cli(f'release = "unreleased"\n{RECORD}')))
    assert marked.unreleased_tools() == {"dxf-prep/prepare": "docs/gaps/dxf-prep.md"}
    for extra in (
        'release = "unreleased"',
        f'release = "released"\n{RECORD}',
        RECORD,
        f'release = "draft"\n{RECORD}',
        'release = "unreleased"\nrelease_record = "/records/y.md"',
        'release = "unreleased"\nrelease_record = "../y.md"',
    ):
        with pytest.raises(ConfigError, match="release"):
            load_servers_config(_write(tmp_path, _cli(extra)))


def test_audit_log_flag(tmp_path: Path) -> None:
    """AC40: absent `audit_log` is true; a value that is not a boolean is a ConfigError (section 4.2 rule 5)."""
    assert load_servers_config(_write(tmp_path, _minimal())).servers["csi"].audit_log is True
    off = _minimal(extra="audit_log = false")
    assert load_servers_config(_write(tmp_path, off)).servers["csi"].audit_log is False
    on = _minimal(extra="audit_log = true")
    assert load_servers_config(_write(tmp_path, on)).servers["csi"].audit_log is True
    # Strings and numbers are not booleans, including the ones a lax parser would coerce.
    for value in ('"false"', '"true"', '"yes"', "0", "1", "1.0"):
        with pytest.raises(ConfigError, match="audit_log"):
            load_servers_config(_write(tmp_path, _minimal(extra=f"audit_log = {value}")))


def test_servers_config_from_tables(tmp_path: Path) -> None:
    """AC50: the validation of `load_servers_config` over tables already parsed, with the dotted key of a fault."""
    data = tomllib.loads(FULL)
    assert servers_config(data) == load_servers_config(_write(tmp_path, FULL))
    assert servers_config({"engine": {}}) == ServersConfig()
    broken = tomllib.loads(_minimal(extra="audit_log = 1"))
    with pytest.raises(ConfigError) as caught:
        servers_config(broken)
    assert caught.value.key == "servers.csi.audit_log"


def test_byte_order_mark_accepted(tmp_path: Path) -> None:
    """AC50: a file saved with a UTF-8 byte-order mark reads as the same file without it."""
    path = tmp_path / "harness.toml"
    path.write_bytes(b"\xef\xbb\xbf" + FULL.encode("utf-8"))
    assert load_servers_config(path) == servers_config(tomllib.loads(FULL))


def test_host_program_of_product(tmp_path: Path) -> None:
    """AC50: the entry named by the product in lower case, else a `ConfigError` naming `host_programs.<name>`."""
    config = servers_config(tomllib.loads(FULL))
    assert config.host_program("ETABS") is config.host_programs["etabs"]
    assert config.host_program("etabs").executables == ("ETABS.exe",)
    with pytest.raises(ConfigError) as caught:
        config.host_program("SAP2000")
    assert caught.value.key == "host_programs.sap2000"
    with pytest.raises(ConfigError, match=r"^host_programs\.etabs: "):
        ServersConfig().host_program("Etabs")


def _server(
    name: str, *, product: str | None, host_key: str, command: str = "/opt/sasaah/sasaah-csi-mcp", sha: str = SHA
) -> str:
    """One `[servers.<name>]` section of the CSI adapter with a main role, as the spec 0008 AC1 example."""
    product_line = f'product = "{product}"' if product is not None else ""
    return f"""
[servers.{name}]
adapter = "sasaah-csi-mcp"
command = "{command}"
args = ["--disable-script"]
client_grace_s = 5
build = {{ sasaah_commit = "{COMMIT}", exe_sha256 = "{sha}" }}
host_key = "{host_key}"
{product_line}

[servers.{name}.roles.main]
classes = ["session", "call"]
call_timeout_s = 10
"""


SAFE_PROGRAM = '\n[host_programs.safe]\nexecutables = ["SAFE.exe"]\n'


def test_safe_server_section(tmp_path: Path) -> None:
    """AC1: `[servers.csi_safe]` runs the same executable with its own product, host key, roles and timeouts."""
    safe = _server("csi_safe", product="SAFE", host_key="csi_safe").replace(
        "call_timeout_s = 10", "call_timeout_s = 77"
    )
    text = _server("csi", product="ETABS", host_key="csi") + safe + SAFE_PROGRAM
    config = load_servers_config(_write(tmp_path, text))
    assert set(config.servers) == {"csi", "csi_safe"}
    etabs, safe_server = config.servers["csi"], config.servers["csi_safe"]
    assert (etabs.product, safe_server.product) == ("ETABS", "SAFE")
    assert (etabs.host_key, safe_server.host_key) == ("csi", "csi_safe")
    assert etabs.command == safe_server.command
    assert (etabs.roles["main"].call_timeout_s, safe_server.roles["main"].call_timeout_s) == (10, 77)
    assert config.host_program("SAFE").executables == ("SAFE.exe",)


@pytest.mark.parametrize(
    ("text", "key"),
    [
        (_server("csi", product=None, host_key="csi"), "servers.csi.product"),
        (_server("csi", product="STAAD", host_key="csi"), "servers.csi.product"),
        (_server("csi", product="safe", host_key="csi"), "servers.csi.product"),
        (
            _server("csi", product="ETABS", host_key="shared") + _server("csi_safe", product="SAFE", host_key="shared"),
            "servers.csi_safe.host_key",
        ),
        (
            _server("csi", product="ETABS", host_key="csi")
            + _server("csi_safe", product="SAFE", host_key="csi_safe", sha="c" * 64),
            "servers.csi_safe.build",
        ),
    ],
)
def test_product_and_host_key_rules(tmp_path: Path, text: str, key: str) -> None:
    """AC1: no product, an unknown product, one host key twice, or two pins for one executable name the key."""
    with pytest.raises(ConfigError) as error:
        load_servers_config(_write(tmp_path, text))
    assert error.value.key == key


def _revit() -> str:
    return f"""
[servers.revit]
adapter = "sasaah-revit-mcp"
command = "/opt/revit/server"
pipe_name = "bridge"
client_grace_s = 5
host_key = "revit"
build = {{ sasaah_commit = "{COMMIT}", exe_sha256 = "{SHA}", addin_sha256 = ["{SHA}"], addin_paths = ["/a.dll"] }}
[servers.revit.roles.read]
classes = ["session", "call"]
call_timeout_s = 10
[servers.revit.roles.write]
classes = ["attended"]
call_timeout_s = 90
"""


def test_revit_server_section(tmp_path: Path) -> None:
    server = load_servers_config(_write(tmp_path, _revit())).servers["revit"]
    assert server.product == "Revit"
    assert server.pipe_name == "bridge"
    assert server.build.addin_paths == ("/a.dll",)
    assert server.build.addin_sha256 == (SHA,)
    assert server.roles["read"].classes == ("session", "call")
    assert server.roles["write"].classes == ("attended",)
    for before, after, key, match in (
        ('pipe_name = "bridge"', "", "servers.revit.pipe_name", "pipe_name"),
        ('pipe_name = "bridge"', 'pipe_name = "  "', "servers.revit.pipe_name", "pipe_name"),
        ('addin_paths = ["/a.dll"]', 'addin_paths = ["relative"]', "servers.revit.build.addin_paths", "addin_paths"),
        ('addin_sha256 = ["' + SHA + '"]', "addin_sha256 = []", "servers.revit.build.addin_paths", "addin_paths"),
        (
            f'addin_sha256 = ["{SHA}"], addin_paths = ["/a.dll"]',
            "addin_sha256 = [], addin_paths = []",
            "servers.revit.build",
            "addin_paths",
        ),
        ('classes = ["attended"]', 'classes = ["call"]', "servers.revit.roles", "roles"),
        ('classes = ["session", "call"]', 'classes = ["session", "call", "call"]', "servers.revit.roles", "roles"),
        ("call_timeout_s = 90", "", "servers.revit.roles.write.call_timeout_s", "call_timeout_s"),
        ("call_timeout_s = 10", "", "servers.revit.roles.read.call_timeout_s", "call_timeout_s"),
        ("client_grace_s = 5", "", "servers.revit.client_grace_s", "client_grace_s"),
        ('host_key = "revit"', 'host_key = "revit"\nproduct = "ETABS"', "servers.revit.product", "product"),
        ('[servers.revit.roles.write]\nclasses = ["attended"]\ncall_timeout_s = 90', "", "servers.revit.roles", "roles"),
    ):
        with pytest.raises(ConfigError, match=match) as caught:
            load_servers_config(_write(tmp_path, _revit().replace(before, after)))
        assert caught.value.key == key
    with pytest.raises(ConfigError, match="product") as caught:
        load_servers_config(_write(tmp_path, _minimal(extra='product = "Revit"').replace('product = "ETABS"\n', "")))
    assert caught.value.key == "servers.csi.product"


def test_revit_forbidden_options(tmp_path: Path) -> None:
    load_servers_config(_write(tmp_path, _revit()))
    for extra, key, match in (
        ('args = ["--enable-send-code"]', "servers.revit.args", "args"),
        ('args = ["--enable-adaptive-bake"]', "servers.revit.args", "args"),
        ('args = ["--cache-send-code-bodies"]', "servers.revit.args", "args"),
        ('args = ["--toolsets=all"]', "servers.revit.args", "args"),
        ('args = ["--toolsets", "all"]', "servers.revit.args", "args"),
        ('args = ["--pipe-name", "p"]', "servers.revit.args", "args"),
        ('args = ["--bridge-timeout-ms", "1000"]', "servers.revit.args", "args"),
        ('args = ["--disable-send-code"]', "servers.revit.args", "args"),
        ('args = ["--disable-adaptive-bake"]', "servers.revit.args", "args"),
        ('args = ["--no-cache-send-code-bodies"]', "servers.revit.args", "args"),
        ('args = ["--read-only"]', "servers.revit.args", "args"),
        ('toolsets = ["destructive"]', "servers.revit.toolsets", "toolsets"),
        ('env = { SASAAH_MCP_TEST = "1" }', "servers.revit.env", "SASAAH_MCP_"),
        ('env = { sasaah_mcp_test = "1" }', "servers.revit.env", "SASAAH_MCP_"),
    ):
        text = _revit().replace('host_key = "revit"', 'host_key = "revit"\n' + extra)
        with pytest.raises(ConfigError, match=match) as caught:
            load_servers_config(_write(tmp_path, text))
        assert caught.value.key == key


IDEA_URL = "http://127.0.0.1:5000"
IDEA_NATIVE = 'route = "native"\naudit_log = false'
IDEA_REST = f'route = "rest"\nservice_url = "{IDEA_URL}"\naudit_log = false'
IDEA_SECOND_ROLE = '[servers.idea.roles.long]\nclasses = ["long"]\ncall_timeout_s = 20'


def _idea(*, args: str = '"--disable-script"', extra: str = IDEA_NATIVE, roles: str = "") -> str:
    """A `[servers.idea]` section of spec 0014 section 4.2; `extra` holds the section's own keys."""
    return f"""
[servers.idea]
adapter = "sasaah-idea-mcp"
command = "/opt/x"
args = [{args}]
client_grace_s = 5
build = {{ sasaah_commit = "{COMMIT}", exe_sha256 = "{SHA}" }}
host_key = "idea"
{extra}
[servers.idea.roles.main]
classes = ["session", "call", "long"]
call_timeout_s = 10
{roles}
"""


def test_idea_server_section(tmp_path: Path) -> None:
    """Spec 0014 AC1: the IDEA section with one role `main`, a route, a loopback service URL and the timeouts loads."""
    rest_extra = f'{IDEA_REST}\nidea_dir = "/opt/idea"\nenv = {{ EXTRA = "1" }}'
    rest = load_servers_config(_write(tmp_path, _idea(extra=rest_extra))).servers["idea"]
    assert (rest.adapter, rest.product, rest.route, rest.service_url, rest.idea_dir) == (
        "sasaah-idea-mcp",
        "IDEA",
        "rest",
        IDEA_URL,
        "/opt/idea",
    )
    assert (rest.args, rest.audit_log, rest.host_key, dict(rest.env)) == (
        ("--disable-script",),
        False,
        "idea",
        {"EXTRA": "1"},
    )
    assert tuple(rest.roles) == ("main",)
    assert rest.roles["main"].classes == ("session", "call", "long")
    assert rest.roles["main"].call_timeout_s == 10
    native = load_servers_config(_write(tmp_path, _idea())).servers["idea"]
    assert (native.route, native.service_url, native.idea_dir) == ("native", None, None)
    local = _idea(extra=f'{IDEA_NATIVE}\nservice_url = "http://localhost:5000"')
    assert load_servers_config(_write(tmp_path, local)).servers["idea"].service_url == "http://localhost:5000"
    windows = _idea(extra=f'{IDEA_NATIVE}\nidea_dir = "C:\\\\Program Files\\\\IDEA"')
    assert load_servers_config(_write(tmp_path, windows)).servers["idea"].idea_dir == "C:\\Program Files\\IDEA"


@pytest.mark.parametrize(
    ("text", "key"),
    [
        (_idea(roles=IDEA_SECOND_ROLE), r"servers\.idea\.roles"),
        (_idea().replace("roles.main", "roles.other"), r"servers\.idea\.roles"),
        (_idea(args='"--disable-script", "--read-only"'), r"servers\.idea\.args: .*--read-only"),
        (_idea(args='"--disable-script", "--read-only=true"'), r"servers\.idea\.args: .*--read-only"),
        (_idea(args='"--disable-script", "--default-project"'), r"servers\.idea\.args: .*--default-project"),
        (_idea(args='"--disable-script", "--default-project", "p"'), r"servers\.idea\.args: .*--default-project"),
        (_idea(args='"--disable-script", "--other"'), r"servers\.idea\.args: .*--other"),
        (_idea(args='"--disable-script", "--idea-dir"'), r"servers\.idea\.args: .*--idea-dir"),
        (_idea(args='"--disable-script", "--service-url"'), r"servers\.idea\.args: .*--service-url"),
        (_idea(args='"--disable-script", "--call-timeout-sec", "5"'), r"servers\.idea\.args: .*--call-timeout-sec"),
        (_idea(args='"--disable-script", "--audit-log"'), r"servers\.idea\.args: .*--audit-log"),
        (_idea(args='"--disable-script=false"'), r"servers\.idea\.args: .*--disable-script=false"),
        (_idea(args=""), "--disable-script"),
        (_idea(args='"--other"'), "--other"),
        (_idea(extra="audit_log = false"), r"servers\.idea: route"),
        (_idea(extra='route = "both"\naudit_log = false'), r"servers\.idea\.route"),
        (_idea(extra='route = "REST"\naudit_log = false'), r"servers\.idea\.route"),
        (_idea(extra='route = ""\naudit_log = false'), r"servers\.idea\.route"),
        (_idea(extra='route = "native"'), r"servers\.idea\.audit_log"),
        (_idea(extra='route = "native"\naudit_log = true'), r"servers\.idea\.audit_log"),
        (_idea(extra='route = "rest"\naudit_log = false'), r"servers\.idea: service_url"),
        (_idea(extra=f'{IDEA_NATIVE}\nidea_dir = "relative/idea"'), r"servers\.idea\.idea_dir"),
        (_idea(extra=f'{IDEA_NATIVE}\nproduct = "ETABS"'), r"servers\.idea\.product"),
        (_minimal(extra=f'service_url = "{IDEA_URL}"'), r"servers\.csi\.service_url"),
        (_minimal(extra='idea_dir = "/opt/idea"'), r"servers\.csi\.idea_dir"),
    ],
)
def test_idea_forbidden_options(tmp_path: Path, text: str, key: str) -> None:
    """Spec 0014 AC1: a second role, a forbidden or unknown argument, a missing requirement or route is refused."""
    with pytest.raises(ConfigError, match=key):
        load_servers_config(_write(tmp_path, text))


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:5000",
        "http://127.0.0.1",
        "http://127.0.0.2:8080",
        "http://localhost:5000",
        "HTTP://LOCALHOST:5000",
        "http://[::1]:5000",
        "https://127.0.0.1:5001",
    ],
)
def test_idea_service_url_loopback_accepted(tmp_path: Path, url: str) -> None:
    """Spec 0014 AC1: loopback hosts (IPv4, IPv6, `localhost`) are accepted for the REST service URL."""
    text = _idea(extra=f'route = "rest"\nservice_url = "{url}"\naudit_log = false')
    assert load_servers_config(_write(tmp_path, text)).servers["idea"].service_url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:5000",
        "http://10.0.0.5:5000",
        "http://192.168.1.10:5000",
        "http://0.0.0.0:5000",
        "http://127.0.0.1.example.com:5000",
        "http://localhost.example.com:5000",
        "http://[::2]:5000",
        "http://user@127.0.0.1:5000",
        "http://127.0.0.1@example.com:5000",
        "ftp://127.0.0.1:5000",
        "127.0.0.1:5000",
        "http://",
        "http://127.0.0.1:99999",
        "http://[::1",
        "",
    ],
)
def test_idea_service_url_loopback_only(tmp_path: Path, url: str) -> None:
    """Spec 0014 AC1: a `service_url` whose host is not loopback (or that is not a plain http(s) URL) is refused."""
    good = _idea(extra=IDEA_REST)  # the section itself is valid: only the URL under test differs
    assert load_servers_config(_write(tmp_path, good)).servers["idea"].service_url == IDEA_URL
    for extra in (f'route = "rest"\nservice_url = "{url}"\naudit_log = false', f'{IDEA_NATIVE}\nservice_url = "{url}"'):
        with pytest.raises(ConfigError) as caught:
            load_servers_config(_write(tmp_path, _idea(extra=extra)))
        assert caught.value.key == "servers.idea.service_url"
    with pytest.raises(ConfigError, match=r"servers\.idea\.service_url"):
        load_servers_config(_write(tmp_path, _idea(extra=f"{IDEA_NATIVE}\nservice_url = 5000")))


@pytest.mark.parametrize(
    "name",
    [
        "SASAAH_IDEA_CALL_TIMEOUT_SEC",
        "SASAH_IDEA_READ_ONLY",
        "IDEA_DIR",
        "SASAAH_IDEA_SERVICE_URL",
        "sasaah_idea_default_project",
        "Sasah_Idea_X",
        "idea_dir",
    ],
)
def test_idea_env_keys_refused(tmp_path: Path, name: str) -> None:
    """Spec 0014 AC1: the three aliases of each server option are refused in `env`, in any letter case."""
    with pytest.raises(ConfigError, match=rf"servers\.idea\.env: .*{name.upper()}") as caught:
        load_servers_config(_write(tmp_path, _idea(extra=f'{IDEA_NATIVE}\nenv = {{ {name} = "1" }}')))
    assert caught.value.key == "servers.idea.env"
    # Other variables stay allowed, and the prefixes are the IDEA section's rule only.
    other = _idea(extra=f'{IDEA_NATIVE}\nenv = {{ IDEAL_X = "1", MY_IDEA_X = "2", IDEAS = "3" }}')
    assert set(load_servers_config(_write(tmp_path, other)).servers["idea"].env) == {"IDEAL_X", "MY_IDEA_X", "IDEAS"}
    csi = _minimal(extra=f'env = {{ {name} = "1" }}')
    assert name in load_servers_config(_write(tmp_path, csi)).servers["csi"].env
