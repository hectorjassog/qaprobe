"""Record user interactions in a headed browser and generate a natural-language story."""

from __future__ import annotations

import json
from dataclasses import dataclass

from playwright.async_api import Page, async_playwright

from .config import AGENT_MODEL
from .critical_path import CriticalPath, Locator, PathStep
from .provider import LLMProvider, get_provider


@dataclass
class RecordedEvent:
    action: str  # "navigate", "click", "fill", "select", "press_key"
    target: str = ""
    value: str = ""
    url: str = ""
    role: str = ""
    name: str = ""


STORY_GENERATION_PROMPT = """You are a QA engineer. Given a sequence of browser interactions, write a concise natural-language user story that describes what the user was trying to accomplish and what they should expect to see.

The story should:
- Be written in plain English, as an instruction
- Describe the goal, not the exact clicks
- End with a verification condition ("and verify that...")

Interactions:
{events}

Write ONLY the user story text, nothing else."""


# Maps HTML tags/input types to ARIA roles for the injected JS
_ROLE_INFERENCE_JS = """
function __qaprobe_infer_role(el) {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;

    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();

    const map = {
        'a': 'link', 'button': 'button', 'select': 'combobox',
        'textarea': 'textbox', 'h1': 'heading', 'h2': 'heading',
        'h3': 'heading', 'h4': 'heading', 'h5': 'heading', 'h6': 'heading',
        'nav': 'navigation', 'main': 'main', 'form': 'form',
        'img': 'img', 'table': 'table', 'dialog': 'dialog',
    };
    if (map[tag]) return map[tag];

    if (tag === 'input') {
        const inputMap = {
            'checkbox': 'checkbox', 'radio': 'radio', 'range': 'slider',
            'number': 'spinbutton', 'search': 'searchbox',
        };
        return inputMap[type] || 'textbox';
    }

    return '';
}

function __qaprobe_get_name(el) {
    const label = el.getAttribute('aria-label');
    if (label) return label;

    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
        const parts = labelledBy.split(/\\s+/).map(id => {
            const ref = document.getElementById(id);
            return ref ? ref.textContent.trim() : '';
        }).filter(Boolean);
        if (parts.length) return parts.join(' ');
    }

    if (el.tagName.toLowerCase() === 'input' || el.tagName.toLowerCase() === 'textarea' || el.tagName.toLowerCase() === 'select') {
        if (el.id) {
            const lbl = document.querySelector('label[for="' + el.id + '"]');
            if (lbl) return lbl.textContent.trim();
        }
        const parentLabel = el.closest('label');
        if (parentLabel) return parentLabel.textContent.trim().substring(0, 80);
        const placeholder = el.getAttribute('placeholder');
        if (placeholder) return placeholder;
        const name = el.getAttribute('name');
        if (name) return name;
    }

    const text = el.textContent?.trim().substring(0, 80);
    return text || el.tagName.toLowerCase();
}
"""


async def record_session(url: str, critical_path: bool = False) -> list[RecordedEvent]:
    """Launch a headed browser, record interactions, return events when user closes."""
    events: list[RecordedEvent] = []
    events.append(RecordedEvent(action="navigate", url=url))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(url)

        last_url = url

        page.on("framenavigated", lambda frame: _on_navigate(frame, events, last_url))

        if critical_path:
            await _setup_critical_path_listeners(page, events)
        else:
            await _setup_story_listeners(page, events)

        print(f"\nRecording at: {url}")
        print("Interact with the page, then close the browser window when done.")

        try:
            await page.wait_for_event("close", timeout=0)
        except Exception:
            pass

        await browser.close()

    return events


async def _setup_story_listeners(page: Page, events: list[RecordedEvent]) -> None:
    """Original fuzzy event listeners for story generation mode."""
    await page.expose_function(
        "__qaprobe_click",
        lambda target: events.append(RecordedEvent(action="click", target=target)),
    )
    await page.expose_function(
        "__qaprobe_fill",
        lambda target, value: events.append(
            RecordedEvent(action="fill", target=target, value=value)
        ),
    )

    await page.evaluate("""() => {
        document.addEventListener('click', (e) => {
            const el = e.target;
            const desc = el.getAttribute('aria-label')
                || el.textContent?.trim().substring(0, 50)
                || el.tagName.toLowerCase();
            window.__qaprobe_click(desc);
        }, true);

        document.addEventListener('change', (e) => {
            const el = e.target;
            const desc = el.getAttribute('aria-label')
                || el.getAttribute('name')
                || el.tagName.toLowerCase();
            window.__qaprobe_fill(desc, el.value || '');
        }, true);
    }""")


async def _setup_critical_path_listeners(page: Page, events: list[RecordedEvent]) -> None:
    """Enhanced listeners that capture role + accessible name for deterministic replay."""

    async def on_click(data_json: str) -> None:
        data = json.loads(data_json)
        events.append(RecordedEvent(
            action="click",
            target=data.get("name", ""),
            role=data.get("role", ""),
            name=data.get("name", ""),
        ))

    async def on_fill(data_json: str) -> None:
        data = json.loads(data_json)
        events.append(RecordedEvent(
            action="fill",
            target=data.get("name", ""),
            value=data.get("value", ""),
            role=data.get("role", ""),
            name=data.get("name", ""),
        ))

    async def on_select(data_json: str) -> None:
        data = json.loads(data_json)
        events.append(RecordedEvent(
            action="select",
            target=data.get("name", ""),
            value=data.get("value", ""),
            role=data.get("role", ""),
            name=data.get("name", ""),
        ))

    async def on_keypress(data_json: str) -> None:
        data = json.loads(data_json)
        events.append(RecordedEvent(
            action="press_key",
            value=data.get("key", ""),
        ))

    await page.expose_function("__qaprobe_cp_click", on_click)
    await page.expose_function("__qaprobe_cp_fill", on_fill)
    await page.expose_function("__qaprobe_cp_select", on_select)
    await page.expose_function("__qaprobe_cp_keypress", on_keypress)

    await page.evaluate(_ROLE_INFERENCE_JS)

    await page.evaluate("""() => {
        document.addEventListener('click', (e) => {
            const el = e.target.closest('a, button, [role], input, select, textarea, summary') || e.target;
            const role = __qaprobe_infer_role(el);
            if (!role) return;
            const name = __qaprobe_get_name(el);
            window.__qaprobe_cp_click(JSON.stringify({role, name}));
        }, true);

        document.addEventListener('change', (e) => {
            const el = e.target;
            const role = __qaprobe_infer_role(el);
            if (!role) return;
            const name = __qaprobe_get_name(el);

            if (el.tagName.toLowerCase() === 'select') {
                const selected = el.options[el.selectedIndex];
                window.__qaprobe_cp_select(JSON.stringify({
                    role, name, value: selected ? selected.text : el.value
                }));
            } else {
                window.__qaprobe_cp_fill(JSON.stringify({role, name, value: el.value || ''}));
            }
        }, true);

        document.addEventListener('keydown', (e) => {
            if (['Enter', 'Escape', 'Tab'].includes(e.key)) {
                window.__qaprobe_cp_keypress(JSON.stringify({key: e.key}));
            }
        }, true);
    }""")


def events_to_critical_path(
    events: list[RecordedEvent],
    name: str = "recorded_path",
) -> CriticalPath:
    """Convert recorded events into a CriticalPath with deterministic locators."""
    steps: list[PathStep] = []

    for ev in events:
        if ev.action == "navigate":
            steps.append(PathStep(action="navigate", url=ev.url))
        elif ev.action == "click" and ev.role:
            steps.append(PathStep(
                action="click",
                locator=Locator(role=ev.role, name=ev.name),
            ))
        elif ev.action == "fill" and ev.role:
            steps.append(PathStep(
                action="fill",
                locator=Locator(role=ev.role, name=ev.name),
                value=ev.value,
            ))
        elif ev.action == "select" and ev.role:
            steps.append(PathStep(
                action="select",
                locator=Locator(role=ev.role, name=ev.name),
                value=ev.value,
            ))
        elif ev.action == "press_key":
            steps.append(PathStep(action="press_key", key=ev.value))

    return CriticalPath(name=name, steps=steps)


def _on_navigate(frame, events: list[RecordedEvent], last_url: str) -> None:
    if frame.url and frame.url != last_url and not frame.url.startswith("about:"):
        events.append(RecordedEvent(action="navigate", url=frame.url))


async def generate_story(events: list[RecordedEvent], provider: LLMProvider | None = None) -> str:
    """Use an LLM to generate a natural-language story from recorded events."""
    llm = provider or get_provider()

    event_lines = []
    for ev in events:
        if ev.action == "navigate":
            event_lines.append(f"Navigated to {ev.url}")
        elif ev.action == "click":
            event_lines.append(f"Clicked on '{ev.target}'")
        elif ev.action == "fill":
            event_lines.append(f"Typed '{ev.value}' into '{ev.target}'")
        elif ev.action == "select":
            event_lines.append(f"Selected '{ev.value}' in '{ev.target}'")
    events_text = "\n".join(event_lines)

    prompt = STORY_GENERATION_PROMPT.format(events=events_text)

    response = await llm.chat(
        model=AGENT_MODEL,
        system="You are a helpful QA engineer.",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )

    return response.text.strip()
