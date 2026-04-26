from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import anthropic
from playwright.async_api import Page

from .browser import BrowserSession
from .config import AGENT_MODEL, ANTHROPIC_API_KEY, MAX_STEPS

AGENT_SYSTEM = """You are QAProbe, an expert QA engineer driving a browser to test a web application.

You will be given a user story describing what a user should be able to do.
Your job is to drive the browser to verify this story is working correctly.

At each step you receive the current accessibility tree of the page and choose ONE tool to execute.
Continue until you have enough information to determine if the story passes or fails.

Rules:
- Only interact with elements that exist in the accessibility tree
- Use refs (like btn:0, inp:1) to identify elements
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
                    "description": "Element ref from the accessibility tree (e.g. btn:0)",
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


async def run_agent(
    page: Page,
    session: BrowserSession,
    story: str,
    url: str,
    max_steps: int = MAX_STEPS,
) -> AgentResult:
    """Run the agent loop and return the result."""
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    # Navigate to starting URL
    await page.goto(url, wait_until="domcontentloaded")

    steps: list[Step] = []
    messages: list[dict] = []

    for step_num in range(1, max_steps + 1):
        # Take snapshot
        snap = await session.snapshot()
        snapshot_text = snap.compact()

        # Build user message with current page state
        user_content = (
            f"Step {step_num}/{max_steps}\n\n"
            f"Current page: {page.url}\n"
            f"Title: {await page.title()}\n\n"
            f"Accessibility tree:\n{snapshot_text}\n\n"
            f"User story to test: {story}\n\n"
            f"Choose your next action."
        )

        messages.append({"role": "user", "content": user_content})

        # Call the model
        response = await client.messages.create(
            model=AGENT_MODEL,
            max_tokens=1024,
            system=AGENT_SYSTEM,
            tools=TOOLS,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        )

        # Extract tool use
        tool_use = None
        for block in response.content:
            if block.type == "tool_use":
                tool_use = block
                break

        if tool_use is None:
            # No tool called — treat as inconclusive step, continue
            messages.append({
                "role": "assistant",
                "content": response.content,
            })
            continue

        tool_name = tool_use.name
        tool_input = tool_use.input

        step = Step(
            step_num=step_num,
            snapshot=snapshot_text,
            tool_name=tool_name,
            tool_input=tool_input,
        )

        # Execute the tool
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
            result_text = await _execute_tool(page, session, tool_name, tool_input)
        except Exception as e:
            error = str(e)
            result_text = f"Error: {error}"

        step.result = result_text
        step.error = error
        steps.append(step)

        # Add assistant response and tool result to messages
        messages.append({
            "role": "assistant",
            "content": response.content,
        })
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_text,
                }
            ],
        })

    # Step budget exhausted
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
) -> str:
    resolver = session.resolver

    if tool_name == "click":
        ref = tool_input["ref"]
        locator = resolver.resolve(page, ref)
        await locator.click()
        await page.wait_for_load_state("domcontentloaded")
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
        return f"Selected {value!r} in {ref}"

    elif tool_name == "press_key":
        key = tool_input["key"]
        await page.keyboard.press(key)
        return f"Pressed {key}"

    elif tool_name == "navigate":
        url = tool_input["url"]
        await page.goto(url, wait_until="domcontentloaded")
        return f"Navigated to {url}"

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
