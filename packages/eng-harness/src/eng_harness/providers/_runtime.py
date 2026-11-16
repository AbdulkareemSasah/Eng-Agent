"""Phase-1 assembly of the decision runtime (spec 0009 4.1, AC49; gap PR-G1).

Until the provider factory and release verification are wired, no provider is built, no release is kept and no point
policy is read: the cascade gets rules and the engineer only. What was configured and what was dropped is reported in
the warnings and in the summary the run header records.
"""

from collections.abc import Mapping

from eng_contract.store import Workspace
from pydantic import BaseModel, ConfigDict, JsonValue

from eng_harness.decisions._policy import DecisionSettings, ShadowRelease
from eng_harness.decisions.interfaces import DecisionProvider, LLMProvider
from eng_harness.decisions.types import DecisionPolicy
from eng_harness.providers._config import ProvidersConfig

_GAP = "PR-G1"


class DecisionRuntime(BaseModel):
    """What the cascade is built with (`model=`, `llm=`), the kept releases, the warnings and the run-header summary."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    model: DecisionProvider | None = None
    llm: LLMProvider | None = None
    releases: Mapping[str, ShadowRelease] = {}
    warnings: tuple[str, ...] = ()
    summary: Mapping[str, JsonValue] = {}


def assemble_decision_runtime(
    providers_config: ProvidersConfig,
    decision_settings: DecisionSettings,
    workspace: Workspace,  # unused until PR-G1 closes
    point_policies: Mapping[str, DecisionPolicy],  # read by nothing in phase 1
) -> DecisionRuntime:
    """Assemble the phase-1 runtime: no provider, no release; each provider and each drop is reported."""
    warnings = [f"{w.code}: {w.table}" for w in providers_config.warnings]
    providers: list[JsonValue] = []
    for table, tier, config in (
        ("providers.decision", 2, providers_config.decision),
        ("providers.llm", 3, providers_config.llm),
    ):
        if config is not None:
            providers.append(
                {"name": config.name, "model": config.model, "version": config.model_version,
                 "is_local": config.local, "tier": tier, "status": "not_implemented"}
            )  # fmt: skip
            warnings.append(f"provider {config.name} ({table}) is not built: {_GAP}")
    dropped = sorted(decision_settings.shadow_released)
    warnings += [f"release of point {point} is dropped, the point stays in shadow: {_GAP}" for point in dropped]
    summary: dict[str, JsonValue] = {
        "providers": providers,
        "released": {},
        "dropped_releases": [{"point": point, "reason": _GAP} for point in dropped],
    }
    return DecisionRuntime(warnings=tuple(warnings), summary=summary)
