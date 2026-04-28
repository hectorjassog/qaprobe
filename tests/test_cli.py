"""CLI smoke tests."""

from click.testing import CliRunner

from qaprobe.cli import main


def test_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.2.0" in result.output


def test_run_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("QAPROBE_PROVIDER", "anthropic")
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--url", "http://example.com", "--story", "Test"])
    assert result.exit_code == 1


def test_suite_requires_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("QAPROBE_PROVIDER", "anthropic")
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
    assert "a11y" in result.output
    assert "init" in result.output
    assert "record" in result.output
    assert "install" in result.output


def test_run_help():
    runner = CliRunner()
    result = runner.invoke(main, ["run", "--help"])
    assert result.exit_code == 0
    assert "--url" in result.output
    assert "--story" in result.output
    assert "--reveal-secrets" in result.output
    assert "--no-routing" in result.output


def test_suite_help():
    runner = CliRunner()
    result = runner.invoke(main, ["suite", "--help"])
    assert result.exit_code == 0
    assert "--baseline" in result.output
    assert "--reveal-secrets" in result.output


def test_a11y_help():
    runner = CliRunner()
    result = runner.invoke(main, ["a11y", "--help"])
    assert result.exit_code == 0
    assert "--url" in result.output
    assert "--html" in result.output


def test_init_creates_scaffold(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0
    assert (tmp_path / "probes" / "example.yml").exists()
    assert (tmp_path / ".auth" / ".gitkeep").exists()
