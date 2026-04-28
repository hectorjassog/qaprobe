# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-04-28

### Added
- **Provider abstraction:** support for Anthropic and OpenAI via `QAPROBE_PROVIDER` env var
- **Prompt caching:** `cache_control` on system prompt and tools for ~50% API cost reduction
- **Model routing:** automatic Haiku/Sonnet routing based on page complexity (`--no-routing` to disable)
- **Stable refs:** deterministic element refs using `(role, name, parent_role)` hashing
- **Duplicate-name disambiguation:** `nth()` indexing when multiple elements share the same role+name
- **SPA snapshot debouncing:** waits for AX tree to stabilize after actions before snapshotting
- **Full snapshot history for verifier:** last 5 step snapshots included in verifier prompt
- **Screenshot as verifier input:** final screenshot sent as image block to the verifier model
- **Origin pinning:** `navigate` constrained to allowed origins (configurable in suite YAML)
- **Secret masking:** `fill` text values redacted in reports by default (`--reveal-secrets` to show)
- **Baseline mode:** `qaprobe suite --baseline` saves results; future runs only fail on regressions
- **Confidence calibration:** both-pass with low verifier confidence now returns inconclusive
- **`qaprobe a11y`:** standalone accessibility audit without a user story (JSON or HTML output)
- **Expanded a11y checks:** form label association, live regions, positive tabindex detection
- **Suite-level HTML report:** aggregate `index.html` with status grid, step logs, a11y findings
- **`qaprobe init`:** scaffold a `probes/` directory with sample suite YAML
- **`qaprobe record`:** record browser interactions and generate a natural-language story
- **`qaprobe install`:** helper command to install Playwright Chromium
- **Story macros:** `{{macro_name(args)}}` expansion in suite YAML stories
- **GitHub Action:** `action.yml` composite action for CI integration
- **Example suites:** `examples/` with example.com, TodoMVC, and Hacker News suites
- **Suite YAML enhancements:** `allowed_origins`, `reveal_fields`, `macros` configuration

### Changed
- Ref format changed from counter-based (`btn:0`) to stable name-based (`btn:submit@form`)
- Verifier now receives snapshot history and screenshot, not just the final snapshot
- Reconciliation now considers verifier confidence level
- CLI now includes `--reveal-secrets`, `--no-routing`, `--baseline` flags

## [0.1.0] - 2026-04-26

### Added
- Initial release: `qaprobe run --url ... --story ...` command
- Agentic browser loop using Claude (Sonnet) with Playwright
- Independent verification using a second model (Opus)
- Three-way verdict system (pass/fail/inconclusive)
- Passive accessibility audit on every run
- `qaprobe login` for saving browser storage state
- `qaprobe suite` for running YAML-defined suites of stories
- HTML + JSON reports per run
- Video recording and Playwright trace for every run
