from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .config import ANTHROPIC_API_KEY, MAX_STEPS, OPENAI_API_KEY, PROVIDER, RUNS_DIR

console = Console()


def _check_api_key() -> None:
    if PROVIDER == "openai":
        if not OPENAI_API_KEY:
            console.print("[red]Error: OPENAI_API_KEY environment variable is not set.[/red]")
            sys.exit(1)
    else:
        if not ANTHROPIC_API_KEY:
            console.print("[red]Error: ANTHROPIC_API_KEY environment variable is not set.[/red]")
            sys.exit(1)


@click.group()
@click.version_option(__version__, prog_name="qaprobe")
def main() -> None:
    """QAProbe — Agentic QA for web apps."""


# --- run command ---


@main.command()
@click.option("--url", required=True, help="URL of the web app to test")
@click.option("--story", required=True, help="Plain-English user story to verify")
@click.option("--auth", default=None, help="Path to Playwright storage state for authentication")
@click.option("--max-steps", default=MAX_STEPS, show_default=True, help="Maximum agent steps")
@click.option("--headed", is_flag=True, default=False, help="Run browser in headed mode")
@click.option(
    "--runs-dir", default=RUNS_DIR, show_default=True, help="Directory to save run artifacts"
)
@click.option("--reveal-secrets", is_flag=True, default=False, help="Show fill values in reports")
@click.option("--no-routing", is_flag=True, default=False, help="Disable model routing")
def run(
    url: str,
    story: str,
    auth: str | None,
    max_steps: int,
    headed: bool,
    runs_dir: str,
    reveal_secrets: bool,
    no_routing: bool,
) -> None:
    """Run a QA probe against a URL with a user story."""
    _check_api_key()
    asyncio.run(
        _run_async(url, story, auth, max_steps, not headed, runs_dir, reveal_secrets, not no_routing)
    )


async def _run_async(
    url: str,
    story: str,
    auth: str | None,
    max_steps: int,
    headless: bool,
    runs_dir: str,
    reveal_secrets: bool = False,
    model_routing: bool = True,
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
        agent_result = await run_agent(
            page,
            session,
            story,
            url,
            max_steps=max_steps,
            model_routing=model_routing,
        )

        console.print("[dim]Taking screenshot...[/dim]")
        screenshot_b64 = await session.screenshot()

        console.print("[dim]Running verifier...[/dim]")
        verifier_result = await run_verifier(story, agent_result, screenshot_b64=screenshot_b64)

        final_snap = await session.snapshot()
        a11y_findings = audit_snapshot(final_snap)

        finished_at = datetime.now(UTC)

        trace_path = run_dir / "trace.zip"
        await session.save_trace(str(trace_path))

        artifacts = {"trace": str(trace_path)}

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
            reveal_secrets=reveal_secrets,
        )

        report_json_path = run_dir / "report.json"
        save_report(report, report_json_path)

        html_report = build_html_report(report)
        (run_dir / "report.html").write_text(html_report, encoding="utf-8")

    finally:
        await session.close()

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


# --- login command ---


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


# --- suite command ---


@main.command("suite")
@click.argument("suite_file", type=click.Path(exists=True))
@click.option("--auth", default=None, help="Path to storage state (overrides suite auth config)")
@click.option(
    "--runs-dir", default=RUNS_DIR, show_default=True, help="Directory to save run artifacts"
)
@click.option("--headed", is_flag=True, default=False, help="Run browser in headed mode")
@click.option("--baseline", is_flag=True, default=False, help="Save results as the new baseline")
@click.option("--reveal-secrets", is_flag=True, default=False, help="Show fill values in reports")
@click.option("--no-routing", is_flag=True, default=False, help="Disable model routing")
def suite_cmd(
    suite_file: str,
    auth: str | None,
    runs_dir: str,
    headed: bool,
    baseline: bool,
    reveal_secrets: bool,
    no_routing: bool,
) -> None:
    """Run a YAML suite of user stories."""
    _check_api_key()
    asyncio.run(
        _suite_async(suite_file, auth, runs_dir, not headed, baseline, reveal_secrets, not no_routing)
    )


async def _suite_async(
    suite_file: str,
    auth: str | None,
    runs_dir: str,
    headless: bool,
    save_baseline: bool = False,
    reveal_secrets: bool = False,
    model_routing: bool = True,
) -> None:
    from .a11y import audit_snapshot
    from .agent import run_agent
    from .browser import BrowserSession
    from .report import (
        RunReport,
        build_html_report,
        build_report,
        build_suite_html_report,
        save_report,
    )
    from .suite import (
        check_regressions,
        load_baseline,
        load_suite,
        resolve_order,
    )
    from .suite import (
        save_baseline as save_baseline_fn,
    )
    from .verifier import run_verifier

    suite = load_suite(suite_file)
    stories = resolve_order(suite.stories)
    storage_state = auth or suite.auth_storage_state

    allowed_origins = suite.allowed_origins or [suite.base_url]

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

    results: list[dict] = []
    reports: list[RunReport] = []
    story_dirs: dict[str, str] = {}

    for story_def in stories:
        url = suite.base_url.rstrip("/") + story_def.path
        console.print(f"\n[bold]→ {story_def.name}[/bold]: {story_def.story[:60]}...")

        story_dir = suite_dir / story_def.name
        story_dir.mkdir(parents=True, exist_ok=True)
        story_dirs[story_def.name] = story_def.name

        session = BrowserSession(headless=headless)
        started_at = datetime.now(UTC)
        verdict = "fail"

        try:
            page = await session.start(str(story_dir / "video"), storage_state=storage_state)
            agent_result = await run_agent(
                page,
                session,
                story_def.story,
                url,
                allowed_origins=allowed_origins,
                model_routing=model_routing,
            )
            screenshot_b64 = await session.screenshot()
            verifier_result = await run_verifier(
                story_def.story, agent_result, screenshot_b64=screenshot_b64
            )
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
                reveal_fields=suite.reveal_fields,
                reveal_secrets=reveal_secrets,
            )
            save_report(report, story_dir / "report.json")
            (story_dir / "report.html").write_text(build_html_report(report), encoding="utf-8")
            verdict = report.verdict
            reports.append(report)
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            finished_at = datetime.now(UTC)
        finally:
            await session.close()

        color = {"pass": "green", "fail": "red", "inconclusive": "yellow"}.get(verdict, "white")
        console.print(f"  [{color}]{verdict.upper()}[/{color}]")
        results.append({"name": story_def.name, "verdict": verdict})

    # Write suite-level HTML report
    if reports:
        suite_html = build_suite_html_report(suite.name, suite_run_id, reports, story_dirs)
        (suite_dir / "index.html").write_text(suite_html)
        console.print(f"\n[bold]Suite report:[/bold] {suite_dir / 'index.html'}")

    # Build verdict map
    verdict_map = {r["name"]: r["verdict"] for r in results}

    # Baseline handling
    if save_baseline:
        save_baseline_fn(verdict_map)
        console.print("[dim]Baseline saved to .qaprobe/baseline.json[/dim]")

    # Print summary
    console.print("\n[bold]Suite Summary:[/bold]")
    for r in results:
        color = {"pass": "green", "fail": "red", "inconclusive": "yellow"}.get(
            r["verdict"], "white"
        )
        console.print(f"  [{color}]●[/{color}] {r['name']}: {r['verdict']}")

    # Check regressions against baseline
    existing_baseline = load_baseline()
    if existing_baseline and not save_baseline:
        regressions = check_regressions(verdict_map, existing_baseline)
        if regressions:
            console.print("\n[red bold]Regressions detected:[/red bold]")
            for name in regressions:
                console.print(f"  [red]✗[/red] {name}: was pass, now {verdict_map[name]}")
            sys.exit(1)
        else:
            non_pass = [r for r in results if r["verdict"] != "pass"]
            if non_pass:
                console.print(
                    f"\n[yellow]{len(non_pass)} non-passing stories "
                    f"(not regressions from baseline)[/yellow]"
                )
            return

    any_fail = any(r["verdict"] != "pass" for r in results)
    if any_fail:
        sys.exit(1)


# --- a11y command ---


@main.command("a11y")
@click.option("--url", required=True, help="URL to audit for accessibility")
@click.option("--html", "output_html", is_flag=True, default=False, help="Output HTML report")
@click.option("--auth", default=None, help="Path to Playwright storage state for authentication")
def a11y_cmd(url: str, output_html: bool, auth: str | None) -> None:
    """Run a standalone accessibility audit (no user story needed)."""
    asyncio.run(_a11y_async(url, output_html, auth))


async def _a11y_async(url: str, output_html: bool, auth: str | None) -> None:
    import tempfile

    from .a11y import audit_snapshot
    from .browser import BrowserSession

    session = BrowserSession(headless=True)
    try:
        page = await session.start(tempfile.mkdtemp(prefix="qaprobe-a11y-"), storage_state=auth)
        await page.goto(url, wait_until="domcontentloaded")
        await session.wait_for_stable()
        snap = await session.snapshot()
        findings = audit_snapshot(snap)
    finally:
        await session.close()

    if output_html:

        html_parts = ['<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">']
        html_parts.append(f"<title>QAProbe A11y Audit — {url}</title>")
        html_parts.append("<style>body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}")
        html_parts.append(".finding{padding:.5rem;margin:.25rem 0;border-left:3px solid #f59e0b;background:#fffbeb}")
        html_parts.append(".error-finding{border-color:#ef4444;background:#fef2f2}")
        html_parts.append("</style></head><body>")
        html_parts.append(f"<h1>Accessibility Audit: {url}</h1>")
        html_parts.append(f"<p>{len(findings)} finding(s)</p>")
        for f in findings:
            css = "error-finding" if f.severity == "error" else "finding"
            html_parts.append(
                f'<div class="{css}"><strong>{f.type}</strong>: {f.message} '
                f"<em>[{f.element_ref} {f.element_role}]</em></div>"
            )
        html_parts.append("</body></html>")
        click.echo("\n".join(html_parts))
    else:
        output = [
            {
                "type": f.type,
                "severity": f.severity,
                "ref": f.element_ref,
                "role": f.element_role,
                "name": f.element_name,
                "message": f.message,
            }
            for f in findings
        ]
        click.echo(json.dumps(output, indent=2))

    if any(f.severity == "error" for f in findings):
        sys.exit(1)


# --- init command ---


@main.command()
def init() -> None:
    """Scaffold a probes/ directory with a sample suite YAML."""
    probes_dir = Path("probes")
    probes_dir.mkdir(exist_ok=True)

    auth_dir = Path(".auth")
    auth_dir.mkdir(exist_ok=True)
    gitkeep = auth_dir / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()

    sample = probes_dir / "example.yml"
    if sample.exists():
        console.print(f"[yellow]{sample} already exists, skipping[/yellow]")
    else:
        sample.write_text(
            "# QAProbe suite — edit base_url and stories for your app\n"
            "name: my-app\n"
            "base_url: http://localhost:3000\n"
            "\n"
            "# auth:\n"
            "#   storage_state: .auth/state.json\n"
            "\n"
            "# allowed_origins:\n"
            "#   - http://localhost:3000\n"
            "\n"
            "# macros:\n"
            '#   login_as: "Go to /login, fill {{1}} in username, fill {{2}} in password, click Login"\n'
            "\n"
            "stories:\n"
            "  - name: homepage_loads\n"
            "    path: /\n"
            '    story: "Navigate to the homepage and verify the main heading is visible"\n'
            "\n"
            "  - name: navigation_works\n"
            "    path: /\n"
            '    story: "Click the first navigation link and verify the page changes"\n'
            "    depends_on: homepage_loads\n"
        )
        console.print(f"[green]Created {sample}[/green]")

    console.print(
        "\n[bold]Next steps:[/bold]\n"
        "  1. Edit probes/example.yml with your app's URL and stories\n"
        "  2. Run: qaprobe suite probes/example.yml\n"
        "  3. For authenticated tests: qaprobe login --url <login-page>\n"
    )


# --- record command ---


@main.command()
@click.option("--url", required=True, help="URL to start recording from")
@click.option("--append-to", default=None, help="Append generated story to a suite YAML file")
@click.option(
    "--critical-path", "critical_path", is_flag=True, default=False,
    help="Record as a deterministic critical path (role-based locators) instead of a story",
)
@click.option("--save-to", default=None, help="Save critical path to a YAML file")
@click.option("--name", "path_name", default=None, help="Name for the critical path")
def record(
    url: str,
    append_to: str | None,
    critical_path: bool,
    save_to: str | None,
    path_name: str | None,
) -> None:
    """Record browser interactions and generate a user story or critical path."""
    if not critical_path:
        _check_api_key()
    asyncio.run(_record_async(url, append_to, critical_path, save_to, path_name))


async def _record_async(
    url: str,
    append_to: str | None,
    critical_path: bool = False,
    save_to: str | None = None,
    path_name: str | None = None,
) -> None:
    from .recorder import generate_story, record_session

    events = await record_session(url, critical_path=critical_path)
    if len(events) <= 1:
        console.print("[yellow]No interactions recorded.[/yellow]")
        return

    if critical_path:
        from .critical_path import CriticalPathFile, save_critical_paths
        from .recorder import events_to_critical_path

        name = path_name or f"recorded_{datetime.now(UTC).strftime('%H%M%S')}"
        cp = events_to_critical_path(events, name=name)

        console.print(f"\n[bold]Recorded critical path:[/bold] {cp.name}")
        console.print(f"  [dim]{len(cp.steps)} steps[/dim]\n")
        for i, step in enumerate(cp.steps, 1):
            loc_info = ""
            if step.locator:
                loc_info = f' {step.locator.role}("{step.locator.name}")'
            elif step.url:
                loc_info = f" {step.url}"
            elif step.key:
                loc_info = f" {step.key}"
            console.print(f"  {i}. [bold]{step.action}[/bold]{loc_info}")

        dest = save_to or f"probes/{name}.yml"
        from urllib.parse import urlparse
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        cpf = CriticalPathFile(base_url=base_url, name=name, paths=[cp])
        save_critical_paths(cpf, dest)
        console.print(f"\n[green]Saved to {dest}[/green]")
    else:
        console.print("[dim]Generating story from recorded interactions...[/dim]")
        story = await generate_story(events)

        console.print(f"\n[bold]Generated story:[/bold]\n  {story}\n")

        if append_to:
            with open(append_to, "a") as f:
                f.write(f"\n  - name: recorded_{datetime.now(UTC).strftime('%H%M%S')}\n")
                f.write("    path: /\n")
                f.write(f'    story: "{story}"\n')
            console.print(f"[green]Appended to {append_to}[/green]")
        else:
            click.echo(story)


# --- replay command ---


@main.command("replay")
@click.argument("path_file", type=click.Path(exists=True))
@click.option("--auth", default=None, help="Path to storage state for authentication")
@click.option("--headed", is_flag=True, default=False, help="Run browser in headed mode")
@click.option(
    "--runs-dir", default=RUNS_DIR, show_default=True, help="Directory to save run artifacts"
)
@click.option("--verify", is_flag=True, default=False, help="Run LLM verifier on final state")
@click.option("--json-output", "json_out", is_flag=True, default=False, help="Output results as JSON")
def replay_cmd(
    path_file: str,
    auth: str | None,
    headed: bool,
    runs_dir: str,
    verify: bool,
    json_out: bool,
) -> None:
    """Replay critical paths deterministically from a YAML file."""
    if verify:
        _check_api_key()
    asyncio.run(_replay_async(path_file, auth, not headed, runs_dir, verify, json_out))


async def _replay_async(
    path_file: str,
    auth: str | None,
    headless: bool,
    runs_dir: str,
    verify: bool = False,
    json_out: bool = False,
) -> None:
    from .critical_path import load_critical_paths
    from .replay import replay_all

    cpf = load_critical_paths(path_file)

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(runs_dir) / f"replay-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        Panel(
            f"[bold]File:[/bold] {path_file}\n"
            f"[bold]Base URL:[/bold] {cpf.base_url}\n"
            f"[bold]Paths:[/bold] {len(cpf.paths)}",
            title="[blue]QAProbe Replay[/blue]",
        )
    )

    results = await replay_all(
        cpf,
        headless=headless,
        storage_state=auth,
        runs_dir=str(run_dir),
    )

    if verify:
        await _verify_replay_results(results, cpf)

    if json_out:
        output = []
        for r in results:
            output.append({
                "name": r.path_name,
                "passed": r.passed,
                "duration_ms": round(r.total_duration_ms, 1),
                "steps": r.step_dicts,
                "error": r.error,
                "final_url": r.final_url,
            })
        click.echo(json.dumps(output, indent=2))
        if any(not r.passed for r in results):
            sys.exit(1)
        return

    console.print()
    any_fail = False
    for r in results:
        color = "green" if r.passed else "red"
        status = "PASS" if r.passed else "FAIL"
        console.print(f"  [{color}]●[/{color}] [bold]{r.path_name}[/bold]: {status}")
        console.print(
            f"    [dim]{len(r.steps)} steps in {r.total_duration_ms:.0f}ms[/dim]"
        )
        if not r.passed:
            any_fail = True
            console.print(f"    [red]{r.error}[/red]")

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    console.print(
        Panel(
            f"[green]{passed} passed[/green]  [red]{failed} failed[/red]  "
            f"[dim]({sum(r.total_duration_ms for r in results):.0f}ms total)[/dim]",
            title="[blue]Replay Summary[/blue]",
        )
    )

    if any_fail:
        sys.exit(1)


async def _verify_replay_results(results: list, cpf: object) -> None:
    """Run the LLM verifier on successful replay results that have a verify clause."""
    path_by_name = {p.name: p for p in cpf.paths}  # type: ignore[attr-defined]

    for r in results:
        if not r.passed:
            continue
        path_def = path_by_name.get(r.path_name)
        if not path_def or not path_def.verify:
            continue

        console.print(f"  [dim]Verifying {r.path_name}...[/dim]")
        try:
            passed = await _run_replay_verifier(
                path_def.verify, r.screenshot_b64, r.final_url, r.step_dicts
            )
            if not passed:
                r.passed = False
                r.error = f"LLM verifier rejected: {path_def.verify}"
        except Exception as e:
            console.print(f"  [yellow]Verifier error for {r.path_name}: {e}[/yellow]")


async def _run_replay_verifier(
    verify_text: str,
    screenshot_b64: str,
    final_url: str,
    steps: list[dict],
) -> bool:
    """Lightweight verifier for critical path replay — asks the LLM one yes/no question.

    Uses FAST_MODEL (Haiku) since this is a simple pass/fail judgment,
    not the full agentic verification that warrants Opus.
    """
    from .config import FAST_MODEL
    from .provider import get_provider

    llm = get_provider()

    step_summary = "\n".join(
        f"  {s['step_num']}. {s['action']} {s.get('detail', '')}" for s in steps
    )

    prompt = (
        f"A critical path replay just completed successfully.\n\n"
        f"Final URL: {final_url}\n"
        f"Steps executed:\n{step_summary}\n\n"
        f"Verification condition: {verify_text}\n\n"
        f"Based on the screenshot of the final page state, "
        f"does the verification condition appear to be met?\n\n"
        f'Respond with JSON: {{"passed": true/false, "reasoning": "..."}}'
    )

    content: list[dict] = [{"type": "text", "text": prompt}]
    if screenshot_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        })

    response = await llm.chat(
        model=FAST_MODEL,
        system="You are a QA verifier. Judge whether a verification condition is met based on evidence.",
        messages=[{"role": "user", "content": content}],
        max_tokens=256,
    )

    import re
    match = re.search(r"\{[^{}]*\}", response.text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return bool(data.get("passed", False))
        except json.JSONDecodeError:
            pass
    return False


# --- watch command ---


@main.command("watch")
@click.argument("path_file", type=click.Path(exists=True))
@click.option(
    "--interval", default="5m",
    help="Interval between runs (e.g. 30s, 5m, 1h). Default: 5m",
)
@click.option("--auth", default=None, help="Path to storage state for authentication")
@click.option("--verify", is_flag=True, default=False, help="Run LLM verifier on final state")
@click.option("--webhook", default=None, help="URL to POST failure notifications to")
@click.option(
    "--runs-dir", default=RUNS_DIR, show_default=True, help="Directory to save run artifacts"
)
@click.option("--max-runs", default=0, type=int, help="Stop after N runs (0 = unlimited)")
def watch_cmd(
    path_file: str,
    interval: str,
    auth: str | None,
    verify: bool,
    webhook: str | None,
    runs_dir: str,
    max_runs: int,
) -> None:
    """Watch critical paths on a schedule, alerting on failures."""
    if verify:
        _check_api_key()
    seconds = _parse_interval(interval)
    asyncio.run(
        _watch_async(path_file, seconds, auth, verify, webhook, runs_dir, max_runs)
    )


def _parse_interval(interval: str) -> int:
    """Parse a human interval string like '30s', '5m', '1h' into seconds."""
    interval = interval.strip().lower()
    if interval.endswith("h"):
        return int(interval[:-1]) * 3600
    if interval.endswith("m"):
        return int(interval[:-1]) * 60
    if interval.endswith("s"):
        return int(interval[:-1])
    return int(interval)


async def _watch_async(
    path_file: str,
    interval_seconds: int,
    auth: str | None,
    verify: bool,
    webhook: str | None,
    runs_dir: str,
    max_runs: int,
) -> None:
    from .critical_path import load_critical_paths
    from .replay import replay_all

    cpf = load_critical_paths(path_file)

    console.print(
        Panel(
            f"[bold]File:[/bold] {path_file}\n"
            f"[bold]Base URL:[/bold] {cpf.base_url}\n"
            f"[bold]Paths:[/bold] {len(cpf.paths)}\n"
            f"[bold]Interval:[/bold] {interval_seconds}s",
            title="[blue]QAProbe Watch[/blue]",
        )
    )

    run_count = 0
    consecutive_failures = 0

    while True:
        run_count += 1
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_dir = Path(runs_dir) / f"watch-{ts}"
        run_dir.mkdir(parents=True, exist_ok=True)

        console.print(f"\n[dim]── Run #{run_count} at {ts} ──[/dim]")

        try:
            results = await replay_all(
                cpf, headless=True, storage_state=auth, runs_dir=str(run_dir),
            )

            if verify:
                await _verify_replay_results(results, cpf)

            failed = [r for r in results if not r.passed]

            for r in results:
                color = "green" if r.passed else "red"
                status = "PASS" if r.passed else "FAIL"
                line = f"  [{color}]●[/{color}] {r.path_name}: {status} ({r.total_duration_ms:.0f}ms)"
                if not r.passed:
                    line += f" — {r.error}"
                console.print(line)

            if failed:
                consecutive_failures += 1
                console.print(
                    f"  [red bold]{len(failed)}/{len(results)} paths failed "
                    f"(streak: {consecutive_failures})[/red bold]"
                )
                if webhook:
                    await _send_webhook(webhook, cpf.name, ts, failed)
            else:
                if consecutive_failures > 0:
                    console.print("  [green]All paths recovered.[/green]")
                consecutive_failures = 0

        except Exception as e:
            console.print(f"  [red]Watch run error: {e}[/red]")
            consecutive_failures += 1

        if max_runs and run_count >= max_runs:
            console.print(f"\n[dim]Reached max-runs ({max_runs}), stopping.[/dim]")
            break

        console.print(f"  [dim]Next run in {interval_seconds}s...[/dim]")
        await asyncio.sleep(interval_seconds)


async def _send_webhook(webhook_url: str, suite_name: str, timestamp: str, failed: list) -> None:
    """POST a failure notification to a webhook URL."""
    import urllib.request

    payload = json.dumps({
        "event": "critical_path_failure",
        "suite": suite_name,
        "timestamp": timestamp,
        "failures": [
            {"name": r.path_name, "error": r.error, "duration_ms": round(r.total_duration_ms, 1)}
            for r in failed
        ],
    }).encode()

    try:
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        console.print(f"  [dim]Webhook sent to {webhook_url}[/dim]")
    except Exception as e:
        console.print(f"  [yellow]Webhook failed: {e}[/yellow]")


# --- install command ---


@main.command("install")
def install_cmd() -> None:
    """Install Playwright browser (Chromium) for qaprobe."""
    console.print("[dim]Installing Chromium via Playwright...[/dim]")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=False,
    )
    if result.returncode == 0:
        console.print("[green]Chromium installed successfully.[/green]")
    else:
        console.print("[red]Failed to install Chromium.[/red]")
        sys.exit(1)
