"""Unit tests for baseline mode."""


from qaprobe.suite import check_regressions, load_baseline, save_baseline


def test_save_and_load_baseline(tmp_path):
    path = str(tmp_path / "baseline.json")
    verdicts = {"story_a": "pass", "story_b": "fail"}
    save_baseline(verdicts, path)
    loaded = load_baseline(path)
    assert loaded == verdicts


def test_load_missing_baseline(tmp_path):
    path = str(tmp_path / "nonexistent.json")
    assert load_baseline(path) == {}


def test_check_regressions_detects_regression():
    baseline = {"story_a": "pass", "story_b": "fail"}
    current = {"story_a": "fail", "story_b": "fail"}
    regressions = check_regressions(current, baseline)
    assert regressions == ["story_a"]


def test_check_regressions_no_regression():
    baseline = {"story_a": "pass", "story_b": "fail"}
    current = {"story_a": "pass", "story_b": "pass"}
    regressions = check_regressions(current, baseline)
    assert regressions == []


def test_check_regressions_new_story_not_regression():
    baseline = {"story_a": "pass"}
    current = {"story_a": "pass", "story_b": "fail"}
    regressions = check_regressions(current, baseline)
    assert regressions == []


def test_check_regressions_already_failing_not_regression():
    baseline = {"story_a": "fail"}
    current = {"story_a": "fail"}
    regressions = check_regressions(current, baseline)
    assert regressions == []
