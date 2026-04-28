from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Page

from .browser import BrowserSession
from .config import AGENT_MODEL, FAST_MODEL, MAX_STEPS, ROUTING_THRESHOLD
from .provider import LLMProvider, get_provider

AGENT_SYSTEM = """You are QAProbe, an expert QA engineer driving a browser to test a web application.

You will be given a user story describing what a user should be able to do.
Your job is to drive the browser to verify this story is working correctly.

At each step you receive the current accessibility tree of the page and choose ONE tool to execute.
Continue until you have enough information to determine if the story passes or fails.

Rules:
- Only interact with elements that exist in the accessibility tree
- Use refs (like btn:submit@form, inp:email@form) to identify elements
- Be methodical: observe, plan, act
- When done, call `done` with your verdict (pass/fail) and clear reasoning
- If the page doesn't load or you can't complete the story, call done with fail
"""

TOOLS = [
    {
        "name": "click",
        "description": "Click on an element identified by its ref",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Element ref from the accessibility tree (e.g. btn:submit@form)",
                },
            },
            "required": ["ref"],
        },
    },
    {
        "name": "fill",
        "description": "Type text into an input field",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Element ref for the input field"},
                "text": {"type": "string", "description": "Text to type"},
            },
            "required": ["ref", "text"],
        },
    },
    {
        "name": "select",
        "description": "Select an option from a dropdown/combobox",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Element ref for the select element"},
                "value": {"type": "string", "description": "Option value or label to select"},
            },
            "required": ["ref", "value"],
        },
    },
    {
        "name": "press_key",
        "description": "Press a keyboard key (e.g. Enter, Tab, Escape, ArrowDown)",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name (Playwright key format)"},
            },
            "required": ["key"],
        },
    },
    {
        "name": "navigate",
        "description": "Navigate the browser to a URL",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "scroll",
        "description": "Scroll the page",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                "amount": {"type": "integer", "description": "Pixels to scroll", "default": 300},
            },
            "required": ["direction"],
        },
    },
    {
        "name": "wait",
        "description": "Wait for a number of milliseconds",
        "input_schema": {
            "type": "object",
            "properties": {
                "ms": {"type": "integer", "description": "Milliseconds to wait (max 5000)"},
            },
            "required": ["ms"],
        },
    },
    {
        "name": "set_input_files",
        "description": "Upload a file to a file input",
        "input_schema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Element ref for the file input"},
                "path": {"type": "string", "description": "Absolute path to the file to upload"},
            },
            "required": ["ref", "path"],
        },
    },
    {
        "name": "done",
        "description": "Finish the test run with a verdict",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["pass", "fail"],
                    "description": "Whether the story passed",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of why the story passed or failed",
                },
            },
            "required": ["verdict", "reasoning"],
        },
    },
]


@dataclass
class Step:
    step_num: int
    snapshot: str
    tool_name: str
    tool_input: dict[str, Any]
    result: str = ""
    error: str = ""


@dataclass
class AgentResult:
    verdict: str  # "pass", "fail", "timeout"
    reasoning: str
    steps: list[Step] = field(default_factory=list)
    final_snapshot: str = ""


def _extract_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def check_origin(target_url: str, allowed_origins: list[str]) -> None:
    """Raise ValueError if target_url's origin is not in allowed_origins."""
    if not allowed_origins:
        return
    target_origin = _extract_origin(target_url)
    for origin in allowed_origins:
        if target_origin == _extract_origin(origin):
            return
    raise ValueError(
        f"Navigation to {target_url!r} blocked — origin {target_origin!r} "
        f"not in allowed origins: {allowed_origins}"
    )


async def run_agent(
    page: Page,
    session: BrowserSession,
    story: str,
    url: str,
    max_steps: int = MAX_STEPS,
    allowed_origins: list[str] | None = None,
    model_routing: bool = True,
    provider: LLMProvider | None = None,
) -> AgentResult:
    """Run the agent loop and return the result."""
    llm = provider or get_provider()

    if allowed_origins is None:
        allowed_origins = [url]

    await page.goto(url, wait_until="domcontentloaded")
    await session.wait_for_stable()

    steps: list[Step] = []
    messages: list[dict] = []
    last_step_ok = True

    for step_num in range(1, max_steps + 1):
        snap = await session.snapshot()
        snapshot_text = snap.compact()
        element_count = len(snap.elements)

        user_content = (
            f"Step {step_num}/{max_steps}\n\n"
            f"Current page: {page.url}\n"
            f"Title: {await page.title()}\n\n"
            f"Accessibility tree:\n{snapshot_text}\n\n"
            f"User story to test: {story}\n\n"
            f"Choose your next action."
        )

        messages.append({"role": "user", "content": user_content})

        use_fast = (
            model_routing
            and element_count < ROUTING_THRESHOLD
            and last_step_ok
        )
        model = FAST_MODEL if use_fast else AGENT_MODEL

        response = await llm.chat(
            model=model,
            system=AGENT_SYSTEM,
            messages=messages,
            tools=TOOLS,
            max_tokens=1024,
            cache_system=True,
        )

        if not response.tool_calls:
            messages.append({"role": "assistant", "content": response.raw.content if hasattr(response.raw, "content") else response.text})
            continue

        tool_call = response.tool_calls[0]
        tool_name = tool_call.name
        tool_input = tool_call.input

        step = Step(
            step_num=step_num,
            snapshot=snapshot_text,
            tool_name=tool_name,
            tool_input=tool_input,
        )

        if tool_name == "done":
            step.result = "done"
            steps.append(step)
            return AgentResult(
                verdict=tool_input.get("verdict", "fail"),
                reasoning=tool_input.get("reasoning", ""),
                steps=steps,
                final_snapshot=snapshot_text,
            )

        error = ""
        result_text = ""
        try:
            result_text = await _execute_tool(page, session, tool_name, tool_input, allowed_origins)
            last_step_ok = True
        except Exception as e:
            error = str(e)
            result_text = f"Error: {error}"
            last_step_ok = False

        step.result = result_text
        step.error = error
        steps.append(step)

        messages.append({"role": "assistant", "content": response.raw.content if hasattr(response.raw, "content") else response.text})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": result_text,
                }
            ],
        })

    snap = await session.snapshot()
    return AgentResult(
        verdict="timeout",
        reasoning=f"Step budget of {max_steps} exhausted without completing the story.",
        steps=steps,
        final_snapshot=snap.compact(),
    )


async def _execute_tool(
    page: Page,
    session: BrowserSession,
    tool_name: str,
    tool_input: dict[str, Any],
    allowed_origins: list[str] | None = None,
) -> str:
    resolver = session.resolver

    if tool_name == "click":
        ref = tool_input["ref"]
        locator = resolver.resolve(page, ref)
        await locator.click()
        await page.wait_for_load_state("domcontentloaded")
        await session.wait_for_stable()
        return f"Clicked {ref}"

    elif tool_name == "fill":
        ref = tool_input["ref"]
        text = tool_input["text"]
        locator = resolver.resolve(page, ref)
        await locator.fill(text)
        return f"Filled {ref} with text"

    elif tool_name == "select":
        ref = tool_input["ref"]
        value = tool_input["value"]
        locator = resolver.resolve(page, ref)
        await locator.select_option(label=value)
        await session.wait_for_stable()
        return f"Selected {value!r} in {ref}"

    elif tool_name == "press_key":
        key = tool_input["key"]
        await page.keyboard.press(key)
        return f"Pressed {key}"

    elif tool_name == "navigate":
        target_url = tool_input["url"]
        check_origin(target_url, allowed_origins or [])
        await page.goto(target_url, wait_until="domcontentloaded")
        await session.wait_for_stable()
        return f"Navigated to {target_url}"

    elif tool_name == "scroll":
        direction = tool_input["direction"]
        amount = tool_input.get("amount", 300)
        if direction == "down":
            await page.mouse.wheel(0, amount)
        elif direction == "up":
            await page.mouse.wheel(0, -amount)
        elif direction == "right":
            await page.mouse.wheel(amount, 0)
        elif direction == "left":
            await page.mouse.wheel(-amount, 0)
        return f"Scrolled {direction} {amount}px"

    elif tool_name == "wait":
        ms = min(tool_input.get("ms", 1000), 5000)
        await asyncio.sleep(ms / 1000)
        return f"Waited {ms}ms"

    elif tool_name == "set_input_files":
        ref = tool_input["ref"]
        path = tool_input["path"]
        locator = resolver.resolve(page, ref)
        await locator.set_input_files(path)
        return f"Uploaded file {path} to {ref}"

    else:
        raise ValueError(f"Unknown tool: {tool_name}")
