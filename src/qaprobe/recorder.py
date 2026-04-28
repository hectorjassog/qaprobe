"""Record user interactions in a headed browser and generate a natural-language story."""

from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import async_playwright

from .config import AGENT_MODEL
from .provider import LLMProvider, get_provider


@dataclass
class RecordedEvent:
    action: str  # "navigate", "click", "fill", "select", "press_key"
    target: str = ""
    value: str = ""
    url: str = ""


STORY_GENERATION_PROMPT = """You are a QA engineer. Given a sequence of browser interactions, write a concise natural-language user story that describes what the user was trying to accomplish and what they should expect to see.

The story should:
- Be written in plain English, as an instruction
- Describe the goal, not the exact clicks
- End with a verification condition ("and verify that...")

Interactions:
{events}

Write ONLY the user story text, nothing else."""


async def record_session(url: str) -> list[RecordedEvent]:
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

        await page.expose_function(
            "__qaprobe_click",
            lambda target: events.append(RecordedEvent(action="click", target=target)),
        )
        await page.expose_function(
            "__qaprobe_fill",
            lambda target, value: events.append(RecordedEvent(action="fill", target=target, value=value)),
        )

        # Inject interaction tracking script
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

        print(f"\nRecording at: {url}")
        print("Interact with the page, then close the browser window when done.")

        try:
            await page.wait_for_event("close", timeout=0)
        except Exception:
            pass

        await browser.close()

    return events


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
