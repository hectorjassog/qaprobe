"""CLI smoke tests."""

from click.testing import CliRunner

from qaprobe.cli import main


def test_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_run_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--url", "http://example.com", "--story", "Test"])
    assert result.exit_code == 1


def test_suite_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    suite_file = tmp_path / "suite.yml"
    suite_file.write_text(
        "base_url: http://example.com\nstories:\n  - name: test\n    story: Test\n"
    )
    runner = CliRunner()
    result = runner.invoke(main, ["suite", str(suite_file)])
    assert result.exit_code == 1


def test_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "login" in result.output
    assert "suite" in result.output


def test_run_help():
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--url" in result.output
    assert "--story" in result.output
