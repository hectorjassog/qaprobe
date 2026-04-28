"""LLM provider abstraction for agent and verifier."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import ANTHROPIC_API_KEY, OPENAI_API_KEY, PROVIDER


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None


class LLMProvider(Protocol):
    async def chat(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
        cache_system: bool = False,
        image_base64: str | None = None,
    ) -> LLMResponse: ...


class AnthropicProvider:
    def __init__(self, api_key: str = "") -> None:
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key or ANTHROPIC_API_KEY)

    async def chat(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
        cache_system: bool = False,
        image_base64: str | None = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if cache_system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            kwargs["system"] = system

        if tools:
            if cache_system:
                cached_tools = []
                for t in tools:
                    ct = dict(t)
                    ct["cache_control"] = {"type": "ephemeral"}
                    cached_tools.append(ct)
                kwargs["tools"] = cached_tools
            else:
                kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)  # type: ignore[arg-type]

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=block.input))

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            raw=response,
        )


class OpenAIProvider:
    def __init__(self, api_key: str = "") -> None:
        try:
            import openai
        except ImportError as e:
            raise ImportError("pip install openai to use the OpenAI provider") from e
        self._client = openai.AsyncOpenAI(api_key=api_key or OPENAI_API_KEY)

    def _convert_tools(self, tools: list[dict]) -> list[dict]:
        """Convert Anthropic-style tool defs to OpenAI function calling format."""
        oai_tools = []
        for t in tools:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            })
        return oai_tools

    async def chat(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
        cache_system: bool = False,
        image_base64: str | None = None,
    ) -> LLMResponse:
        oai_messages = [{"role": "system", "content": system}]

        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")

            if role == "user":
                if isinstance(content, list):
                    # Tool result
                    for item in content:
                        if item.get("type") == "tool_result":
                            oai_messages.append({
                                "role": "tool",
                                "tool_call_id": item.get("tool_use_id", ""),
                                "content": item.get("content", ""),
                            })
                else:
                    oai_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                if isinstance(content, str):
                    oai_messages.append({"role": "assistant", "content": content})
                else:
                    # Anthropic content blocks → OpenAI format
                    text_parts = []
                    tc_list = []
                    for block in content:
                        btype = getattr(block, "type", block.get("type", "")) if isinstance(block, dict) else block.type
                        if btype == "text":
                            text_parts.append(block.text if hasattr(block, "text") else block["text"])
                        elif btype == "tool_use":
                            bid = block.id if hasattr(block, "id") else block["id"]
                            bname = block.name if hasattr(block, "name") else block["name"]
                            binput = block.input if hasattr(block, "input") else block["input"]
                            tc_list.append({
                                "id": bid,
                                "type": "function",
                                "function": {"name": bname, "arguments": json.dumps(binput)},
                            })
                    oai_msg: dict[str, Any] = {"role": "assistant"}
                    if text_parts:
                        oai_msg["content"] = "\n".join(text_parts)
                    if tc_list:
                        oai_msg["tool_calls"] = tc_list
                    oai_messages.append(oai_msg)

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": oai_messages,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
        choice = response.choices[0]
        msg = choice.message

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))

        return LLMResponse(
            text=msg.content or "",
            tool_calls=tool_calls,
            raw=response,
        )


def get_provider(name: str = "") -> LLMProvider:
    """Get a provider instance by name."""
    provider_name = name or PROVIDER
    if provider_name == "anthropic":
        return AnthropicProvider()
    elif provider_name == "openai":
        return OpenAIProvider()
    else:
        raise ValueError(f"Unknown provider: {provider_name!r}. Use 'anthropic' or 'openai'.")
