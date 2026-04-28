"""Unit tests for ref → locator mapping."""

from unittest.mock import MagicMock

import pytest

from qaprobe.browser import AXElement, RefResolver


def _make_elements():
    return [
        AXElement(ref="btn:submit@form", role="button", name="Submit"),
        AXElement(ref="inp:email@form", role="textbox", name="Email"),
        AXElement(ref="lnk:home@nav", role="link", name="Home"),
        AXElement(ref="btn:cancel@form", role="button", name="Cancel"),
    ]


def test_register_and_lookup():
    resolver = RefResolver()
    elements = _make_elements()
    resolver.register(elements)
    assert "btn:submit@form" in resolver._map
    assert "inp:email@form" in resolver._map
    assert resolver._map["btn:submit@form"].name == "Submit"


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

    result = resolver.resolve(page, "btn:submit@form")

    page.get_by_role.assert_called_once_with("button", name="Submit")
    assert result == mock_locator


def test_resolve_no_name_uses_nth():
    resolver = RefResolver()
    resolver.register([AXElement(ref="btn", role="button", name="")])

    page = MagicMock()
    mock_locator = MagicMock()
    page.get_by_role.return_value.nth.return_value = mock_locator

    resolver.resolve(page, "btn")
    page.get_by_role.assert_called_with("button")


def test_duplicate_name_disambiguation():
    resolver = RefResolver()
    elements = [
        AXElement(ref="btn:ok@dlg#0", role="button", name="OK"),
        AXElement(ref="btn:ok@dlg#1", role="button", name="OK"),
    ]
    resolver.register(elements)

    page = MagicMock()
    locator_chain = MagicMock()
    page.get_by_role.return_value.nth.return_value = locator_chain

    resolver.resolve(page, "btn:ok@dlg#0")
    page.get_by_role.return_value.nth.assert_called_with(0)

    page.reset_mock()
    page.get_by_role.return_value.nth.return_value = locator_chain
    resolver.resolve(page, "btn:ok@dlg#1")
    page.get_by_role.return_value.nth.assert_called_with(1)
