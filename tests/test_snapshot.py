"""Unit tests for AX tree → element list (Snapshot) parsing."""

from qaprobe.browser import parse_ax_tree


def _node(role, name="", value="", properties=None):
    return {
        "role": {"value": role},
        "name": {"value": name},
        "description": {"value": ""},
        "value": {"value": value},
        "properties": properties or [],
    }


def test_parse_empty():
    snap = parse_ax_tree([])
    assert snap.elements == []


def test_parse_button():
    nodes = [_node("button", "Submit")]
    snap = parse_ax_tree(nodes)
    assert len(snap.elements) == 1
    el = snap.elements[0]
    assert el.role == "button"
    assert el.name == "Submit"
    assert el.ref == "btn:0"


def test_parse_multiple_roles():
    nodes = [
        _node("button", "OK"),
        _node("textbox", "Email"),
        _node("link", "Home"),
    ]
    snap = parse_ax_tree(nodes)
    assert len(snap.elements) == 3
    refs = [el.ref for el in snap.elements]
    assert "btn:0" in refs
    assert "inp:0" in refs
    assert "lnk:0" in refs


def test_parse_filters_hidden():
    nodes = [
        _node("button", "Visible"),
        {
            "role": {"value": "button"},
            "name": {"value": "Hidden"},
            "description": {"value": ""},
            "value": {"value": ""},
            "properties": [{"name": "hidden", "value": {"value": True}}],
        },
    ]
    snap = parse_ax_tree(nodes)
    assert len(snap.elements) == 1
    assert snap.elements[0].name == "Visible"


def test_parse_filters_none_role():
    nodes = [
        _node("none"),
        _node("presentation"),
        _node("button", "Real"),
    ]
    snap = parse_ax_tree(nodes)
    assert len(snap.elements) == 1


def test_parse_heading_level():
    nodes = [
        {
            "role": {"value": "heading"},
            "name": {"value": "Welcome"},
            "description": {"value": ""},
            "value": {"value": ""},
            "properties": [{"name": "level", "value": {"value": 2}}],
        }
    ]
    snap = parse_ax_tree(nodes)
    assert snap.elements[0].level == 2


def test_compact_output():
    nodes = [_node("button", "Submit")]
    snap = parse_ax_tree(nodes)
    text = snap.compact()
    assert "[btn:0]" in text
    assert "Submit" in text


def test_compact_truncation():
    nodes = [_node("button", f"Button {i}") for i in range(300)]
    snap = parse_ax_tree(nodes)
    text = snap.compact(max_elements=200)
    assert "100 more elements" in text
