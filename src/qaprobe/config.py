"""Configuration: env vars, defaults, model routing."""

from __future__ import annotations

import os

# Provider
PROVIDER = os.environ.get("QAPROBE_PROVIDER", "anthropic")

# Anthropic models
AGENT_MODEL = os.environ.get("QAPROBE_AGENT_MODEL", "claude-sonnet-4-5")
VERIFIER_MODEL = os.environ.get("QAPROBE_VERIFIER_MODEL", "claude-opus-4-5")
FAST_MODEL = os.environ.get("QAPROBE_FAST_MODEL", "claude-haiku-3-5")

# Model routing threshold: use fast model when snapshot has fewer elements than this
ROUTING_THRESHOLD = int(os.environ.get("QAPROBE_ROUTING_THRESHOLD", "20"))

# Agent loop
MAX_STEPS = int(os.environ.get("QAPROBE_MAX_STEPS", "40"))

# Playwright
HEADLESS = os.environ.get("QAPROBE_HEADLESS", "1") not in ("0", "false", "no")
BROWSER_TIMEOUT_MS = int(os.environ.get("QAPROBE_BROWSER_TIMEOUT_MS", "30000"))

# SPA debounce
DEBOUNCE_POLL_MS = int(os.environ.get("QAPROBE_DEBOUNCE_POLL_MS", "200"))
DEBOUNCE_STABLE_MS = int(os.environ.get("QAPROBE_DEBOUNCE_STABLE_MS", "500"))
DEBOUNCE_TIMEOUT_MS = int(os.environ.get("QAPROBE_DEBOUNCE_TIMEOUT_MS", "3000"))

# Output
RUNS_DIR = os.environ.get("QAPROBE_RUNS_DIR", "runs")

# API keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
