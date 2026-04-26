from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

# Roles that map to short prefixes in refs
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


@dataclass
class AXElement:
    ref: str
    role: str
    name: str
    description: str = ""
    value: str = ""
    disabled: bool = False
    level: int = 0  # for headings


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
    """Maps ref strings to Playwright locators."""

    def __init__(self) -> None:
        self._map: dict[str, AXElement] = {}

    def register(self, elements: list[AXElement]) -> None:
        self._map = {el.ref: el for el in elements}

    def resolve(self, page: Page, ref: str) -> Any:
        """Return a Playwright locator for the given ref."""
        el = self._map.get(ref)
        if el is None:
            raise ValueError(f"Unknown ref: {ref!r}")

        # Parse the index from the ref (e.g., "btn:3" → index 3)
        parts = ref.rsplit(":", 1)
        idx = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else 0

        role = el.role
        name = el.name

        if name:
            locator = page.get_by_role(role, name=name)  # type: ignore[arg-type]
            return locator.nth(0)
        else:
            return page.get_by_role(role).nth(idx)  # type: ignore[arg-type]


def _ax_node_to_element(node: dict, counters: dict[str, int]) -> AXElement | None:
    role = node.get("role", {}).get("value", "")
    if not role or role in ("none", "presentation", "ignored", "InlineTextBox", "StaticText"):
        return None

    name_val = node.get("name", {}).get("value", "")
    desc_val = node.get("description", {}).get("value", "")
    value_val = node.get("value", {}).get("value", "")

    # Check if hidden
    properties = {p["name"]: p.get("value", {}).get("value") for p in node.get("properties", [])}
    if properties.get("hidden") is True:
        return None

    prefix = ROLE_PREFIX.get(role, role[:3].lower())
    idx = counters.get(prefix, 0)
    counters[prefix] = idx + 1
    ref = f"{prefix}:{idx}"

    level = 0
    if role == "heading":
        try:
            level = int(properties.get("level", 0) or 0)
        except (ValueError, TypeError):
            level = 0

    disabled = bool(properties.get("disabled"))

    return AXElement(
        ref=ref,
        role=role,
        name=name_val,
        description=desc_val,
        value=str(value_val) if value_val is not None else "",
        disabled=disabled,
        level=level,
    )


def parse_ax_tree(nodes: list[dict]) -> Snapshot:
    """Convert raw CDP AX nodes to a Snapshot."""
    counters: dict[str, int] = {}
    elements = []
    for node in nodes:
        el = _ax_node_to_element(node, counters)
        if el is not None:
            elements.append(el)
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
