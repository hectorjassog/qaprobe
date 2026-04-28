# qaprobe

Agentic QA for web apps — local or deployed. Give it a URL and a plain-English user story. It drives a real browser with an LLM, records video, and has a second model independently verify the result. Every run also produces an accessibility audit for free.

Works against anything with a URL: `localhost` dev servers, staging environments, production. No setup on the target app — if you can open it in a browser, QAProbe can test it.

## 30-Second Quickstart

```bash
pip install qaprobe
qaprobe install          # downloads Chromium

export ANTHROPIC_API_KEY=sk-ant-...

qaprobe run --url http://localhost:3000 \
  --story "Add an item to the cart and verify the total updates"
```

That's it. You'll get a verdict (PASS / FAIL / INCONCLUSIVE), an HTML report, video recording, Playwright trace, and accessibility findings.

## Usage

### Single run

```bash
# Test your local dev server
qaprobe run --url http://localhost:3000 --story "Add an item to the cart and verify the total updates"

# Test staging before a deploy
qaprobe run --url https://staging.myapp.com --story "Log in and verify the dashboard loads"

# Test any public site
qaprobe run --url https://example.com --story "Click 'More information' and verify I land on IANA's site"
```

### Suite runner

Define a YAML suite and run all stories at once:

```yaml
# probes/myapp.yml
name: my-app
base_url: http://localhost:3000
auth:
  storage_state: .auth/qa.json

macros:
  login_as: "Go to /login, fill {{1}} in username, fill {{2}} in password, click Login"

stories:
  - name: browse_catalog
    path: /
    story: "Browse to the catalog page and verify at least 3 products are listed"

  - name: add_to_cart
    path: /catalog
    story: "Add the first product to the cart and verify the cart badge shows 1"
    depends_on: browse_catalog
```

```bash
qaprobe suite probes/myapp.yml
```

The suite produces a single `index.html` dashboard with per-story status, step logs, a11y findings, and links to videos/traces.

### Authentication

```bash
# Save login state once
qaprobe login --url https://myapp.com/login --save .auth/state.json

# Reuse it
qaprobe run --url https://myapp.com/dashboard --story "..." --auth .auth/state.json
```

### Standalone accessibility audit

```bash
# JSON output
qaprobe a11y --url https://example.com

# HTML report
qaprobe a11y --url https://example.com --html
```

### Record and generate stories

```bash
# Open a browser, interact, then close to generate a story
qaprobe record --url http://localhost:3000

# Append to an existing suite
qaprobe record --url http://localhost:3000 --append-to probes/myapp.yml
```

### Scaffold a new project

```bash
qaprobe init
# Creates probes/example.yml and .auth/ directory
```

## CI / GitHub Actions

```yaml
- uses: qaprobe/action@v1
  with:
    suite: probes/myapp.yml
    auth-state: .auth/qa.json
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

On failure, trace and video artifacts are uploaded automatically.

### Baseline mode

```bash
# Save current results as the baseline
qaprobe suite probes/myapp.yml --baseline

# Future runs only fail on regressions (stories that were passing now fail)
qaprobe suite probes/myapp.yml
```

## Architecture

```
qaprobe run --url <URL> --story "<story>"
    │
    ├─ Launch headless Chromium (Playwright)
    │   ├─ Video recording ON
    │   └─ Tracing ON
    │
    ├─ Agent loop (Claude Sonnet, up to 40 steps)
    │   ├─ Observe: CDP Accessibility.getFullAXTree → stable element refs
    │   ├─ Decide: LLM picks one tool (click, fill, select, press_key, navigate, scroll, wait, done)
    │   ├─ Act: RefResolver maps ref → Playwright locator (role+name, not CSS)
    │   ├─ SPA debouncing: waits for AX tree to stabilize after actions
    │   └─ Repeat until done or step budget exhausted
    │
    ├─ Verifier (Claude Opus, 1 call, fresh context)
    │   ├─ Sees: story + snapshot history + step log + screenshot + agent verdict
    │   └─ Returns: {goal_achieved, confidence, reasoning}
    │
    └─ Reconcile
        ├─ Both agree pass (high confidence) → PASS
        ├─ Both agree fail → FAIL
        ├─ Both agree pass but low confidence → INCONCLUSIVE
        └─ Disagree → INCONCLUSIVE (needs human review)
```

Output per run: `runs/<timestamp>/{report.json, report.html, trace.zip, video/*.webm}`

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | Anthropic API key |
| `OPENAI_API_KEY` | | OpenAI API key (when using `openai` provider) |
| `QAPROBE_PROVIDER` | `anthropic` | LLM provider: `anthropic` or `openai` |
| `QAPROBE_AGENT_MODEL` | `claude-sonnet-4-5` | Model for the agent loop |
| `QAPROBE_VERIFIER_MODEL` | `claude-opus-4-5` | Model for independent verification |
| `QAPROBE_FAST_MODEL` | `claude-haiku-3-5` | Fast model for simple steps (model routing) |
| `QAPROBE_ROUTING_THRESHOLD` | `20` | Element count below which the fast model is used |
| `QAPROBE_MAX_STEPS` | `40` | Maximum agent steps per run |
| `QAPROBE_BROWSER_TIMEOUT_MS` | `30000` | Playwright action timeout |
| `QAPROBE_DEBOUNCE_POLL_MS` | `200` | SPA debounce polling interval |
| `QAPROBE_DEBOUNCE_STABLE_MS` | `500` | AX tree stable time before snapshot |
| `QAPROBE_DEBOUNCE_TIMEOUT_MS` | `3000` | Maximum debounce wait |
| `QAPROBE_RUNS_DIR` | `runs` | Directory for run artifacts |

## CLI Flags

```
qaprobe run
  --url              URL to test (required)
  --story            Plain-English story (required)
  --auth             Path to storage state JSON
  --max-steps        Max agent steps (default: 40)
  --headed           Show the browser window
  --runs-dir         Artifact directory
  --reveal-secrets   Show fill values in reports (default: masked)
  --no-routing       Disable fast/slow model routing

qaprobe suite <file>
  --auth             Override suite auth config
  --runs-dir         Artifact directory
  --headed           Show the browser window
  --baseline         Save results as baseline
  --reveal-secrets   Show fill values in reports
  --no-routing       Disable model routing

qaprobe a11y
  --url              URL to audit (required)
  --html             Output HTML instead of JSON
  --auth             Path to storage state JSON

qaprobe login
  --url              Login page URL (required)
  --save             Path to save state (default: .auth/state.json)

qaprobe init           Scaffold probes/ directory
qaprobe record         Record interactions and generate a story
qaprobe install        Install Playwright Chromium
```

## Suite YAML Reference

```yaml
name: my-app
base_url: http://localhost:3000

auth:
  storage_state: .auth/state.json

allowed_origins:
  - http://localhost:3000
  - https://api.myapp.com

reveal_fields:
  - inp:username@form

macros:
  login_as: "Go to /login, fill {{1}} in username, fill {{2}} in password, click Login"

stories:
  - name: story_name
    path: /page
    story: "Description of what should happen"
    depends_on: other_story_name  # optional
```

## Why This Exists

Traditional E2E tests require selectors, test IDs, and fixture setup. They're brittle and slow to write. QAProbe uses the **accessibility tree** — the same structure screen readers use — so it's resilient to visual changes and produces a11y findings as a free side-effect.

| Feature | QAProbe | Traditional E2E | Other AI QA |
|---|---|---|---|
| Test language | Plain English | Code (Cypress/Playwright DSL) | Mixed |
| Target | Any URL | Requires test harness | Varies |
| Setup on target | None — just a URL | Test IDs, selectors, fixtures | Agents / SDKs |
| Observation | Accessibility tree (CDP) | DOM / CSS selectors | DOM / screenshots |
| Verification | Independent second model | Assertion code | Self-reported |
| Verdict | Three-way (pass/fail/inconclusive) | Binary | Binary |
| A11y audit | Free on every run | Separate tool | None |
| Artifacts | Video + trace + HTML report | Screenshots on failure | Varies |
| Multi-provider | Anthropic + OpenAI | N/A | Single vendor |

## Examples

See the [`examples/`](examples/) directory for suite files you can run immediately:

- [`example_com.yml`](examples/example_com.yml) — basic tests against example.com
- [`todomvc.yml`](examples/todomvc.yml) — tests against a public TodoMVC React app
- [`hackernews.yml`](examples/hackernews.yml) — tests against Hacker News

## License

MIT
