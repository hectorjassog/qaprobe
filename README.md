# qaprobe

Agentic QA for web apps — local or deployed. Give it a URL and a plain-English user story. It drives a real browser with Claude, records video, and has a second model independently verify the result. Every run also produces an accessibility audit for free.

Works against anything with a URL: `localhost` dev servers, staging environments, production. No setup on the target app — if you can open it in a browser, QAProbe can test it.

## Install

```bash
pip install qaprobe
playwright install chromium
```

## Usage

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# Test your local dev server
qaprobe run --url http://localhost:3000 --story "Add an item to the cart and verify the total updates"

# Test staging before a deploy
qaprobe run --url https://staging.myapp.com --story "Log in and verify the dashboard loads"

# Test any public site
qaprobe run --url https://example.com --story "Click 'More information' and verify I land on IANA's site"
```

## Suite runner

```yaml
# probes/myapp.yml
base_url: http://localhost:3000
auth:
  storage_state: .auth/qa.json
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

## Auth

```bash
qaprobe login --url https://myapp.com/login --save .auth/state.json
qaprobe run --url https://myapp.com/dashboard --story "..." --auth .auth/state.json
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
    │   ├─ Observe: CDP Accessibility.getFullAXTree → compact element list with refs
    │   ├─ Decide: Claude picks one tool (click, fill, select, press_key, navigate, scroll, wait, done)
    │   ├─ Act: RefResolver maps ref → Playwright locator (role+name, not CSS)
    │   └─ Repeat until done or step budget exhausted
    │
    ├─ Verifier (Claude Opus, 1 call, fresh context)
    │   ├─ Sees: story + final snapshot + step history + agent verdict
    │   └─ Returns: {goal_achieved, confidence, reasoning}
    │
    └─ Reconcile
        ├─ Both agree pass → PASS
        ├─ Both agree fail → FAIL
        └─ Disagree → INCONCLUSIVE (needs human review)
```

Output per run: `runs/<timestamp>/{report.json, report.html, trace.zip, video/*.webm}`

## Why this exists

Traditional E2E tests require selectors, test IDs, and fixture setup. They're brittle and slow to write. QAProbe uses the **accessibility tree** — the same structure screen readers use — so it's resilient to visual changes and produces a11y findings as a free side-effect.

| Feature | QAProbe | Traditional E2E |
|---|---|---|
| Test language | Plain English | Code (Cypress/Playwright DSL) |
| Setup on target | None — just a URL | Test IDs, selectors, fixtures |
| Verification | Independent second model | Assertion code |
| A11y audit | Free on every run | Separate tool |

## License

MIT
