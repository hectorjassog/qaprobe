"""Tests for the replay engine (unit-level, no real browser)."""

from qaprobe.critical_path import Locator, PathStep
from qaprobe.replay import ReplayResult, StepResult, _step_detail


def test_step_detail_navigate():
    step = PathStep(action="navigate", url="/products")
    assert _step_detail(step) == "/products"


def test_step_detail_click():
    step = PathStep(action="click", locator=Locator(role="button", name="Submit"))
    assert _step_detail(step) == 'button("Submit")'


def test_step_detail_click_nth():
    step = PathStep(action="click", locator=Locator(role="link", name="Delete", nth=2))
    assert _step_detail(step) == 'link("Delete").nth(2)'


def test_step_detail_fill():
    step = PathStep(action="fill", locator=Locator(role="textbox", name="Email"), value="a@b.com")
    assert "textbox" in _step_detail(step)
    assert "a@b.com" in _step_detail(step)


def test_step_detail_press_key():
    step = PathStep(action="press_key", key="Enter")
    assert _step_detail(step) == "Enter"


def test_step_detail_scroll():
    step = PathStep(action="scroll", direction="down", amount=500)
    assert _step_detail(step) == "down 500px"


def test_step_detail_wait():
    step = PathStep(action="wait", ms=2000)
    assert _step_detail(step) == "2000ms"


def test_step_result_to_dict():
    sr = StepResult(
        step_num=1, action="click", detail='button("OK")',
        passed=True, duration_ms=123.456,
    )
    d = sr.to_dict()
    assert d["step_num"] == 1
    assert d["passed"] is True
    assert d["duration_ms"] == 123.5
    assert "error" not in d


def test_step_result_to_dict_with_error():
    sr = StepResult(
        step_num=3, action="fill", detail='textbox("Email")',
        passed=False, duration_ms=5000.0, error="Element not found",
    )
    d = sr.to_dict()
    assert d["passed"] is False
    assert d["error"] == "Element not found"


def test_replay_result_step_dicts():
    rr = ReplayResult(
        path_name="test",
        passed=True,
        steps=[
            StepResult(step_num=1, action="navigate", detail="/", passed=True, duration_ms=100.0),
            StepResult(
                step_num=2, action="click", detail='button("Go")',
                passed=True, duration_ms=50.0,
            ),
        ],
    )
    dicts = rr.step_dicts
    assert len(dicts) == 2
    assert dicts[0]["action"] == "navigate"
    assert dicts[1]["action"] == "click"


def test_replay_result_defaults():
    rr = ReplayResult(path_name="empty", passed=False)
    assert rr.total_duration_ms == 0.0
    assert rr.failed_step is None
    assert rr.error == ""
    assert rr.screenshot_b64 == ""
    assert rr.final_url == ""
    assert rr.step_dicts == []
