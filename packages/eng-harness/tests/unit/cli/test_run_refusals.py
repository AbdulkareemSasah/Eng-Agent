"""`run` and `resume` refuse before anything is created (spec 0006 AC6, AC62 refusals, AC71)."""

from pathlib import Path
from typing import Any

from helpers.cli_deps import NEEDS_BASIS, WORKFLOW, Rig

from eng_harness.calc import CalcStatus
from eng_harness.cli import ExitCode
from eng_harness.errors import HarnessCode
from eng_harness.servers import ConfigError

NO_RUN = "run_" + "0" * 26


def _boom(_: Path) -> None:
    raise ConfigError("servers.csi", "no host program for the product")


def test_refusals_create_no_run(tmp_path: Path) -> None:
    refused = [(("harness.model_diff", CalcStatus.DRAFT, HarnessCode.CALC_NOT_APPROVED))]
    cases: list[tuple[str, Rig, list[str], int, str]] = []

    def case(name: str, argv: list[str], code: int, text: str, **rig: Any) -> None:
        cases.append((name, Rig(tmp_path / name, **rig), argv, code, text))

    case("unknown", ["run", "nosuch"], ExitCode.REFUSED, "workflow 'nosuch' is not registered")
    case("basis", ["run", NEEDS_BASIS], ExitCode.USAGE, "required basis fields is not available")
    case(
        "calcs",
        ["run", WORKFLOW],
        ExitCode.REFUSED,
        "harness.model_diff is draft (CALC_NOT_APPROVED)",
        refusals=refused,
    )
    case("builder", ["run", WORKFLOW], ExitCode.USAGE, "configuration error: servers.csi", on_build=_boom)
    case("answers", ["run", WORKFLOW, "--answers", "a.json"], ExitCode.USAGE, "--answers option is not available")
    case("option", ["run", WORKFLOW, "--bogus"], ExitCode.USAGE, "unrecognized arguments: --bogus")
    case("quantity", ["run", WORKFLOW, "--load", "2"], ExitCode.USAGE, "unrecognized arguments: --load")
    case("no_run", ["resume", NO_RUN], ExitCode.NOT_FOUND, f"no run {NO_RUN}")
    case("bad_id", ["resume", "../x"], ExitCode.NOT_FOUND, "no run ../x")
    for name, rig, argv, code, text in cases:
        assert rig.main(*argv) == code, name
        assert text in rig.err.getvalue(), (name, rig.err.getvalue())
        assert (rig.run_ids(), rig.engines, rig.out.getvalue()) == ([], [], ""), name
    # an input that cannot be read or does not fit the workflow's input model
    for name, text, where in [
        ("syntax", "{not json", "cannot read the input file"),
        ("list", "[1]", "must hold one JSON object"),
        ("model", '{"count": "many"}', "the input does not fit fake_flow: count"),
        ("extra", '{"unknown": 1}', "the input does not fit fake_flow: unknown"),
    ]:
        rig = Rig(tmp_path / name)
        assert rig.main("run", WORKFLOW, "--input", rig.input_file(text)) == ExitCode.USAGE, name
        assert where in rig.err.getvalue(), (name, rig.err.getvalue())
        assert (rig.run_ids(), rig.engines) == ([], []), name


def test_workspace_that_cannot_be_used_ends_run_and_resume(tmp_path: Path) -> None:
    for argv in (["run", WORKFLOW], ["resume", NO_RUN]):
        rig = Rig(tmp_path / argv[0])
        assert rig.main(*argv, environ={}) == ExitCode.USAGE
        assert "no workspace is configured (set ENG_WORKSPACE)" in rig.err.getvalue()
        assert not rig.workspace.exists()
        assert (rig.engines, rig.built) == ([], [])


def test_trial_run_makes_no_calc_preflight(tmp_path: Path) -> None:
    rig = Rig(tmp_path, refusals=[("harness.model_diff", CalcStatus.DRAFT, HarnessCode.CALC_NOT_APPROVED)])
    assert rig.main("run", WORKFLOW, "--run-class", "trial", "--no-report") == ExitCode.OK
    assert [(c.run_class.value, c.preflighted) for c in rig.calcs] == [("trial", False)]
    rig = Rig(tmp_path / "production")
    assert rig.main("run", WORKFLOW, "--no-report") == ExitCode.OK
    assert [(c.run_class.value, c.preflighted) for c in rig.calcs] == [("production", True)]


def test_run_is_unavailable_without_collaborators(tmp_path: Path) -> None:
    for argv in (["run", WORKFLOW], ["resume", NO_RUN]):
        rig = Rig(tmp_path / argv[0])
        for missing in ("workflow_registry", "port_builder", "calc_port_factory"):
            assert rig.main(*argv, **{missing: None}) == ExitCode.USAGE
            assert f"command {argv[0]} is not available in this build" in rig.err.getvalue()
        assert (rig.run_ids(), rig.engines, rig.built, rig.workspace.exists()) == ([], [], [], False)


def test_arguments_no_command_knows_are_usage_errors(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    for argv in (["status", "--bogus"], ["resume", NO_RUN, "--title", "T"], ["stop", NO_RUN, "extra"]):
        assert rig.main(*argv) == ExitCode.USAGE, argv
    assert "eng-harness resume: error: unrecognized arguments: --title T" in rig.err.getvalue()
