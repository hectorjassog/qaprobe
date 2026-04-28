"""Unit tests for stable deterministic ref generation."""

from qaprobe.browser import parse_ax_tree


def _node(role, name="", node_id="", parent_id=None, properties=None):
    n = {
        "nodeId": node_id,
        "role": {"value": role},
        "name": {"value": name},
        "description": {"value": ""},
        "value": {"value": ""},
        "properties": properties or [],
    }
    if parent_id:
        n["parentId"] = parent_id
    return n


def test_refs_include_name():
    nodes = [_node("button", "Submit", "1")]
    snap = parse_ax_tree(nodes)
    assert "submit" in snap.elements[0].ref.lower()


def test_refs_include_parent_context():
    nodes = [
        _node("form", "Login", "1"),
        _node("textbox", "Email", "2", parent_id="1"),
    ]
    snap = parse_ax_tree(nodes)
    email_el = [e for e in snap.elements if e.name == "Email"][0]
    assert "@form" in email_el.ref


def test_duplicate_names_get_counter():
    nodes = [
        _node("form", "Edit", "1"),
        _node("button", "Save", "2", parent_id="1"),
        _node("button", "Save", "3", parent_id="1"),
    ]
    snap = parse_ax_tree(nodes)
    save_elements = [e for e in snap.elements if e.name == "Save"]
    assert len(save_elements) == 2
    assert save_elements[0].ref != save_elements[1].ref


def test_refs_deterministic_across_calls():
    nodes = [
        _node("button", "OK", "1"),
        _node("textbox", "Name", "2"),
    ]
    snap1 = parse_ax_tree(nodes)
    snap2 = parse_ax_tree(nodes)
    assert snap1.elements[0].ref == snap2.elements[0].ref
    assert snap1.elements[1].ref == snap2.elements[1].ref


def test_anonymous_elements():
    nodes = [
        _node("button", "", "1"),
        _node("button", "", "2"),
        _node("button", "", "3"),
    ]
    snap = parse_ax_tree(nodes)
    refs = [e.ref for e in snap.elements]
    assert len(set(refs)) == 3
