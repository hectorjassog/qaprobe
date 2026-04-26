"""Configuration: env vars, defaults, model routing."""

from __future__ import annotations

import os

# Anthropic models
AGENT_MODEL = os.environ.get("QAPROBE_AGENT_MODEL", "claude-sonnet-4-5")
VERIFIER_MODEL = os.environ.get("QAPROBE_VERIFIER_MODEL", "claude-opus-4-5")

# Agent loop
MAX_STEPS = int(os.environ.get("QAPROBE_MAX_STEPS", "40"))

# Playwright
HEADLESS = os.environ.get("QAPROBE_HEADLESS", "1") not in ("0", "false", "no")
BROWSER_TIMEOUT_MS = int(os.environ.get("QAPROBE_BROWSER_TIMEOUT_MS", "30000"))

# Output
RUNS_DIR = os.environ.get("QAPROBE_RUNS_DIR", "runs")

# Anthropic API key
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
