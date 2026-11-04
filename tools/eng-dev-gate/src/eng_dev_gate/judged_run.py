"""Entry point of ``coverage run`` inside the environment of the judged tree (spec 4.12, 4.16, B-059).

In pull-request context the ``tests`` step runs ``uv run --project <judged tree> ... python judged_run.py <args>``. This
file is run as a script by the interpreter of the judged environment, so it imports nothing of the gate except itself
and loads the pytest plugin of the base commit from the file next to it, under a name of its own. The judged
environment may contain another ``eng_dev_gate`` (the pull request's own copy); that copy is never used as the plugin.

Invariant: ``pytest_plugin.py`` imports nothing from ``eng_dev_gate`` (a unit test checks it), because inside this
environment such an import would resolve to the pull request's copy.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

__all__ = ["BASE_PLUGIN", "NO_COV_MARKER", "load_base_plugin", "main", "resolve_arguments"]

BASE_PLUGIN = "eng_gate_base_pytest_plugin"  # module name of the base plugin; pytest finds it in ``sys.modules``
NO_COV_MARKER = "--eng-gate-no-cov-if-installed"  # replaced by ``--no-cov`` when pytest-cov exists in this environment
MISSING_TOOL_EXIT = 2  # the tests step maps every exit code outside pytest's own to an environment fault


def _pytest_cov_installed() -> bool:
    """True when pytest-cov, a development dependency only, can be imported; ``--no-cov`` is unknown without it."""
    return importlib.util.find_spec("pytest_cov") is not None


def resolve_arguments(argv: Sequence[str]) -> list[str]:
    """Return ``argv`` with ``NO_COV_MARKER`` replaced by ``--no-cov`` or dropped, by what this environment has."""
    no_cov = ["--no-cov"] if _pytest_cov_installed() else []
    return [part for arg in argv for part in (no_cov if arg == NO_COV_MARKER else [arg])]


def load_base_plugin() -> ModuleType:
    """Load ``pytest_plugin.py`` that sits next to this file as ``BASE_PLUGIN`` and register it in ``sys.modules``.

    Raises:
        ImportError: pytest is not installed in this environment.
    """
    path = Path(__file__).resolve().with_name("pytest_plugin.py")
    spec = importlib.util.spec_from_file_location(BASE_PLUGIN, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the base plugin {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[BASE_PLUGIN] = module
    spec.loader.exec_module(module)
    return module


def _working_directory_first() -> None:
    """Put the working directory first on ``sys.path`` in place of this script's folder, as ``python -m`` does."""
    script_dir = Path(__file__).resolve().parent
    sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != script_dir]
    sys.path.insert(0, os.getcwd())


def main(argv: Sequence[str]) -> int:
    """Run ``coverage`` with ``argv`` after pinning the base plugin; return coverage's exit status.

    A missing ``pytest`` or ``coverage`` returns ``MISSING_TOOL_EXIT`` with a message on stderr.
    """
    _working_directory_first()
    try:
        load_base_plugin()
        from coverage.cmdline import main as coverage_main
    except ImportError as error:
        sys.stderr.write(f"the judged environment lacks {error.name or 'a required tool'}: {error}\n")
        return MISSING_TOOL_EXIT
    return coverage_main(resolve_arguments(argv)) or 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
