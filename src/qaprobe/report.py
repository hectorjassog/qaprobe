from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .agent import AgentResult
from .verifier import VerifierResult


@dataclass
class A11yFinding:
    type: str  # e.g. "missing_label", "heading_skip", "empty_alt"
    severity: str  # "error", "warning", "info"
    element_ref: str
    element_role: str
    element_name: str
    message: str


@dataclass
class RunReport:
    run_id: str
    url: str
    story: str
    started_at: str
    finished_at: str
    verdict: str  # "pass", "fail", "inconclusive"
    agent_verdict: str
    agent_reasoning: str
    verifier_goal_achieved: bool
    verifier_confidence: str
    verifier_reasoning: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    a11y_findings: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)


def reconcile_verdict(
    agent_result: AgentResult,
    verifier_result: VerifierResult,
) -> str:
    """Reconcile agent and verifier verdicts into a final verdict.

    Confidence calibration: if both agree pass but verifier confidence is low,
    returns inconclusive instead of pass.
    """
    agent_pass = agent_result.verdict == "pass"
    verifier_pass = verifier_result.goal_achieved

    if agent_pass and verifier_pass:
        if verifier_result.confidence == "low":
            return "inconclusive"
        return "pass"
    elif not agent_pass and not verifier_pass:
        return "fail"
    else:
        return "inconclusive"


def mask_secrets(
    steps: list[dict[str, Any]],
    reveal_fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Redact fill text values in step data, unless the field is in reveal_fields."""
    reveal = set(reveal_fields or [])
    masked = []
    for step in steps:
        step = dict(step)
        if step.get("tool") == "fill":
            inp = dict(step.get("input", {}))
            ref = inp.get("ref", "")
            if ref not in reveal and "text" in inp:
                inp["text"] = "***"
            step["input"] = inp
        masked.append(step)
    return masked


def build_report(
    run_id: str,
    url: str,
    story: str,
    started_at: datetime,
    finished_at: datetime,
    agent_result: AgentResult,
    verifier_result: VerifierResult,
    a11y_findings: list[A11yFinding],
    artifacts: dict[str, str],
    reveal_fields: list[str] | None = None,
    reveal_secrets: bool = False,
) -> RunReport:
    verdict = reconcile_verdict(agent_result, verifier_result)

    steps = [
        {
            "step_num": s.step_num,
            "tool": s.tool_name,
            "input": s.tool_input,
            "result": s.result,
            "error": s.error,
        }
        for s in agent_result.steps
    ]

    if not reveal_secrets:
        steps = mask_secrets(steps, reveal_fields)

    return RunReport(
        run_id=run_id,
        url=url,
        story=story,
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        verdict=verdict,
        agent_verdict=agent_result.verdict,
        agent_reasoning=agent_result.reasoning,
        verifier_goal_achieved=verifier_result.goal_achieved,
        verifier_confidence=verifier_result.confidence,
        verifier_reasoning=verifier_result.reasoning,
        steps=steps,
        a11y_findings=[asdict(f) for f in a11y_findings],
        artifacts=artifacts,
    )


def save_report(report: RunReport, path: Path) -> None:
    path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QAProbe Report — {run_id}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ color: #1a1a2e; }}
  .verdict {{ display: inline-block; padding: .25rem .75rem; border-radius: 4px; font-weight: bold; text-transform: uppercase; }}
  .pass {{ background: #dcfce7; color: #166534; }}
  .fail {{ background: #fee2e2; color: #991b1b; }}
  .inconclusive {{ background: #fef9c3; color: #854d0e; }}
  .meta {{ color: #6b7280; font-size: .9rem; margin: .5rem 0; }}
  details {{ margin: 1rem 0; border: 1px solid #e5e7eb; border-radius: 6px; }}
  summary {{ padding: .75rem 1rem; cursor: pointer; font-weight: 600; background: #f9fafb; }}
  .step {{ padding: .5rem 1rem; border-top: 1px solid #e5e7eb; font-size: .85rem; }}
  .step:nth-child(even) {{ background: #f9fafb; }}
  .tool {{ color: #6366f1; font-weight: 600; }}
  .error {{ color: #dc2626; }}
  .a11y-finding {{ padding: .5rem; margin: .25rem 0; border-left: 3px solid #f59e0b; background: #fffbeb; }}
  .a11y-error {{ border-color: #ef4444; background: #fef2f2; }}
  pre {{ background: #f3f4f6; padding: .5rem; border-radius: 4px; overflow-x: auto; font-size: .8rem; }}
</style>
</head>
<body>
<h1>QAProbe Run Report</h1>
<p class="meta">Run ID: <code>{run_id}</code></p>
<p class="meta">URL: <a href="{url}">{url}</a></p>
<p class="meta">Story: <em>{story}</em></p>
<p class="meta">Started: {started_at} | Finished: {finished_at}</p>

<h2>Verdict: <span class="verdict {verdict}">{verdict}</span></h2>

<details open>
<summary>Agent Assessment ({agent_verdict})</summary>
<div style="padding: 1rem">
<p>{agent_reasoning}</p>
</div>
</details>

<details open>
<summary>Verifier Assessment (confidence: {verifier_confidence})</summary>
<div style="padding: 1rem">
<p>{verifier_reasoning}</p>
</div>
</details>

<details>
<summary>Steps ({step_count} steps)</summary>
{steps_html}
</details>

<details>
<summary>Accessibility Findings ({a11y_count} findings)</summary>
{a11y_html}
</details>

<details>
<summary>Artifacts</summary>
<div style="padding: 1rem">
{artifacts_html}
</div>
</details>
</body>
</html>"""


def build_html_report(report: RunReport) -> str:
    steps_html_parts = []
    for step in report.steps:
        tool = step.get("tool", "")
        inp = json.dumps(step.get("input", {}))
        result = step.get("result", "")
        error = step.get("error", "")
        err_html = f'<span class="error"> Error: {error}</span>' if error else ""
        steps_html_parts.append(
            f'<div class="step"><strong>Step {step.get("step_num", "?")}:</strong> '
            f'<span class="tool">{tool}</span> {inp}'
            f" → {result}{err_html}</div>"
        )
    steps_html = "\n".join(steps_html_parts) or "<div class='step'>No steps recorded</div>"

    a11y_html_parts = []
    for finding in report.a11y_findings:
        css = "a11y-error" if finding.get("severity") == "error" else "a11y-finding"
        a11y_html_parts.append(
            f'<div class="{css}"><strong>{finding.get("type", "")}</strong>: '
            f'{finding.get("message", "")} '
            f'<em>[{finding.get("element_ref", "")} {finding.get("element_role", "")} '
            f'"{finding.get("element_name", "")}"]</em></div>'
        )
    a11y_html = "\n".join(a11y_html_parts) or "<div style='padding:1rem'>No findings</div>"

    artifacts_html_parts = []
    for name, path in report.artifacts.items():
        artifacts_html_parts.append(f'<p><a href="{path}">{name}</a></p>')
    artifacts_html = "\n".join(artifacts_html_parts) or "<p>No artifacts</p>"

    return HTML_TEMPLATE.format(
        run_id=report.run_id,
        url=report.url,
        story=report.story,
        started_at=report.started_at,
        finished_at=report.finished_at,
        verdict=report.verdict,
        agent_verdict=report.agent_verdict,
        agent_reasoning=report.agent_reasoning,
        verifier_confidence=report.verifier_confidence,
        verifier_reasoning=report.verifier_reasoning,
        step_count=len(report.steps),
        steps_html=steps_html,
        a11y_count=len(report.a11y_findings),
        a11y_html=a11y_html,
        artifacts_html=artifacts_html,
    )


# --- Suite-level aggregate HTML report ---

SUITE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>QAProbe Suite Report — {suite_name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #1a1a2e; }}
  h1 {{ margin-bottom: .5rem; }}
  .suite-meta {{ color: #6b7280; font-size: .9rem; margin-bottom: 1.5rem; }}
  .summary-bar {{ display: flex; gap: 1rem; margin-bottom: 2rem; }}
  .summary-card {{ padding: 1rem 1.5rem; border-radius: 8px; font-weight: 700; font-size: 1.1rem; }}
  .summary-card.pass {{ background: #dcfce7; color: #166534; }}
  .summary-card.fail {{ background: #fee2e2; color: #991b1b; }}
  .summary-card.inconclusive {{ background: #fef9c3; color: #854d0e; }}
  .summary-card.total {{ background: #f3f4f6; color: #374151; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
  .story-card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; }}
  .story-card .name {{ font-weight: 600; margin-bottom: .25rem; }}
  .story-card .story-text {{ color: #6b7280; font-size: .85rem; margin-bottom: .5rem; }}
  .verdict-badge {{ display: inline-block; padding: .15rem .5rem; border-radius: 4px; font-weight: bold; text-transform: uppercase; font-size: .8rem; }}
  .verdict-badge.pass {{ background: #dcfce7; color: #166534; }}
  .verdict-badge.fail {{ background: #fee2e2; color: #991b1b; }}
  .verdict-badge.inconclusive {{ background: #fef9c3; color: #854d0e; }}
  .story-links {{ margin-top: .5rem; font-size: .8rem; }}
  .story-links a {{ color: #6366f1; text-decoration: none; margin-right: .75rem; }}
  .story-links a:hover {{ text-decoration: underline; }}
  details {{ margin: 1rem 0; border: 1px solid #e5e7eb; border-radius: 6px; }}
  summary {{ padding: .75rem 1rem; cursor: pointer; font-weight: 600; background: #f9fafb; }}
  .step {{ padding: .5rem 1rem; border-top: 1px solid #e5e7eb; font-size: .85rem; }}
  .tool {{ color: #6366f1; font-weight: 600; }}
  .error {{ color: #dc2626; }}
  .a11y-finding {{ padding: .5rem; margin: .25rem 0; border-left: 3px solid #f59e0b; background: #fffbeb; }}
  .a11y-error {{ border-color: #ef4444; background: #fef2f2; }}
</style>
</head>
<body>
<h1>QAProbe Suite Report</h1>
<p class="suite-meta">{suite_name} &middot; {suite_run_id} &middot; {total_duration}</p>

<div class="summary-bar">
  <div class="summary-card total">{total_count} stories</div>
  <div class="summary-card pass">{pass_count} passed</div>
  <div class="summary-card fail">{fail_count} failed</div>
  <div class="summary-card inconclusive">{inconclusive_count} inconclusive</div>
</div>

<div class="grid">
{story_cards}
</div>

{story_details}
</body>
</html>"""


def build_suite_html_report(
    suite_name: str,
    suite_run_id: str,
    reports: list[RunReport],
    story_dirs: dict[str, str] | None = None,
) -> str:
    pass_count = sum(1 for r in reports if r.verdict == "pass")
    fail_count = sum(1 for r in reports if r.verdict == "fail")
    inconclusive_count = sum(1 for r in reports if r.verdict == "inconclusive")
    total_count = len(reports)

    if reports:
        first = reports[0].started_at
        last = reports[-1].finished_at
        total_duration = f"{first} → {last}"
    else:
        total_duration = "N/A"

    dirs = story_dirs or {}

    card_parts = []
    detail_parts = []
    for report in reports:
        story_name = report.run_id.split("-", 1)[-1] if "-" in report.run_id else report.run_id
        story_dir = dirs.get(story_name, story_name)

        links = []
        links.append(f'<a href="{story_dir}/report.html">Full report</a>')
        if report.artifacts.get("video"):
            links.append(f'<a href="{story_dir}/video/">Video</a>')
        if report.artifacts.get("trace"):
            links.append(f'<a href="{story_dir}/trace.zip">Trace</a>')

        card_parts.append(
            f'<div class="story-card">'
            f'<div class="name">{story_name}</div>'
            f'<div class="story-text">{report.story[:80]}{"..." if len(report.story) > 80 else ""}</div>'
            f'<span class="verdict-badge {report.verdict}">{report.verdict}</span>'
            f'<div class="story-links">{"".join(links)}</div>'
            f'</div>'
        )

        steps_html = ""
        for step in report.steps:
            tool = step.get("tool", "")
            inp = json.dumps(step.get("input", {}))
            result = step.get("result", "")
            error = step.get("error", "")
            err_html = f'<span class="error"> Error: {error}</span>' if error else ""
            steps_html += (
                f'<div class="step"><strong>Step {step.get("step_num", "?")}:</strong> '
                f'<span class="tool">{tool}</span> {inp} → {result}{err_html}</div>\n'
            )

        a11y_html = ""
        for finding in report.a11y_findings:
            css = "a11y-error" if finding.get("severity") == "error" else "a11y-finding"
            a11y_html += (
                f'<div class="{css}"><strong>{finding.get("type", "")}</strong>: '
                f'{finding.get("message", "")} '
                f'<em>[{finding.get("element_ref", "")}]</em></div>\n'
            )

        detail_parts.append(
            f'<details>\n'
            f'<summary><span class="verdict-badge {report.verdict}">{report.verdict}</span> {story_name} — {report.story[:60]}</summary>\n'
            f'<div style="padding:1rem">\n'
            f'<p><strong>Agent:</strong> {report.agent_verdict} — {report.agent_reasoning}</p>\n'
            f'<p><strong>Verifier:</strong> {"pass" if report.verifier_goal_achieved else "fail"} (confidence: {report.verifier_confidence}) — {report.verifier_reasoning}</p>\n'
            f'<h4>Steps ({len(report.steps)})</h4>\n{steps_html or "<p>No steps</p>"}\n'
            f'<h4>A11y Findings ({len(report.a11y_findings)})</h4>\n{a11y_html or "<p>None</p>"}\n'
            f'</div>\n</details>'
        )

    return SUITE_HTML_TEMPLATE.format(
        suite_name=suite_name,
        suite_run_id=suite_run_id,
        total_duration=total_duration,
        total_count=total_count,
        pass_count=pass_count,
        fail_count=fail_count,
        inconclusive_count=inconclusive_count,
        story_cards="\n".join(card_parts),
        story_details="\n".join(detail_parts),
    )
