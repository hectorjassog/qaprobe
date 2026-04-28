"""Unit tests for origin pinning."""

import pytest

from qaprobe.agent import check_origin


def test_same_origin_allowed():
    check_origin("https://example.com/page", ["https://example.com"])


def test_different_origin_blocked():
    with pytest.raises(ValueError, match="blocked"):
        check_origin("https://evil.com/steal", ["https://example.com"])


def test_multiple_allowed_origins():
    check_origin("https://api.example.com/data", [
        "https://example.com",
        "https://api.example.com",
    ])


def test_port_matters():
    with pytest.raises(ValueError, match="blocked"):
        check_origin("http://localhost:4000/page", ["http://localhost:3000"])


def test_empty_allowed_origins_permits_all():
    check_origin("https://anything.com/page", [])


def test_path_ignored_in_comparison():
    check_origin("https://example.com/deep/path?q=1", ["https://example.com/other"])
