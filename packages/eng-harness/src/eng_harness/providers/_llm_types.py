"""Per-request structured output for the language-model tier (spec 0009 section 4.7, AC21)."""

from hashlib import sha256
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, create_model
from pydantic_ai.output import ToolOutput

from eng_harness.decisions._rules import Rationale
from eng_harness.decisions.interfaces import ProviderRequest

__all__ = ["build_output_type", "build_tool_output"]


def build_output_type(request: ProviderRequest) -> type[BaseModel]:
    """A frozen model with a literal ``choice`` and a digit-free ``Rationale``."""

    values = tuple(option.value for option in request.options)
    tag = sha256(repr(values).encode()).hexdigest()[:10]
    return create_model(
        f"LlmStructuredOutput_{tag}",
        __config__=ConfigDict(frozen=True, extra="forbid"),
        choice=(Literal[*values], ...),  # type: ignore[arg-type]  # B-224: dynamic option literals
        rationale=(Rationale, ...),
    )


def build_tool_output(request: ProviderRequest) -> ToolOutput:
    """The strict tool output PydanticAI uses for this request (spec section 4.7; AC23)."""

    output_type = cast(Any, build_output_type(request))
    return ToolOutput(output_type, max_retries=0, strict=True)
