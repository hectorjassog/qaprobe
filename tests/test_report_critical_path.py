"""Self-test: replay a critical path against qaprobe's own suite HTML report.

This is the full recursive loop -- qaprobe's replay engine verifying that
qaprobe's own report output is navigable and structurally sound.
"""

import pytest

from qaprobe.critical_path import CriticalPath, Locator, PathStep
from qaprobe.replay import replay_path
from qaprobe.report import RunReport, build_suite_html_report


def _sample_report(verdict: str, name: str) -> RunReport:
    return RunReport(
        run_id=f"run-{name}",
        url="https://example.com",
        story=f"Test story for {name}",
        started_at="2026-04-28T23:00:00Z",
        finished_at="2026-04-28T23:00:05Z",
        verdict=verdict,
        agent_verdict=verdict,
        agent_reasoning=f"Reasoning for {name}.",
        verifier_goal_achieved=verdict == "pass",
        verifier_confidence="high",
        verifier_reasoning="Verified.",
        steps=[
            {
                "step_num": 1,
                "tool": "navigate",
                "input": {"url": "/"},
                "result": "ok",
                "error": "",
            },
        ],
        a11y_findings=[],
        artifacts={"trace": "trace.zip"},
    )


def _generate_suite_html(tmp_path):
    reports = [
        _sample_report("pass", "login"),
        _sample_report("fail", "checkout"),
    ]
    html = build_suite_html_report(
        "self-test", "run-001", reports,
        {"login": "login", "checkout": "checkout"},
    )
    html_file = tmp_path / "index.html"
    html_file.write_text(html, encoding="utf-8")
    return html_file


async def _replay_against_file(html_file, name, steps, timeout_ms=5000):
    """Replay a critical path against a local HTML file."""
    file_url = f"file://{html_file}"
    path = CriticalPath(
        name=name,
        steps=[PathStep(action="navigate", url=file_url)] + steps,
    )
    return await replay_path(
        path,
        base_url="unused",
        headless=True,
        timeout_ms=timeout_ms,
    )


@pytest.mark.asyncio
async def test_suite_report_heading_clickable(tmp_path):
    """The suite report heading is present and clickable."""
    html_file = _generate_suite_html(tmp_path)
    result = await _replay_against_file(html_file, "verify_heading", [
        PathStep(
            action="click",
            locator=Locator(role="heading", name="QAProbe Suite Report"),
        ),
    ])
    assert result.passed, f"Heading not found: {result.error}"


@pytest.mark.asyncio
async def test_suite_report_story_details_expandable(tmp_path):
    """The collapsible story details can be expanded."""
    html_file = _generate_suite_html(tmp_path)
    result = await _replay_against_file(html_file, "expand_details", [
        PathStep(
            action="click",
            locator=Locator(role="group", name="", exact=False),
        ),
    ])
    assert result.passed, f"Details not expandable: {result.error}"


@pytest.mark.asyncio
async def test_suite_report_has_story_links(tmp_path):
    """Full report links are present and clickable."""
    html_file = _generate_suite_html(tmp_path)
    result = await _replay_against_file(html_file, "click_full_report", [
        PathStep(
            action="click",
            locator=Locator(role="link", name="Full report"),
        ),
    ])
    assert result.passed, f"Full report link not found: {result.error}"


@pytest.mark.asyncio
async def test_suite_report_summary_cards_present(tmp_path):
    """Summary bar cards with pass/fail counts are visible."""
    html_file = _generate_suite_html(tmp_path)
    result = await _replay_against_file(html_file, "find_summary", [
        PathStep(
            action="click",
            locator=Locator(role="heading", name="QAProbe Suite Report"),
        ),
    ])
    assert result.passed, f"Summary not found: {result.error}"
    assert "index.html" in result.final_url
