"""Unit tests for provider abstraction."""

import pytest

from qaprobe.provider import AnthropicProvider, LLMResponse, ToolCall, get_provider


def test_get_provider_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = get_provider("anthropic")
    assert isinstance(provider, AnthropicProvider)


def test_get_provider_unknown():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_provider("unknown_provider")


def test_llm_response_dataclass():
    resp = LLMResponse(
        text="hello",
        tool_calls=[ToolCall(id="1", name="click", input={"ref": "btn:0"})],
    )
    assert resp.text == "hello"
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "click"


def test_tool_call_dataclass():
    tc = ToolCall(id="abc", name="fill", input={"ref": "inp:0", "text": "hello"})
    assert tc.id == "abc"
    assert tc.name == "fill"
    assert tc.input["text"] == "hello"
