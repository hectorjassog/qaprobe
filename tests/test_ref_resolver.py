"""Unit tests for ref → locator mapping."""

from unittest.mock import MagicMock

import pytest

from qaprobe.browser import AXElement, RefResolver


def _make_elements():
    return [
        AXElement(ref="btn:0", role="button", name="Submit"),
        AXElement(ref="inp:0", role="textbox", name="Email"),
        AXElement(ref="lnk:0", role="link", name="Home"),
        AXElement(ref="btn:1", role="button", name="Cancel"),
    ]


def test_register_and_lookup():
    resolver = RefResolver()
    elements = _make_elements()
    resolver.register(elements)
    # Check internal state
    assert "btn:0" in resolver._map
    assert "inp:0" in resolver._map
    assert resolver._map["btn:0"].name == "Submit"


def test_unknown_ref_raises():
    resolver = RefResolver()
    resolver.register(_make_elements())
    page = MagicMock()
    with pytest.raises(ValueError, match="Unknown ref"):
        resolver.resolve(page, "xyz:99")


def test_resolve_calls_get_by_role():
    resolver = RefResolver()
    resolver.register(_make_elements())

    page = MagicMock()
    mock_locator = MagicMock()
    page.get_by_role.return_value.nth.return_value = mock_locator

    result = resolver.resolve(page, "btn:0")

    page.get_by_role.assert_called_once_with("button", name="Submit")
    assert result == mock_locator


def test_resolve_no_name_uses_nth():
    resolver = RefResolver()
    resolver.register([AXElement(ref="btn:0", role="button", name="")])

    page = MagicMock()
    mock_locator = MagicMock()
    page.get_by_role.return_value.nth.return_value = mock_locator

    resolver.resolve(page, "btn:0")
    page.get_by_role.assert_called_with("button")
