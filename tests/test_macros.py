"""Unit tests for story macro expansion."""

from qaprobe.suite import expand_macros


def test_simple_macro():
    macros = {"greet": "Hello {{1}}"}
    assert expand_macros("{{greet(World)}}", macros) == "Hello World"


def test_multiple_args():
    macros = {"login_as": "Go to /login, fill {{1}} in username, fill {{2}} in password"}
    result = expand_macros("{{login_as(admin, secret123)}}", macros)
    assert "admin" in result
    assert "secret123" in result


def test_unknown_macro_left_as_is():
    macros = {"greet": "Hello {{1}}"}
    text = "{{unknown(arg)}}"
    assert expand_macros(text, macros) == text


def test_no_macros_passthrough():
    assert expand_macros("plain text", {}) == "plain text"


def test_macro_in_context():
    macros = {"auth": "Log in as {{1}}"}
    text = "First {{auth(admin)}} then check the dashboard"
    result = expand_macros(text, macros)
    assert result == "First Log in as admin then check the dashboard"


def test_quoted_args():
    macros = {"greet": "Hello {{1}}"}
    assert expand_macros('{{greet("World")}}', macros) == "Hello World"
