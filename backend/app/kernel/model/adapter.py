"""The one adapter that reaches a provider, over Pydantic AI's direct request.

Provider-generic on purpose: the binding's `provider` string is what selects the
Pydantic AI provider (`infer_model` reads `provider:model`), so adding a provider
is a row in `core.tier_binding` and no code at all. No provider is named here.

Pydantic AI 2.36.0: `direct.model_request` is the request path without an agent,
which is what this module wants — the prompt is already assembled and the kernel
owns it.
"""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic_ai.direct import model_request
from pydantic_ai.messages import ModelRequest, ModelResponse, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition

from app.kernel.context.service import AssembledTurn, PrefixLayer
from app.kernel.ports.model_runner import Binding, Completion, ProposedCall, Usage
from app.kernel.store.models import Json

_EFFORTS = ("minimal", "low", "medium", "high", "xhigh")


class PydanticAIModelRunner:
    """`ModelRunner` against a real provider."""

    async def run(self, assembled: AssembledTurn, binding: Binding) -> Completion:
        response = await model_request(
            f"{binding.provider}:{binding.model}",
            [
                ModelRequest(
                    parts=[
                        UserPromptPart(content=part.body) for part in assembled.envelope
                    ],
                    instructions=instructions(assembled.prefix),
                )
            ],
            model_settings=_settings(binding),
            model_request_parameters=ModelRequestParameters(
                function_tools=tool_definitions(assembled.prefix)
            ),
        )
        return completion(response)


def instructions(prefix: tuple[PrefixLayer, ...]) -> str:
    """The prefix as one instruction block, in the order assembly fixed."""
    return "\n\n".join(layer.body for layer in prefix)


def tool_definitions(prefix: tuple[PrefixLayer, ...]) -> list[ToolDefinition]:
    """L5 back into Pydantic AI's shape.

    The tool block is kernel-owned and reaches the adapter as the JSON assembly
    put in the prefix (ADR-0013), so this reads that block rather than the
    registry: what the model is offered is exactly what the manifest recorded.
    """
    layer = next((one for one in prefix if one.slot == "L5"), None)
    tools = cast("list[dict[str, Any]]", json.loads(layer.body)) if layer else []
    return [
        ToolDefinition(
            name=cast("str", tool["name"]),
            parameters_json_schema=cast("dict[str, Any]", tool["parameters"]),
            description=cast("str | None", tool["description"]),
        )
        for tool in tools
    ]


def _settings(binding: Binding) -> ModelSettings | None:
    """A null effort is the provider's own default, so nothing is sent."""
    if binding.effort is None:
        return None
    if binding.effort not in _EFFORTS:
        raise ValueError(f"unknown effort {binding.effort!r} in the tier binding")
    return ModelSettings(thinking=binding.effort)


def completion(response: ModelResponse) -> Completion:
    """The provider's answer in the port's words, cache counts included."""
    usage = response.usage
    cache: Json = {
        "cache_read_tokens": usage.cache_read_tokens,
        "cache_write_tokens": usage.cache_write_tokens,
    }
    return Completion(
        text=response.text or "",
        calls=tuple(
            ProposedCall(
                name=call.tool_name,
                args=cast("Json", call.args_as_dict()),
                tool_call_id=call.tool_call_id,
            )
            for call in response.tool_calls
        ),
        usage=Usage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_tokens=usage.cache_read_tokens,
        ),
        cache=cache,
    )
