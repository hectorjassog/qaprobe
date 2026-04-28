from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .agent import AgentResult
from .config import VERIFIER_MODEL
from .provider import LLMProvider, get_provider

VERIFIER_SYSTEM = """You are an independent QA verifier. You will review the execution history of a browser automation agent and determine whether the user's story was successfully demonstrated.

You must make an INDEPENDENT judgment based on the evidence — not just accept the agent's self-reported verdict.

Be critical but fair. If there's ambiguity, report it."""

SNAPSHOT_HISTORY_STEPS = 5


@dataclass
class VerifierResult:
    goal_achieved: bool
    confidence: str  # "high", "medium", "low"
    reasoning: str


async def run_verifier(
    story: str,
    agent_result: AgentResult,
    screenshot_b64: str | None = None,
    provider: LLMProvider | None = None,
) -> VerifierResult:
    """Run the independent verifier on the agent's result."""
    llm = provider or get_provider()

    step_lines = []
    for step in agent_result.steps:
        step_lines.append(
            f"Step {step.step_num}: {step.tool_name}({step.tool_input}) → {step.result or step.error}"
        )
    step_history = "\n".join(step_lines) if step_lines else "(no steps recorded)"

    snapshot_history_parts = []
    recent_steps = agent_result.steps[-SNAPSHOT_HISTORY_STEPS:]
    for step in recent_steps:
        truncated = "\n".join(step.snapshot.split("\n")[:50])
        snapshot_history_parts.append(f"--- After step {step.step_num} ---\n{truncated}")
    snapshot_history = "\n\n".join(snapshot_history_parts) if snapshot_history_parts else "(no snapshots)"

    prompt = (
        f"User story: {story}\n\n"
        f"Agent verdict: {agent_result.verdict}\n"
        f"Agent reasoning: {agent_result.reasoning}\n\n"
        f"Step history:\n{step_history}\n\n"
        f"Snapshot history (last {SNAPSHOT_HISTORY_STEPS} steps):\n{snapshot_history}\n\n"
        f"Final page state (accessibility tree):\n{agent_result.final_snapshot}\n\n"
        f"Based on this evidence, did the agent successfully demonstrate the user story?\n\n"
        f"Respond with a JSON object:\n"
        f'{{\n  "goal_achieved": true/false,\n  "confidence": "high"/"medium"/"low",\n  "reasoning": "your independent assessment"\n}}'
    )

    content: list[dict] = [{"type": "text", "text": prompt}]
    if screenshot_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        })

    messages = [{"role": "user", "content": content}]

    response = await llm.chat(
        model=VERIFIER_MODEL,
        system=VERIFIER_SYSTEM,
        messages=messages,
        max_tokens=1024,
    )

    text = response.text or "{}"
    return _parse_verifier_response(text)


def _parse_verifier_response(text: str) -> VerifierResult:
    json_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            return VerifierResult(
                goal_achieved=bool(data.get("goal_achieved", False)),
                confidence=str(data.get("confidence", "low")),
                reasoning=str(data.get("reasoning", "")),
            )
        except json.JSONDecodeError:
            pass

    try:
        data = json.loads(text)
        return VerifierResult(
            goal_achieved=bool(data.get("goal_achieved", False)),
            confidence=str(data.get("confidence", "low")),
            reasoning=str(data.get("reasoning", text)),
        )
    except json.JSONDecodeError:
        return VerifierResult(
            goal_achieved=False,
            confidence="low",
            reasoning=f"Could not parse verifier response: {text[:200]}",
        )
