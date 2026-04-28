"""Unit tests for AX tree → element list (Snapshot) parsing."""

from qaprobe.browser import parse_ax_tree


def _node(role, name="", value="", properties=None, node_id="", parent_id=None):
    n = {
        "role": {"value": role},
        "name": {"value": name},
        "description": {"value": ""},
        "value": {"value": value},
        "properties": properties or [],
    }
    if node_id:
        n["nodeId"] = node_id
    if parent_id:
        n["parentId"] = parent_id
    return n


def test_parse_empty():
    snap = parse_ax_tree([])
    assert snap.elements == []


def test_parse_button():
    nodes = [_node("button", "Submit", node_id="1")]
    snap = parse_ax_tree(nodes)
    assert len(snap.elements) == 1
    el = snap.elements[0]
    assert el.role == "button"
    assert el.name == "Submit"
    assert "btn:" in el.ref
    assert "submit" in el.ref


def test_parse_multiple_roles():
    nodes = [
        _node("button", "OK", node_id="1"),
        _node("textbox", "Email", node_id="2"),
        _node("link", "Home", node_id="3"),
    ]
    snap = parse_ax_tree(nodes)
    assert len(snap.elements) == 3
    roles = {el.role for el in snap.elements}
    assert "button" in roles
    assert "textbox" in roles
    assert "link" in roles


def test_parse_filters_hidden():
    nodes = [
        _node("button", "Visible", node_id="1"),
        {
            "nodeId": "2",
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
        _node("none", node_id="1"),
        _node("presentation", node_id="2"),
        _node("button", "Real", node_id="3"),
    ]
    snap = parse_ax_tree(nodes)
    assert len(snap.elements) == 1


def test_parse_heading_level():
    nodes = [
        {
            "nodeId": "1",
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
    nodes = [_node("button", "Submit", node_id="1")]
    snap = parse_ax_tree(nodes)
    text = snap.compact()
    assert "btn:" in text
    assert "Submit" in text


def test_compact_truncation():
    nodes = [_node("button", f"Button {i}", node_id=str(i)) for i in range(300)]
    snap = parse_ax_tree(nodes)
    text = snap.compact(max_elements=200)
    assert "100 more elements" in text


def test_stable_refs_with_parent():
    nodes = [
        _node("form", "Login", node_id="1"),
        _node("textbox", "Email", node_id="2", parent_id="1"),
        _node("button", "Submit", node_id="3", parent_id="1"),
    ]
    snap = parse_ax_tree(nodes)
    refs = {el.ref for el in snap.elements}
    assert len(refs) == 3
    email_el = [el for el in snap.elements if el.name == "Email"][0]
    assert "@form" in email_el.ref


def test_anonymous_elements_get_counter():
    nodes = [
        _node("button", "", node_id="1"),
        _node("button", "", node_id="2"),
    ]
    snap = parse_ax_tree(nodes)
    assert len(snap.elements) == 2
    assert snap.elements[0].ref != snap.elements[1].ref
