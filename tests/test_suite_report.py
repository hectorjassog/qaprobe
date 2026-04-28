"""Unit tests for suite-level HTML report generation."""

from qaprobe.report import RunReport, build_suite_html_report


def _report(name, verdict, story="Test story"):
    return RunReport(
        run_id=f"run-{name}",
        url=f"http://example.com/{name}",
        story=story,
        started_at="2026-04-28T00:00:00",
        finished_at="2026-04-28T00:01:00",
        verdict=verdict,
        agent_verdict=verdict,
        agent_reasoning=f"Agent says {verdict}",
        verifier_goal_achieved=(verdict == "pass"),
        verifier_confidence="high",
        verifier_reasoning=f"Verifier says {verdict}",
        steps=[
            {"step_num": 1, "tool": "click", "input": {"ref": "btn:0"}, "result": "ok", "error": ""}
        ],
        a11y_findings=[],
        artifacts={},
    )


def test_suite_report_contains_all_stories():
    reports = [_report("a", "pass"), _report("b", "fail"), _report("c", "inconclusive")]
    html = build_suite_html_report("test-suite", "20260428", reports)
    assert "test-suite" in html
    assert "3 stories" in html
    assert "1 passed" in html
    assert "1 failed" in html
    assert "1 inconclusive" in html


def test_suite_report_has_story_cards():
    reports = [_report("checkout", "pass", story="Complete checkout")]
    html = build_suite_html_report("suite", "id", reports)
    assert "checkout" in html
    assert "Complete checkout" in html


def test_empty_suite():
    html = build_suite_html_report("empty", "id", [])
    assert "0 stories" in html
