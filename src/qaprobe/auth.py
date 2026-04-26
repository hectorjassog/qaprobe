from __future__ import annotations

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


async def save_storage_state(url: str, output_path: str) -> None:
    """Launch a headed browser for manual login, then save storage state."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(url)

        print(f"\nBrowser opened at: {url}")
        print("Please log in manually in the browser window.")
        print("Press ENTER in this terminal when you are done logging in...")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input)

        # Save storage state
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(out))

        await browser.close()
        print(f"\nStorage state saved to: {output_path}")


def load_storage_state(path: str) -> dict:
    """Load storage state from a JSON file."""
    return json.loads(Path(path).read_text())
