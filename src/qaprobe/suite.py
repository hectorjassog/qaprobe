from __future__ import annotations

import json
import re
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
    allowed_origins: list[str] = field(default_factory=list)
    reveal_fields: list[str] = field(default_factory=list)
    macros: dict[str, str] = field(default_factory=dict)


def expand_macros(text: str, macros: dict[str, str]) -> str:
    """Expand {{macro_name(arg1, arg2)}} patterns in story text."""
    if not macros:
        return text

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        args_str = match.group(2) or ""
        template = macros.get(name)
        if template is None:
            return match.group(0)
        args = [a.strip().strip('"').strip("'") for a in args_str.split(",") if a.strip()]
        result = template
        for i, arg in enumerate(args, 1):
            result = result.replace(f"{{{{{i}}}}}", arg)
        return result

    return re.sub(r"\{\{(\w+)\(([^)]*)\)\}\}", _replace, text)


def load_suite(path: str | Path) -> Suite:
    """Load a YAML suite file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    base_url = data.get("base_url", "")
    name = data.get("name", Path(path).stem)

    auth = data.get("auth", {})
    auth_storage_state = auth.get("storage_state") if auth else None

    allowed_origins = data.get("allowed_origins", [])
    reveal_fields = data.get("reveal_fields", [])
    macros = data.get("macros", {})

    stories = []
    for item in data.get("stories", []):
        story_text = item["story"]
        if macros:
            story_text = expand_macros(story_text, macros)
        stories.append(
            SuiteStory(
                name=item["name"],
                story=story_text,
                path=item.get("path", "/"),
                depends_on=item.get("depends_on"),
            )
        )

    return Suite(
        base_url=base_url,
        stories=stories,
        auth_storage_state=auth_storage_state,
        name=name,
        allowed_origins=allowed_origins,
        reveal_fields=reveal_fields,
        macros=macros,
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


# --- Baseline support ---

BASELINE_FILE = ".qaprobe/baseline.json"


def load_baseline(path: str = BASELINE_FILE) -> dict[str, str]:
    """Load baseline verdicts from a JSON file. Returns {story_name: verdict}."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def save_baseline(results: dict[str, str], path: str = BASELINE_FILE) -> None:
    """Save verdict-per-story to a baseline JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(results, indent=2))


def check_regressions(
    current: dict[str, str],
    baseline: dict[str, str],
) -> list[str]:
    """Return story names that regressed (were pass in baseline, now fail/inconclusive)."""
    regressions = []
    for name, verdict in current.items():
        baseline_verdict = baseline.get(name)
        if baseline_verdict == "pass" and verdict != "pass":
            regressions.append(name)
    return regressions
