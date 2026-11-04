"""The page server binds the loopback interface only, on a port the operating system chooses (plan 0006 T6; AC22)."""

import io
import ipaddress
import re
import tokenize
from pathlib import Path

import pytest
from eng_contract.errors import ErrorCode
from tests.helpers.page_client import StubApp, serving

from eng_harness.pages import LOOPBACK, PageBindError, PageServer

PAGES = Path(__file__).resolve().parents[3] / "src" / "eng_harness" / "pages"
_ADDRESS_WORDS = re.compile(r"0\.0\.0\.0|localhost", re.IGNORECASE)
_ANY_V6 = re.compile(r"\[?::\]?")


def test_loopback_random_port() -> None:
    with serving(session=False) as first, serving(session=False) as second:
        assert first.server.address == "127.0.0.1" == LOOPBACK
        assert second.server.address == "127.0.0.1"
        assert first.server.port > 0
        assert second.server.port > 0
        assert first.server.port != second.server.port
        assert first.server.launch_address.startswith(f"http://127.0.0.1:{first.server.port}/launch?code=")
        assert first.client.get("/").status == 403  # reachable on that address and port (refused: no session yet)


ANY_V4 = str(ipaddress.IPv4Address(0))  # the wildcard address, spelled without the literal


@pytest.mark.parametrize("address", [ANY_V4, "::", "localhost", "192.0.2.1", "127.0.0.2", "", "example.org"])
def test_other_addresses_are_refused(address: str) -> None:
    with pytest.raises(PageBindError) as refused:
        PageServer(StubApp(), address=address)
    assert refused.value.detail.code is ErrorCode.INVALID_ARGUMENT


def test_no_source_line_names_a_wildcard_or_name_address() -> None:
    sources = sorted(PAGES.glob("*.py"))
    assert {p.name for p in sources} >= {"__init__.py", "_security.py", "_server.py", "_routes.py", "_css.py"}
    offences: list[str] = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        offences += [f"{path.name}:{n}" for n, line in enumerate(text.splitlines(), 1) if _ADDRESS_WORDS.search(line)]
        for token in tokenize.generate_tokens(io.StringIO(text).readline):  # `::` in CSS or a slice is not an address
            if token.type == tokenize.STRING and _ANY_V6.fullmatch(token.string.strip("\"'").strip()):
                offences.append(f"{path.name}:{token.start[0]}")
    assert offences == []
