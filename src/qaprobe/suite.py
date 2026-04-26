from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SuiteStory:
    name: str
    story: str
    path: str = "/"
    depends_on: str | None = None


@dataclass
class Suite:
    base_url: str
    stories: list[SuiteStory] = field(default_factory=list)
    auth_storage_state: str | None = None
    name: str = ""


def load_suite(path: str | Path) -> Suite:
    """Load a YAML suite file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    base_url = data.get("base_url", "")
    name = data.get("name", Path(path).stem)

    auth = data.get("auth", {})
    auth_storage_state = auth.get("storage_state") if auth else None

    stories = []
    for item in data.get("stories", []):
        stories.append(
            SuiteStory(
                name=item["name"],
                story=item["story"],
                path=item.get("path", "/"),
                depends_on=item.get("depends_on"),
            )
        )

    return Suite(
        base_url=base_url,
        stories=stories,
        auth_storage_state=auth_storage_state,
        name=name,
    )


def resolve_order(stories: list[SuiteStory]) -> list[SuiteStory]:
    """Topological sort based on depends_on."""
    story_map = {s.name: s for s in stories}
    visited: set[str] = set()
    result: list[SuiteStory] = []

    def visit(name: str) -> None:
        if name in visited:
            return
        story = story_map[name]
        if story.depends_on:
            visit(story.depends_on)
        visited.add(name)
        result.append(story)

    for s in stories:
        visit(s.name)

    return result
