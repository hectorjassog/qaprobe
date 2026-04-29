"""CLI tests for replay, watch, and record --critical-path commands."""

from click.testing import CliRunner

from qaprobe.cli import _parse_interval, main


def test_replay_help():
    runner = CliRunner()
    result = runner.invoke(main, ["replay", "--help"])
    assert result.exit_code == 0
    assert "--auth" in result.output
    assert "--headed" in result.output
    assert "--verify" in result.output
    assert "--json-output" in result.output


def test_watch_help():
    runner = CliRunner()
    result = runner.invoke(main, ["watch", "--help"])
    assert result.exit_code == 0
    assert "--interval" in result.output
    assert "--webhook" in result.output
    assert "--max-runs" in result.output
    assert "--verify" in result.output


def test_record_help_shows_critical_path():
    runner = CliRunner()
    result = runner.invoke(main, ["record", "--help"])
    assert result.exit_code == 0
    assert "--critical-path" in result.output
    assert "--save-to" in result.output
    assert "--name" in result.output


def test_help_shows_new_commands():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "replay" in result.output
    assert "watch" in result.output


def test_replay_requires_existing_file():
    runner = CliRunner()
    result = runner.invoke(main, ["replay", "nonexistent.yml"])
    assert result.exit_code != 0


def test_watch_requires_existing_file():
    runner = CliRunner()
    result = runner.invoke(main, ["watch", "nonexistent.yml"])
    assert result.exit_code != 0


def test_parse_interval_seconds():
    assert _parse_interval("30s") == 30


def test_parse_interval_minutes():
    assert _parse_interval("5m") == 300


def test_parse_interval_hours():
    assert _parse_interval("1h") == 3600


def test_parse_interval_plain_number():
    assert _parse_interval("60") == 60


def test_parse_interval_whitespace():
    assert _parse_interval("  10s  ") == 10
