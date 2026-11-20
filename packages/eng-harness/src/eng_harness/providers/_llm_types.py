"""Per-request structured output for the language-model tier (spec 0009 section 4.7, AC21)."""

from hashlib import sha256
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, create_model
from pydantic_ai.output import ToolOutput

from eng_harness.decisions._rules import Rationale
from eng_harness.decisions.interfaces import ProviderRequest

__all__ = ["build_output_type", "build_tool_output"]


def _choice_type(values: tuple[str, ...]) -> Any:
    allowed = frozenset(values)

    def check(value: object) -> str:
        if not isinstance(value, str) or value not in allowed:
            msg = "choice is not one of the request options"
            raise ValueError(msg)
        return value

    return Annotated[str, BeforeValidator(check), Field(json_schema_extra={"enum": list(values)})]


def build_output_type(request: ProviderRequest) -> type[BaseModel]:
    """A frozen model with a literal ``choice`` and a digit-free ``Rationale``."""

    values = tuple(option.value for option in request.options)
    tag = sha256(repr(values).encode()).hexdigest()[:10]
    return create_model(
        f"LlmStructuredOutput_{tag}",
        __config__=ConfigDict(frozen=True, extra="forbid"),
        choice=(_choice_type(values), ...),
        rationale=(Rationale, ...),
    )


def build_tool_output(request: ProviderRequest) -> ToolOutput[BaseModel]:
    """The strict tool output PydanticAI uses for this request (spec section 4.7; AC23)."""

    return ToolOutput(build_output_type(request), max_retries=0, strict=True)
