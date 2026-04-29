"""Tests for locator resilience: edit distance, suggestions, schema, and recorder fallbacks."""

from qaprobe.browser import AXElement, Snapshot
from qaprobe.critical_path import (
    CriticalPath,
    CriticalPathFile,
    Locator,
    PathStep,
    load_critical_paths,
    save_critical_paths,
)
from qaprobe.recorder import RecordedEvent, events_to_critical_path
from qaprobe.replay import StepResult, _edit_distance, suggest_closest

# ---------------------------------------------------------------------------
# Edit distance
# ---------------------------------------------------------------------------


def test_edit_distance_identical():
    assert _edit_distance("hello", "hello") == 0


def test_edit_distance_case_insensitive():
    assert _edit_distance("Hello", "hello") == 0


def test_edit_distance_one_char():
    assert _edit_distance("cat", "car") == 1


def test_edit_distance_insertion():
    assert _edit_distance("Learn more", "Learn more...") == 3


def test_edit_distance_empty():
    assert _edit_distance("", "abc") == 3
    assert _edit_distance("abc", "") == 3


def test_edit_distance_completely_different():
    dist = _edit_distance("abc", "xyz")
    assert dist == 3


# ---------------------------------------------------------------------------
# suggest_closest
# ---------------------------------------------------------------------------


def _make_snapshot(elements: list[tuple[str, str]]) -> Snapshot:
    """Build a minimal Snapshot from (role, name) pairs."""
    axels = [
        AXElement(ref=f"ref{i}", role=role, name=name)
        for i, (role, name) in enumerate(elements)
    ]
    return Snapshot(elements=axels)


def test_suggest_closest_exact_role_close_name():
    snap = _make_snapshot([
        ("button", "Learn More"),
        ("link", "About"),
        ("button", "Submit"),
    ])
    suggestions = suggest_closest(snap, "button", "Learn more")
    assert len(suggestions) >= 1
    assert 'button("Learn More")' in suggestions[0]


def test_suggest_closest_same_name_different_role():
    snap = _make_snapshot([
        ("link", "Learn more"),
        ("heading", "Title"),
    ])
    suggestions = suggest_closest(snap, "button", "Learn more")
    assert any("different role" in s for s in suggestions)


def test_suggest_closest_no_match():
    snap = _make_snapshot([
        ("heading", "Welcome"),
        ("paragraph", "Some text"),
    ])
    suggestions = suggest_closest(snap, "button", "Submit")
    assert len(suggestions) <= 3


def test_suggest_closest_empty_name():
    snap = _make_snapshot([("button", "OK")])
    suggestions = suggest_closest(snap, "button", "")
    assert suggestions == []


def test_suggest_closest_max_results():
    snap = _make_snapshot([
        ("button", "A"),
        ("button", "B"),
        ("button", "C"),
        ("button", "D"),
        ("button", "E"),
    ])
    suggestions = suggest_closest(snap, "button", "X", max_suggestions=2)
    assert len(suggestions) <= 2


def test_suggest_closest_sorts_by_distance():
    snap = _make_snapshot([
        ("button", "Submit Form"),
        ("button", "Submt"),
        ("button", "Completely Different"),
    ])
    suggestions = suggest_closest(snap, "button", "Submit")
    assert "Submt" in suggestions[0]


# ---------------------------------------------------------------------------
# Extended Locator schema
# ---------------------------------------------------------------------------


def test_locator_with_test_id():
    loc = Locator(role="button", name="Add", test_id="add-btn")
    d = loc.to_dict()
    assert d["test_id"] == "add-btn"
    assert "css" not in d
    assert "exact" not in d


def test_locator_with_css():
    loc = Locator(role="button", name="Go", css="button.primary")
    d = loc.to_dict()
    assert d["css"] == "button.primary"
    assert "test_id" not in d


def test_locator_with_exact_false():
    loc = Locator(role="textbox", name="Email", exact=False)
    d = loc.to_dict()
    assert d["exact"] is False


def test_locator_exact_true_not_serialized():
    loc = Locator(role="button", name="OK", exact=True)
    d = loc.to_dict()
    assert "exact" not in d


def test_locator_from_dict_with_fallbacks():
    d = {
        "role": "button",
        "name": "Submit",
        "test_id": "submit-btn",
        "css": ".form-submit",
        "exact": False,
    }
    loc = Locator.from_dict(d)
    assert loc.role == "button"
    assert loc.name == "Submit"
    assert loc.test_id == "submit-btn"
    assert loc.css == ".form-submit"
    assert loc.exact is False


def test_locator_from_dict_backward_compatible():
    d = {"role": "link", "name": "Home"}
    loc = Locator.from_dict(d)
    assert loc.test_id == ""
    assert loc.css == ""
    assert loc.exact is True


def test_locator_yaml_round_trip(tmp_path):
    cpf = CriticalPathFile(
        base_url="http://localhost",
        name="test",
        paths=[
            CriticalPath(
                name="flow",
                steps=[
                    PathStep(
                        action="click",
                        locator=Locator(
                            role="button",
                            name="Buy",
                            test_id="buy-btn",
                            css="button.buy",
                        ),
                    ),
                ],
            )
        ],
    )
    out = tmp_path / "out.yml"
    save_critical_paths(cpf, out)
    reloaded = load_critical_paths(str(out))
    loc = reloaded.paths[0].steps[0].locator
    assert loc.role == "button"
    assert loc.name == "Buy"
    assert loc.test_id == "buy-btn"
    assert loc.css == "button.buy"
    assert loc.exact is True


def test_locator_yaml_load_with_fallbacks(tmp_path):
    f = tmp_path / "paths.yml"
    f.write_text(
        "name: test\n"
        "base_url: http://localhost\n"
        "critical_paths:\n"
        "  - name: p\n"
        "    steps:\n"
        "      - action: click\n"
        "        locator:\n"
        "          role: button\n"
        "          name: Add to Cart\n"
        "          test_id: add-cart\n"
        "          css: button.add-to-cart\n"
    )
    cpf = load_critical_paths(str(f))
    loc = cpf.paths[0].steps[0].locator
    assert loc.test_id == "add-cart"
    assert loc.css == "button.add-to-cart"


# ---------------------------------------------------------------------------
# Recorder fallbacks
# ---------------------------------------------------------------------------


def test_events_to_critical_path_with_test_id():
    events = [
        RecordedEvent(
            action="click", target="Buy",
            role="button", name="Buy",
            test_id="buy-btn", css="button.buy",
        ),
    ]
    cp = events_to_critical_path(events)
    loc = cp.steps[0].locator
    assert loc.test_id == "buy-btn"
    assert loc.css == "button.buy"


def test_events_to_critical_path_without_fallbacks():
    events = [
        RecordedEvent(
            action="click", target="OK",
            role="button", name="OK",
        ),
    ]
    cp = events_to_critical_path(events)
    loc = cp.steps[0].locator
    assert loc.test_id == ""
    assert loc.css == ""


def test_events_fill_with_fallbacks():
    events = [
        RecordedEvent(
            action="fill", target="Email",
            role="textbox", name="Email", value="a@b.com",
            test_id="email-input", css="input#email",
        ),
    ]
    cp = events_to_critical_path(events)
    loc = cp.steps[0].locator
    assert loc.test_id == "email-input"
    assert loc.css == "input#email"
    assert cp.steps[0].value == "a@b.com"


def test_events_select_with_fallbacks():
    events = [
        RecordedEvent(
            action="select", target="Country",
            role="combobox", name="Country", value="Mexico",
            test_id="country-sel", css="select.country",
        ),
    ]
    cp = events_to_critical_path(events)
    loc = cp.steps[0].locator
    assert loc.test_id == "country-sel"
    assert loc.css == "select.country"


# ---------------------------------------------------------------------------
# StepResult warning field
# ---------------------------------------------------------------------------


def test_step_result_warning_in_dict():
    sr = StepResult(
        step_num=1, action="click", detail='button("OK")',
        passed=True, duration_ms=100.0,
        warning="Fuzzy match used",
    )
    d = sr.to_dict()
    assert d["warning"] == "Fuzzy match used"


def test_step_result_no_warning_omitted():
    sr = StepResult(
        step_num=1, action="click", detail='button("OK")',
        passed=True, duration_ms=100.0,
    )
    d = sr.to_dict()
    assert "warning" not in d
