from __future__ import annotations

import asyncio
import base64
import hashlib
from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from .config import DEBOUNCE_POLL_MS, DEBOUNCE_STABLE_MS, DEBOUNCE_TIMEOUT_MS

ROLE_PREFIX = {
    "button": "btn",
    "link": "lnk",
    "textbox": "inp",
    "checkbox": "chk",
    "radio": "rad",
    "combobox": "sel",
    "listbox": "lst",
    "option": "opt",
    "menuitem": "mnu",
    "tab": "tab",
    "heading": "hd",
    "img": "img",
    "list": "ul",
    "listitem": "li",
    "generic": "div",
    "paragraph": "p",
    "main": "main",
    "navigation": "nav",
    "banner": "hdr",
    "contentinfo": "ftr",
    "form": "form",
    "search": "srch",
    "region": "rgn",
    "dialog": "dlg",
    "alert": "alrt",
    "status": "stat",
    "log": "log",
    "progressbar": "prog",
    "spinbutton": "spin",
    "slider": "sld",
    "separator": "sep",
    "table": "tbl",
    "row": "row",
    "cell": "cel",
    "columnheader": "col",
    "rowheader": "rh",
    "grid": "grd",
    "gridcell": "gc",
    "treeitem": "tri",
    "tree": "tre",
    "group": "grp",
    "toolbar": "tb",
    "menu": "mnu",
    "menubar": "mnb",
    "tooltip": "tip",
    "figure": "fig",
    "math": "math",
    "note": "note",
    "term": "term",
    "definition": "def",
    "code": "code",
    "deletion": "del",
    "insertion": "ins",
    "subscript": "sub",
    "superscript": "sup",
    "time": "time",
    "mark": "mark",
}


def _short_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:6]


@dataclass
class AXElement:
    ref: str
    role: str
    name: str
    description: str = ""
    value: str = ""
    disabled: bool = False
    level: int = 0
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Snapshot:
    elements: list[AXElement] = field(default_factory=list)
    raw_text: str = ""

    def compact(self, max_elements: int = 200) -> str:
        lines = []
        for el in self.elements[:max_elements]:
            parts = [f"[{el.ref}]", f"role={el.role}"]
            if el.name:
                parts.append(f'name="{el.name}"')
            if el.value:
                parts.append(f'value="{el.value}"')
            if el.disabled:
                parts.append("disabled")
            if el.level:
                parts.append(f"level={el.level}")
            lines.append(" ".join(parts))
        if len(self.elements) > max_elements:
            lines.append(f"... ({len(self.elements) - max_elements} more elements)")
        return "\n".join(lines)


class RefResolver:
    """Maps ref strings to Playwright locators with duplicate-name disambiguation."""

    def __init__(self) -> None:
        self._map: dict[str, AXElement] = {}
        self._role_name_counts: dict[tuple[str, str], int] = {}
        self._role_name_indices: dict[str, int] = {}

    def register(self, elements: list[AXElement]) -> None:
        self._map = {el.ref: el for el in elements}

        counts: dict[tuple[str, str], int] = {}
        indices: dict[str, int] = {}
        seen: dict[tuple[str, str], int] = {}
        for el in elements:
            key = (el.role, el.name)
            counts[key] = counts.get(key, 0) + 1

        for el in elements:
            key = (el.role, el.name)
            idx = seen.get(key, 0)
            seen[key] = idx + 1
            indices[el.ref] = idx

        self._role_name_counts = counts
        self._role_name_indices = indices

    def resolve(self, page: Page, ref: str) -> Any:
        """Return a Playwright locator for the given ref."""
        el = self._map.get(ref)
        if el is None:
            raise ValueError(f"Unknown ref: {ref!r}")

        role = el.role
        name = el.name
        idx = self._role_name_indices.get(ref, 0)

        if name:
            locator = page.get_by_role(role, name=name)  # type: ignore[arg-type]
            return locator.nth(idx)
        else:
            return page.get_by_role(role).nth(idx)  # type: ignore[arg-type]


def _build_parent_map(nodes: list[dict]) -> dict[str, str]:
    """Build nodeId → parentId lookup from CDP nodes that have parentId."""
    parent_map: dict[str, str] = {}
    for node in nodes:
        nid = node.get("nodeId", "")
        pid = node.get("parentId")
        if nid and pid:
            parent_map[nid] = pid
    return parent_map


def _build_node_map(nodes: list[dict]) -> dict[str, dict]:
    return {node["nodeId"]: node for node in nodes if "nodeId" in node}


def _get_parent_role(node_map: dict[str, dict], parent_map: dict[str, str], node_id: str) -> str:
    pid = parent_map.get(node_id)
    if not pid:
        return ""
    parent = node_map.get(pid)
    if not parent:
        return ""
    return parent.get("role", {}).get("value", "")


def _make_stable_ref(role: str, name: str, parent_role: str, counters: dict[str, int]) -> str:
    prefix = ROLE_PREFIX.get(role, role[:3].lower())
    if name:
        safe_name = name.lower().replace(" ", "-")[:20]
        base = f"{prefix}:{safe_name}"
        if parent_role:
            parent_prefix = ROLE_PREFIX.get(parent_role, parent_role[:3].lower())
            base = f"{prefix}:{safe_name}@{parent_prefix}"
    else:
        base = prefix

    count = counters.get(base, 0)
    counters[base] = count + 1
    if count == 0:
        return base
    return f"{base}#{count}"


def parse_ax_tree(nodes: list[dict]) -> Snapshot:
    """Convert raw CDP AX nodes to a Snapshot with stable deterministic refs."""
    parent_map = _build_parent_map(nodes)
    node_map = _build_node_map(nodes)
    counters: dict[str, int] = {}
    elements = []

    for node in nodes:
        role = node.get("role", {}).get("value", "")
        if not role or role in ("none", "presentation", "ignored", "InlineTextBox", "StaticText"):
            continue

        name_val = node.get("name", {}).get("value", "")
        desc_val = node.get("description", {}).get("value", "")
        value_val = node.get("value", {}).get("value", "")

        props = {p["name"]: p.get("value", {}).get("value") for p in node.get("properties", [])}
        if props.get("hidden") is True:
            continue

        node_id = node.get("nodeId", "")
        parent_role = _get_parent_role(node_map, parent_map, node_id)

        ref = _make_stable_ref(role, name_val, parent_role, counters)

        level = 0
        if role == "heading":
            try:
                level = int(props.get("level", 0) or 0)
            except (ValueError, TypeError):
                level = 0

        disabled = bool(props.get("disabled"))

        elements.append(
            AXElement(
                ref=ref,
                role=role,
                name=name_val,
                description=desc_val,
                value=str(value_val) if value_val is not None else "",
                disabled=disabled,
                level=level,
                properties=props,
            )
        )

    snapshot = Snapshot(elements=elements)
    snapshot.raw_text = snapshot.compact()
    return snapshot


class BrowserSession:
    """Manages Playwright browser lifecycle for a single run."""

    def __init__(self, headless: bool = True, timeout_ms: int = 30000) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self.resolver = RefResolver()

    async def start(self, runs_dir: str, storage_state: str | None = None) -> Page:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)

        ctx_kwargs: dict = {
            "record_video_dir": runs_dir,
            "record_video_size": {"width": 1280, "height": 720},
        }
        if storage_state:
            ctx_kwargs["storage_state"] = storage_state

        self._context = await self._browser.new_context(**ctx_kwargs)
        await self._context.tracing.start(screenshots=True, snapshots=True, sources=True)

        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        return self._page

    async def snapshot(self) -> Snapshot:
        """Take an AX tree snapshot of the current page."""
        page = self._page
        assert page is not None
        client = await page.context.new_cdp_session(page)
        result = await client.send("Accessibility.getFullAXTree")
        await client.detach()
        nodes = result.get("nodes", [])
        snap = parse_ax_tree(nodes)
        self.resolver.register(snap.elements)
        return snap

    async def wait_for_stable(self) -> None:
        """Wait until the AX tree stabilizes (SPA debouncing)."""
        page = self._page
        assert page is not None

        poll_interval = DEBOUNCE_POLL_MS / 1000
        stable_threshold = DEBOUNCE_STABLE_MS / 1000
        timeout = DEBOUNCE_TIMEOUT_MS / 1000

        client = await page.context.new_cdp_session(page)
        result = await client.send("Accessibility.getFullAXTree")
        last_count = len(result.get("nodes", []))
        await client.detach()

        stable_time = 0.0
        elapsed = 0.0

        while elapsed < timeout:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            client = await page.context.new_cdp_session(page)
            result = await client.send("Accessibility.getFullAXTree")
            current_count = len(result.get("nodes", []))
            await client.detach()

            if current_count == last_count:
                stable_time += poll_interval
                if stable_time >= stable_threshold:
                    return
            else:
                stable_time = 0.0
                last_count = current_count

    async def screenshot(self) -> str:
        """Take a screenshot and return it as a base64-encoded PNG."""
        page = self._page
        assert page is not None
        png_bytes = await page.screenshot(type="png", full_page=False)
        return base64.b64encode(png_bytes).decode("ascii")

    async def save_trace(self, path: str) -> None:
        assert self._context is not None
        await self._context.tracing.stop(path=path)

    async def close(self) -> None:
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
