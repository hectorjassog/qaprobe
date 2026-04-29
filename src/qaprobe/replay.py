"""Deterministic replay engine for critical paths."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Page

from .browser import BrowserSession, Snapshot
from .critical_path import CriticalPath, CriticalPathFile, PathStep

logger = logging.getLogger("qaprobe.replay")

PROBE_TIMEOUT_MS = 2000


@dataclass
class StepResult:
    step_num: int
    action: str
    detail: str
    passed: bool
    duration_ms: float
    error: str = ""
    warning: str = ""

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
        if self.warning:
            d["warning"] = self.warning
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


# ---------------------------------------------------------------------------
# Edit distance for self-healing suggestions
# ---------------------------------------------------------------------------

def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance between two strings (case-insensitive)."""
    a, b = a.lower(), b.lower()
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def suggest_closest(
    snapshot: Snapshot,
    role: str,
    name: str,
    max_suggestions: int = 3,
) -> list[str]:
    """Find the closest AX elements by role and name similarity."""
    if not name:
        return []

    candidates: list[tuple[int, str]] = []
    for el in snapshot.elements:
        if not el.name:
            continue
        if el.role == role:
            dist = _edit_distance(name, el.name)
            label = f'{el.role}("{el.name}")'
            candidates.append((dist, label))
        elif el.name.lower() == name.lower():
            label = f'{el.role}("{el.name}") [different role]'
            candidates.append((0, label))

    candidates.sort(key=lambda x: x[0])
    seen: set[str] = set()
    results: list[str] = []
    for _, label in candidates:
        if label not in seen:
            seen.add(label)
            results.append(label)
        if len(results) >= max_suggestions:
            break
    return results


# ---------------------------------------------------------------------------
# Tiered locator resolution
# ---------------------------------------------------------------------------

async def _locator_visible(locator: Any, timeout_ms: int = PROBE_TIMEOUT_MS) -> bool:
    """Check whether a Playwright locator finds at least one visible element."""
    try:
        await locator.first.wait_for(state="visible", timeout=timeout_ms)
        return True
    except Exception:
        return False


async def _resolve_locator(
    page: Page,
    step: PathStep,
    session: BrowserSession | None = None,
) -> tuple[Any, str]:
    """Tiered locator resolution. Returns (locator, warning_message).

    Resolution order:
      1. Exact role + name match
      2. Fuzzy role + name match (exact=False)
      3. data-testid fallback
      4. CSS selector fallback
    If all fail, take an AX snapshot and suggest closest matches.
    """
    loc = step.locator
    if loc is None:
        raise ValueError(f"Step action '{step.action}' requires a locator")

    warning = ""

    # --- Tier 1: exact match ---
    if loc.name:
        exact_loc = page.get_by_role(
            loc.role, name=loc.name, exact=loc.exact,  # type: ignore[arg-type]
        )
        candidate = exact_loc.nth(loc.nth) if loc.nth else exact_loc.first
        if await _locator_visible(candidate):
            return candidate, warning

    elif loc.role:
        role_loc = page.get_by_role(loc.role)  # type: ignore[arg-type]
        candidate = role_loc.nth(loc.nth) if loc.nth else role_loc.first
        if await _locator_visible(candidate):
            return candidate, warning

    # --- Tier 2: fuzzy match (only if tier 1 used exact=True and has a name) ---
    if loc.name and loc.exact:
        fuzzy_loc = page.get_by_role(
            loc.role, name=loc.name, exact=False,  # type: ignore[arg-type]
        )
        candidate = fuzzy_loc.nth(loc.nth) if loc.nth else fuzzy_loc.first
        if await _locator_visible(candidate):
            warning = (
                f"Fuzzy match used for {loc.role}(\"{loc.name}\") — "
                f"exact match failed, substring/case-insensitive matched"
            )
            logger.warning(warning)
            return candidate, warning

    # --- Tier 3: test_id fallback ---
    if loc.test_id:
        tid_loc = page.get_by_test_id(loc.test_id).first
        if await _locator_visible(tid_loc):
            warning = (
                f"Fallback to test_id=\"{loc.test_id}\" for "
                f"{loc.role}(\"{loc.name}\") — role+name not found"
            )
            logger.warning(warning)
            return tid_loc, warning

    # --- Tier 4: CSS selector fallback ---
    if loc.css:
        css_loc = page.locator(loc.css).first
        if await _locator_visible(css_loc):
            warning = (
                f"Fallback to css=\"{loc.css}\" for "
                f"{loc.role}(\"{loc.name}\") — role+name and test_id not found"
            )
            logger.warning(warning)
            return css_loc, warning

    # --- All tiers failed: build a helpful error with suggestions ---
    suggestions: list[str] = []
    if session:
        try:
            snap = await session.snapshot()
            suggestions = suggest_closest(snap, loc.role, loc.name)
        except Exception:
            pass

    msg = f'{loc.role}("{loc.name}") not found on page'
    if suggestions:
        msg += "\n  Suggestions:\n"
        for s in suggestions:
            msg += f"    - {s}\n"
    raise ValueError(msg)


async def _execute_step(
    page: Page,
    session: BrowserSession,
    step: PathStep,
    base_url: str,
) -> str:
    """Execute a single critical-path step. Returns a warning string (empty if none)."""
    warning = ""

    if step.action == "navigate":
        url = step.url
        if url.startswith("/"):
            url = base_url.rstrip("/") + url
        await page.goto(url, wait_until="domcontentloaded")
        await session.wait_for_stable()

    elif step.action == "click":
        locator, warning = await _resolve_locator(page, step, session)
        await locator.click()
        await page.wait_for_load_state("domcontentloaded")
        await session.wait_for_stable()

    elif step.action == "fill":
        locator, warning = await _resolve_locator(page, step, session)
        await locator.fill(step.value)

    elif step.action == "select":
        locator, warning = await _resolve_locator(page, step, session)
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

    return warning


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
        _fallback_dir = None
        if not video_dir:
            _fallback_dir = tempfile.mkdtemp(prefix="qaprobe-replay-")
        page = await session.start(video_dir or _fallback_dir, storage_state=storage_state)

        for i, step in enumerate(path.steps, 1):
            step_start = time.monotonic()
            detail = _step_detail(step)

            try:
                warning = await _execute_step(page, session, step, base_url)
                elapsed = (time.monotonic() - step_start) * 1000
                result.steps.append(StepResult(
                    step_num=i,
                    action=step.action,
                    detail=detail,
                    passed=True,
                    duration_ms=elapsed,
                    warning=warning,
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
