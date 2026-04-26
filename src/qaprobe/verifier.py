from __future__ import annotations

import json
import re
from dataclasses import dataclass

import anthropic

from .agent import AgentResult
from .config import ANTHROPIC_API_KEY, VERIFIER_MODEL

VERIFIER_SYSTEM = """You are an independent QA verifier. You will review the execution history of a browser automation agent and determine whether the user's story was successfully demonstrated.

You must make an INDEPENDENT judgment based on the evidence — not just accept the agent's self-reported verdict.

Be critical but fair. If there's ambiguity, report it."""


@dataclass
class VerifierResult:
    goal_achieved: bool
    confidence: str  # "high", "medium", "low"
    reasoning: str


async def run_verifier(
    story: str,
    agent_result: AgentResult,
) -> VerifierResult:
    """Run the independent verifier on the agent's result."""
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

    # Build step history summary
    step_lines = []
    for step in agent_result.steps:
        step_lines.append(
            f"Step {step.step_num}: {step.tool_name}({step.tool_input}) → {step.result or step.error}"
        )
    step_history = "\n".join(step_lines) if step_lines else "(no steps recorded)"

    prompt = (
        f"User story: {story}\n\n"
        f"Agent verdict: {agent_result.verdict}\n"
        f"Agent reasoning: {agent_result.reasoning}\n\n"
        f"Step history:\n{step_history}\n\n"
        f"Final page state (accessibility tree):\n{agent_result.final_snapshot}\n\n"
        f"Based on this evidence, did the agent successfully demonstrate the user story?\n\n"
        f"Respond with a JSON object:\n"
        f'{{\n  "goal_achieved": true/false,\n  "confidence": "high"/"medium"/"low",\n  "reasoning": "your independent assessment"\n}}'
    )

    response = await client.messages.create(
        model=VERIFIER_MODEL,
        max_tokens=1024,
        system=VERIFIER_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text if response.content else "{}"

    # Extract JSON from possible markdown code blocks
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

    # Fallback: try to parse the whole text
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
