from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .config import ANTHROPIC_API_KEY, MAX_STEPS, RUNS_DIR

console = Console()


def _check_api_key() -> None:
    if not ANTHROPIC_API_KEY:
        console.print("[red]Error: ANTHROPIC_API_KEY environment variable is not set.[/red]")
        sys.exit(1)


@click.group()
@click.version_option(__version__, prog_name="qaprobe")
def main() -> None:
    """QAProbe — Agentic QA for web apps."""


@main.command()
@click.option("--url", required=True, help="URL of the web app to test")
@click.option("--story", required=True, help="Plain-English user story to verify")
@click.option("--auth", default=None, help="Path to Playwright storage state for authentication")
@click.option("--max-steps", default=MAX_STEPS, show_default=True, help="Maximum agent steps")
@click.option("--headed", is_flag=True, default=False, help="Run browser in headed mode")
@click.option(
    "--runs-dir", default=RUNS_DIR, show_default=True, help="Directory to save run artifacts"
)
def run(
    url: str,
    story: str,
    auth: str | None,
    max_steps: int,
    headed: bool,
    runs_dir: str,
) -> None:
    """Run a QA probe against a URL with a user story."""
    _check_api_key()
    asyncio.run(_run_async(url, story, auth, max_steps, not headed, runs_dir))


async def _run_async(
    url: str,
    story: str,
    auth: str | None,
    max_steps: int,
    headless: bool,
    runs_dir: str,
) -> None:
    from .a11y import audit_snapshot
    from .agent import run_agent
    from .browser import BrowserSession
    from .report import build_html_report, build_report, reconcile_verdict, save_report
    from .verifier import run_verifier

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(runs_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        Panel(
            f"[bold]URL:[/bold] {url}\n[bold]Story:[/bold] {story}",
            title="[blue]QAProbe Run[/blue]",
            subtitle=f"Run ID: {run_id}",
        )
    )

    session = BrowserSession(headless=headless, timeout_ms=30000)
    started_at = datetime.now(UTC)

    try:
        page = await session.start(str(run_dir / "video"), storage_state=auth)

        console.print("[dim]Running agent...[/dim]")
        agent_result = await run_agent(page, session, story, url, max_steps=max_steps)

        console.print("[dim]Running verifier...[/dim]")
        verifier_result = await run_verifier(story, agent_result)

        # Audit last snapshot for a11y
        final_snap = await session.snapshot()
        a11y_findings = audit_snapshot(final_snap)

        finished_at = datetime.now(UTC)

        # Save trace
        trace_path = run_dir / "trace.zip"
        await session.save_trace(str(trace_path))

        # Build and save report
        artifacts = {"trace": str(trace_path)}

        # Find video file
        video_dir = run_dir / "video"
        if video_dir.exists():
            videos = list(video_dir.glob("*.webm"))
            if videos:
                artifacts["video"] = str(videos[0])

        verdict = reconcile_verdict(agent_result, verifier_result)
        report = build_report(
            run_id=run_id,
            url=url,
            story=story,
            started_at=started_at,
            finished_at=finished_at,
            agent_result=agent_result,
            verifier_result=verifier_result,
            a11y_findings=a11y_findings,
            artifacts=artifacts,
        )

        report_json_path = run_dir / "report.json"
        save_report(report, report_json_path)

        html_report = build_html_report(report)
        (run_dir / "report.html").write_text(html_report)

    finally:
        await session.close()

    # Display result
    verdict_colors = {"pass": "green", "fail": "red", "inconclusive": "yellow"}
    color = verdict_colors.get(verdict, "white")

    console.print()
    console.print(
        Panel(
            f"[bold {color}]{verdict.upper()}[/bold {color}]\n\n"
            f"[bold]Agent:[/bold] {agent_result.verdict} — {agent_result.reasoning}\n\n"
            f"[bold]Verifier:[/bold] {'✓' if verifier_result.goal_achieved else '✗'} "
            f"(confidence: {verifier_result.confidence}) — {verifier_result.reasoning}\n\n"
            f"[bold]A11y findings:[/bold] {len(a11y_findings)}\n"
            f"[bold]Report:[/bold] {run_dir / 'report.html'}",
            title=f"[{color}]QAProbe Result[/{color}]",
        )
    )

    if verdict != "pass":
        sys.exit(1)


@main.command()
@click.option("--url", required=True, help="URL of the login page")
@click.option(
    "--save", default=".auth/state.json", show_default=True, help="Path to save storage state"
)
def login(url: str, save: str) -> None:
    """Log in manually and save browser storage state for reuse."""
    asyncio.run(_login_async(url, save))


async def _login_async(url: str, save: str) -> None:
    from .auth import save_storage_state

    await save_storage_state(url, save)


@main.command("suite")
@click.argument("suite_file", type=click.Path(exists=True))
@click.option("--auth", default=None, help="Path to storage state (overrides suite auth config)")
@click.option(
    "--runs-dir", default=RUNS_DIR, show_default=True, help="Directory to save run artifacts"
)
@click.option("--headed", is_flag=True, default=False, help="Run browser in headed mode")
def suite_cmd(
    suite_file: str,
    auth: str | None,
    runs_dir: str,
    headed: bool,
) -> None:
    """Run a YAML suite of user stories."""
    _check_api_key()
    asyncio.run(_suite_async(suite_file, auth, runs_dir, not headed))


async def _suite_async(
    suite_file: str,
    auth: str | None,
    runs_dir: str,
    headless: bool,
) -> None:
    from .a11y import audit_snapshot
    from .agent import run_agent
    from .browser import BrowserSession
    from .report import build_html_report, build_report, save_report
    from .suite import load_suite, resolve_order
    from .verifier import run_verifier

    suite = load_suite(suite_file)
    stories = resolve_order(suite.stories)
    storage_state = auth or suite.auth_storage_state

    suite_run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suite_dir = Path(runs_dir) / f"suite-{suite_run_id}"
    suite_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        Panel(
            f"[bold]Suite:[/bold] {suite.name}\n"
            f"[bold]Base URL:[/bold] {suite.base_url}\n"
            f"[bold]Stories:[/bold] {len(stories)}",
            title="[blue]QAProbe Suite[/blue]",
        )
    )

    results = []
    any_fail = False

    for story_def in stories:
        url = suite.base_url.rstrip("/") + story_def.path
        console.print(f"\n[bold]→ {story_def.name}[/bold]: {story_def.story[:60]}...")

        story_dir = suite_dir / story_def.name
        story_dir.mkdir(parents=True, exist_ok=True)

        session = BrowserSession(headless=headless)
        started_at = datetime.now(UTC)
        verdict = "fail"

        try:
            page = await session.start(str(story_dir / "video"), storage_state=storage_state)
            agent_result = await run_agent(page, session, story_def.story, url)
            verifier_result = await run_verifier(story_def.story, agent_result)
            final_snap = await session.snapshot()
            a11y_findings = audit_snapshot(final_snap)
            finished_at = datetime.now(UTC)
            trace_path = story_dir / "trace.zip"
            await session.save_trace(str(trace_path))
            artifacts: dict[str, str] = {"trace": str(trace_path)}
            videos = (
                list((story_dir / "video").glob("*.webm"))
                if (story_dir / "video").exists()
                else []
            )
            if videos:
                artifacts["video"] = str(videos[0])
            run_id = f"{suite_run_id}-{story_def.name}"
            report = build_report(
                run_id=run_id,
                url=url,
                story=story_def.story,
                started_at=started_at,
                finished_at=finished_at,
                agent_result=agent_result,
                verifier_result=verifier_result,
                a11y_findings=a11y_findings,
                artifacts=artifacts,
            )
            save_report(report, story_dir / "report.json")
            (story_dir / "report.html").write_text(build_html_report(report))
            verdict = report.verdict
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            finished_at = datetime.now(UTC)
        finally:
            await session.close()

        if verdict != "pass":
            any_fail = True

        color = {"pass": "green", "fail": "red", "inconclusive": "yellow"}.get(verdict, "white")
        console.print(f"  [{color}]{verdict.upper()}[/{color}]")
        results.append({"name": story_def.name, "verdict": verdict})

    # Print summary
    console.print("\n[bold]Suite Summary:[/bold]")
    for r in results:
        color = {"pass": "green", "fail": "red", "inconclusive": "yellow"}.get(
            r["verdict"], "white"
        )
        console.print(f"  [{color}]●[/{color}] {r['name']}: {r['verdict']}")

    if any_fail:
        sys.exit(1)
