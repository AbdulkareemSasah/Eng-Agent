"""Package skeleton tests (plan task T1; spec section 4.1 table of public names)."""

from importlib import resources

import eng_contract


def test_version_constants() -> None:
    assert eng_contract.CONTRACT_VERSION == "eng-contract/1"
    assert eng_contract.UNITS_VERSION == "canonical/1"
    assert eng_contract.__version__ == "0.1.0.dev0"


def test_py_typed_marker_ships() -> None:
    assert resources.files("eng_contract").joinpath("py.typed").is_file()
