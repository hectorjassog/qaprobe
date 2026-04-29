"""Self-test: audit qaprobe's own HTML report templates for accessibility.

This test generates sample RunReports, renders them to HTML, opens them
in a headless browser, takes an AX snapshot, and runs the same a11y
auditor that qaprobe uses on user sites. Any findings here mean we're
shipping inaccessible reports.
"""

import pytest

from qaprobe.a11y import audit_snapshot
from qaprobe.report import RunReport, build_html_report, build_suite_html_report


def _sample_report(verdict: str = "pass", name: str = "story") -> RunReport:
    return RunReport(
        run_id=f"self-test-{name}",
        url="https://example.com",
        story="Click the link and verify navigation works",
        started_at="2026-04-28T23:00:00Z",
        finished_at="2026-04-28T23:00:05Z",
        verdict=verdict,
        agent_verdict=verdict,
        agent_reasoning="Test reasoning.",
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
            {
                "step_num": 2,
                "tool": "click",
                "input": {"ref": "lnk:more"},
                "result": "ok",
                "error": "",
            },
        ],
        a11y_findings=[
            {
                "type": "missing_label",
                "severity": "error",
                "element_ref": "inp:demo",
                "element_role": "textbox",
                "element_name": "",
                "message": "Example finding for rendering",
            },
        ],
        artifacts={"trace": "trace.zip"},
    )


async def _audit_html(html: str, tmp_path) -> list:
    """Write HTML to disk, open in headless Playwright, snapshot, audit."""
    from playwright.async_api import async_playwright

    from qaprobe.browser import parse_ax_tree

    html_file = tmp_path / "report.html"
    html_file.write_text(html, encoding="utf-8")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"file://{html_file}")
        await page.wait_for_load_state("domcontentloaded")

        cdp = await page.context.new_cdp_session(page)
        result = await cdp.send("Accessibility.getFullAXTree")
        snapshot = parse_ax_tree(result.get("nodes", []))

        await cdp.detach()
        await browser.close()

    return audit_snapshot(snapshot)


@pytest.mark.asyncio
async def test_single_report_has_no_a11y_errors(tmp_path):
    report = _sample_report("pass")
    html = build_html_report(report)
    findings = await _audit_html(html, tmp_path)
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"a11y errors in single report: {[f.message for f in errors]}"


@pytest.mark.asyncio
async def test_single_report_fail_verdict_accessible(tmp_path):
    report = _sample_report("fail")
    html = build_html_report(report)
    findings = await _audit_html(html, tmp_path)
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"a11y errors in fail report: {[f.message for f in errors]}"


@pytest.mark.asyncio
async def test_suite_report_has_no_a11y_errors(tmp_path):
    reports = [
        _sample_report("pass", "login"),
        _sample_report("fail", "checkout"),
        _sample_report("inconclusive", "search"),
    ]
    html = build_suite_html_report(
        "self-test-suite",
        "run-001",
        reports,
        {"login": "login", "checkout": "checkout", "search": "search"},
    )
    findings = await _audit_html(html, tmp_path)
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"a11y errors in suite report: {[f.message for f in errors]}"


@pytest.mark.asyncio
async def test_empty_suite_report_accessible(tmp_path):
    html = build_suite_html_report("empty", "run-002", [], {})
    findings = await _audit_html(html, tmp_path)
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"a11y errors in empty suite: {[f.message for f in errors]}"


@pytest.mark.asyncio
async def test_suite_report_heading_hierarchy(tmp_path):
    """Verify the suite report doesn't skip heading levels."""
    reports = [_sample_report("pass", "story1")]
    html = build_suite_html_report("test", "run-003", reports, {"story1": "story1"})
    findings = await _audit_html(html, tmp_path)
    heading_skips = [f for f in findings if f.type == "heading_skip"]
    assert heading_skips == [], (
        f"Heading level skips in suite report: {[f.message for f in heading_skips]}"
    )
