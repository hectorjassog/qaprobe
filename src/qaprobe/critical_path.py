"""Critical path schema: load, save, and validate deterministic step sequences."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Locator:
    role: str
    name: str = ""
    nth: int = 0
    test_id: str = ""
    css: str = ""
    exact: bool = True

    def to_dict(self) -> dict:
        d: dict = {"role": self.role}
        if self.name:
            d["name"] = self.name
        if self.nth:
            d["nth"] = self.nth
        if self.test_id:
            d["test_id"] = self.test_id
        if self.css:
            d["css"] = self.css
        if not self.exact:
            d["exact"] = False
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Locator:
        return cls(
            role=data["role"],
            name=data.get("name", ""),
            nth=data.get("nth", 0),
            test_id=data.get("test_id", ""),
            css=data.get("css", ""),
            exact=data.get("exact", True),
        )


@dataclass
class PathStep:
    action: str  # navigate, click, fill, select, press_key, scroll, wait
    locator: Locator | None = None
    url: str = ""
    value: str = ""
    key: str = ""
    direction: str = ""
    amount: int = 300
    ms: int = 1000

    def to_dict(self) -> dict:
        d: dict = {"action": self.action}
        if self.locator:
            d["locator"] = self.locator.to_dict()
        if self.url:
            d["url"] = self.url
        if self.value:
            d["value"] = self.value
        if self.key:
            d["key"] = self.key
        if self.direction:
            d["direction"] = self.direction
            d["amount"] = self.amount
        if self.action == "wait":
            d["ms"] = self.ms
        return d

    @classmethod
    def from_dict(cls, data: dict) -> PathStep:
        locator = None
        if "locator" in data:
            locator = Locator.from_dict(data["locator"])
        return cls(
            action=data["action"],
            locator=locator,
            url=data.get("url", ""),
            value=data.get("value", ""),
            key=data.get("key", ""),
            direction=data.get("direction", ""),
            amount=data.get("amount", 300),
            ms=data.get("ms", 1000),
        )


@dataclass
class CriticalPath:
    name: str
    steps: list[PathStep] = field(default_factory=list)
    description: str = ""
    verify: str = ""


@dataclass
class CriticalPathFile:
    base_url: str
    paths: list[CriticalPath] = field(default_factory=list)
    name: str = ""
    auth_storage_state: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "base_url": self.base_url}
        if self.auth_storage_state:
            d["auth"] = {"storage_state": self.auth_storage_state}
        d["critical_paths"] = []
        for cp in self.paths:
            entry: dict = {"name": cp.name}
            if cp.description:
                entry["description"] = cp.description
            entry["steps"] = [s.to_dict() for s in cp.steps]
            if cp.verify:
                entry["verify"] = cp.verify
            d["critical_paths"].append(entry)
        return d


def load_critical_paths(path: str | Path) -> CriticalPathFile:
    """Load critical paths from a YAML file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    base_url = data.get("base_url", "")
    name = data.get("name", Path(path).stem)
    auth = data.get("auth", {})
    auth_storage_state = auth.get("storage_state") if auth else None

    paths: list[CriticalPath] = []
    for item in data.get("critical_paths", []):
        steps = [PathStep.from_dict(s) for s in item.get("steps", [])]
        paths.append(
            CriticalPath(
                name=item["name"],
                steps=steps,
                description=item.get("description", ""),
                verify=item.get("verify", ""),
            )
        )

    return CriticalPathFile(
        base_url=base_url,
        paths=paths,
        name=name,
        auth_storage_state=auth_storage_state,
    )


def save_critical_paths(cpf: CriticalPathFile, path: str | Path) -> None:
    """Save critical paths to a YAML file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.dump(cpf.to_dict(), default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
