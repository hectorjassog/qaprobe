"""Tests for the enhanced recorder critical-path mode."""

from qaprobe.recorder import RecordedEvent, events_to_critical_path


def test_events_to_critical_path_navigate():
    events = [RecordedEvent(action="navigate", url="https://example.com")]
    cp = events_to_critical_path(events, name="test")
    assert cp.name == "test"
    assert len(cp.steps) == 1
    assert cp.steps[0].action == "navigate"
    assert cp.steps[0].url == "https://example.com"


def test_events_to_critical_path_click():
    events = [
        RecordedEvent(action="click", target="Submit", role="button", name="Submit"),
    ]
    cp = events_to_critical_path(events)
    assert len(cp.steps) == 1
    assert cp.steps[0].action == "click"
    assert cp.steps[0].locator is not None
    assert cp.steps[0].locator.role == "button"
    assert cp.steps[0].locator.name == "Submit"


def test_events_to_critical_path_fill():
    events = [
        RecordedEvent(action="fill", target="Email", value="a@b.com", role="textbox", name="Email"),
    ]
    cp = events_to_critical_path(events)
    assert cp.steps[0].action == "fill"
    assert cp.steps[0].locator.role == "textbox"
    assert cp.steps[0].value == "a@b.com"


def test_events_to_critical_path_select():
    events = [
        RecordedEvent(
            action="select", target="Country", value="Mexico",
            role="combobox", name="Country",
        ),
    ]
    cp = events_to_critical_path(events)
    assert cp.steps[0].action == "select"
    assert cp.steps[0].locator.role == "combobox"
    assert cp.steps[0].value == "Mexico"


def test_events_to_critical_path_press_key():
    events = [RecordedEvent(action="press_key", value="Enter")]
    cp = events_to_critical_path(events)
    assert cp.steps[0].action == "press_key"
    assert cp.steps[0].key == "Enter"


def test_events_to_critical_path_skips_no_role_click():
    events = [
        RecordedEvent(action="click", target="something", role="", name=""),
    ]
    cp = events_to_critical_path(events)
    assert len(cp.steps) == 0


def test_events_to_critical_path_full_flow():
    events = [
        RecordedEvent(action="navigate", url="https://example.com/login"),
        RecordedEvent(
            action="fill", target="Username", value="admin",
            role="textbox", name="Username",
        ),
        RecordedEvent(
            action="fill", target="Password", value="secret",
            role="textbox", name="Password",
        ),
        RecordedEvent(action="click", target="Sign In", role="button", name="Sign In"),
        RecordedEvent(action="navigate", url="https://example.com/dashboard"),
    ]
    cp = events_to_critical_path(events, name="login_flow")

    assert cp.name == "login_flow"
    assert len(cp.steps) == 5
    actions = [s.action for s in cp.steps]
    assert actions == ["navigate", "fill", "fill", "click", "navigate"]


def test_events_to_critical_path_default_name():
    events = [RecordedEvent(action="navigate", url="/")]
    cp = events_to_critical_path(events)
    assert cp.name == "recorded_path"
