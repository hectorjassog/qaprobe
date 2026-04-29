"""Deterministic replay engine for critical paths."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page

from .browser import BrowserSession
from .critical_path import CriticalPath, CriticalPathFile, PathStep


@dataclass
class StepResult:
    step_num: int
    action: str
    detail: str
    passed: bool
    duration_ms: float
    error: str = ""

    def to_dict(self) -> dict:
        d: dict = {
            "step_num": self.step_num,
            "action": self.action,
            "detail": self.detail,
            "passed": self.passed,
            "duration_ms": round(self.duration_ms, 1),
        }
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class ReplayResult:
    path_name: str
    passed: bool
    steps: list[StepResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    failed_step: int | None = None
    error: str = ""
    screenshot_b64: str = ""
    final_url: str = ""

    @property
    def step_dicts(self) -> list[dict]:
        return [s.to_dict() for s in self.steps]


def _step_detail(step: PathStep) -> str:
    if step.action == "navigate":
        return step.url
    if step.locator:
        loc_str = f'{step.locator.role}("{step.locator.name}")'
        if step.locator.nth:
            loc_str += f".nth({step.locator.nth})"
        if step.value:
            return f"{loc_str} = {step.value!r}"
        return loc_str
    if step.action == "press_key":
        return step.key
    if step.action == "scroll":
        return f"{step.direction} {step.amount}px"
    if step.action == "wait":
        return f"{step.ms}ms"
    return ""


def _resolve_locator(page: Page, step: PathStep) -> Any:
    """Build a Playwright locator from a PathStep's locator definition."""
    loc = step.locator
    if loc is None:
        raise ValueError(f"Step action '{step.action}' requires a locator")

    if loc.name:
        locator = page.get_by_role(loc.role, name=loc.name)  # type: ignore[arg-type]
    else:
        locator = page.get_by_role(loc.role)  # type: ignore[arg-type]

    if loc.nth:
        locator = locator.nth(loc.nth)
    else:
        locator = locator.first

    return locator


async def _execute_step(
    page: Page,
    session: BrowserSession,
    step: PathStep,
    base_url: str,
) -> None:
    """Execute a single critical-path step."""
    if step.action == "navigate":
        url = step.url
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
        await page.goto(url, wait_until="domcontentloaded")
        await session.wait_for_stable()

    elif step.action == "click":
        locator = _resolve_locator(page, step)
        await locator.click()
        await page.wait_for_load_state("domcontentloaded")
        await session.wait_for_stable()

    elif step.action == "fill":
        locator = _resolve_locator(page, step)
        await locator.fill(step.value)

    elif step.action == "select":
        locator = _resolve_locator(page, step)
        await locator.select_option(label=step.value)
        await session.wait_for_stable()

    elif step.action == "press_key":
        await page.keyboard.press(step.key)
        await session.wait_for_stable()

    elif step.action == "scroll":
        dx, dy = 0, 0
        if step.direction == "down":
            dy = step.amount
        elif step.direction == "up":
            dy = -step.amount
        elif step.direction == "right":
            dx = step.amount
        elif step.direction == "left":
            dx = -step.amount
        await page.mouse.wheel(dx, dy)

    elif step.action == "wait":
        await asyncio.sleep(min(step.ms, 10000) / 1000)

    else:
        raise ValueError(f"Unknown action: {step.action!r}")


async def replay_path(
    path: CriticalPath,
    base_url: str,
    headless: bool = True,
    storage_state: str | None = None,
    timeout_ms: int = 30000,
    video_dir: str | None = None,
) -> ReplayResult:
    """Replay a critical path deterministically and return the result."""
    session = BrowserSession(headless=headless, timeout_ms=timeout_ms)
    result = ReplayResult(path_name=path.name, passed=False)
    overall_start = time.monotonic()

    try:
        page = await session.start(video_dir or ".", storage_state=storage_state)

        for i, step in enumerate(path.steps, 1):
            step_start = time.monotonic()
            detail = _step_detail(step)

            try:
                await _execute_step(page, session, step, base_url)
                elapsed = (time.monotonic() - step_start) * 1000
                result.steps.append(StepResult(
                    step_num=i,
                    action=step.action,
                    detail=detail,
                    passed=True,
                    duration_ms=elapsed,
                ))
            except Exception as e:
                elapsed = (time.monotonic() - step_start) * 1000
                result.steps.append(StepResult(
                    step_num=i,
                    action=step.action,
                    detail=detail,
                    passed=False,
                    duration_ms=elapsed,
                    error=str(e),
                ))
                result.failed_step = i
                result.error = f"Step {i} ({step.action} {detail}): {e}"
                break

        result.final_url = page.url

        try:
            result.screenshot_b64 = await session.screenshot()
        except Exception:
            pass

        if result.failed_step is None:
            result.passed = True

    except Exception as e:
        result.error = f"Session startup failed: {e}"
    finally:
        result.total_duration_ms = (time.monotonic() - overall_start) * 1000
        await session.close()

    return result


async def replay_all(
    cpf: CriticalPathFile,
    headless: bool = True,
    storage_state: str | None = None,
    timeout_ms: int = 30000,
    runs_dir: str | None = None,
) -> list[ReplayResult]:
    """Replay all critical paths in a file sequentially."""
    auth = storage_state or cpf.auth_storage_state
    results: list[ReplayResult] = []

    for path in cpf.paths:
        video_dir = None
        if runs_dir:
            from pathlib import Path as P
            vd = P(runs_dir) / path.name / "video"
            vd.mkdir(parents=True, exist_ok=True)
            video_dir = str(vd)

        result = await replay_path(
            path,
            base_url=cpf.base_url,
            headless=headless,
            storage_state=auth,
            timeout_ms=timeout_ms,
            video_dir=video_dir,
        )
        results.append(result)

    return results
