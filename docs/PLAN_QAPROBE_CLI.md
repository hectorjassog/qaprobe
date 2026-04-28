# QAProbe — open-source CLI tool plan

Domain: **qaprobe.com** (available)
PyPI: **qaprobe** (available)
CLI command: **qaprobe**

Standalone repo plan for extracting QAProbe from neltik into a pip-installable, open-source CLI tool.

## What QAProbe is

Agentic QA for web apps — local or deployed. Give it a URL and a plain-English user story. It drives a real browser with Claude, records video, and has a second model independently verify the result. Every run also produces an accessibility audit for free.

Works against anything with a URL: `localhost` dev servers, staging environments, production. No setup on the target app — if you can open it in a browser, QAProbe can test it.

```bash
pip install qaprobe

# Test your local dev server
qaprobe run --url http://localhost:3000 --story "Add an item to the cart and verify the total updates"

# Test staging before a deploy
qaprobe run --url https://staging.myapp.com --story "Log in and verify the dashboard loads"

# Test any public site
qaprobe run --url https://example.com --story "Click 'More information' and verify I land on IANA's site"
```

## Positioning

"Agentic QA that sees your app like a screen reader does."

Not another Selenium wrapper. Not a visual regression tool. QAProbe is functional QA + accessibility auditing via the same mechanism: both the agent and screen readers consume the accessibility tree. Point it at any URL — localhost, staging, production — and describe what a user should be able to do.

### What makes it different

| Feature | QAProbe | Traditional E2E | Other AI QA tools |
|---|---|---|---|
| Test language | Plain English stories | Code (Cypress/Playwright DSL) | Mixed |
| Target | Any URL (localhost, staging, prod) | Requires test harness / config | Varies |
| Setup on target app | None — just a URL | Test IDs, selectors, fixtures | Agents / SDKs |
| Observation model | Accessibility tree (CDP) | DOM / CSS selectors | DOM / screenshots |
| Verification | Independent second model (no self-grading) | Assertion code | Self-reported |
| Verdict system | Three-way (pass/fail/inconclusive) | Binary | Binary |
| A11y audit | Free side-effect of every run | Separate tool (axe, Lighthouse) | None |
| Artifacts | Video + Playwright trace + JSON report | Screenshots on failure | Varies |

### Anti-goals

- **Not a visual regression tool.** That's Percy/Chromatic. QAProbe is functional + a11y.
- **Not a DSL.** Natural-language stories are the point. Don't Gherkin this.
- **Not self-healing selectors.** AX-tree refs degrade gracefully already.

---

## Architecture (current MVP)

Single-file, ~730 LOC. Two external deps: `anthropic`, `playwright`.

```
qaprobe run --url <URL> --story "<story>"
    │
    ├─ Launch headless Chromium (Playwright)
    │   ├─ Video recording ON
    │   └─ Tracing ON
    │
    ├─ Agent loop (Sonnet, up to 40 steps)
    │   ├─ Observe: CDP Accessibility.getFullAXTree → compact element list with refs
    │   ├─ Decide: Claude picks one tool (click, fill, select, press_key, navigate, scroll, wait, set_input_files, done)
    │   ├─ Act: RefResolver maps ref → Playwright locator (role+name, not CSS)
    │   └─ Repeat until `done` or step budget exhausted
    │
    ├─ Verifier (Opus, 1 call, fresh context)
    │   ├─ Sees: story + final snapshot + step history + agent verdict
    │   └─ Returns: {goal_achieved, confidence, reasoning}
    │
    └─ Reconcile
        ├─ Both agree pass → PASS
        ├─ Both agree fail → FAIL
        └─ Disagree → INCONCLUSIVE (needs human review)
```

Output per run: `runs/<timestamp>/{report.json, trace.zip, video/*.webm}`

---

## Repo structure (target)

```
qaprobe/
├── src/
│   └── qaprobe/
│       ├── __init__.py
│       ├── cli.py              # Click/Typer CLI entry point
│       ├── agent.py            # Agent loop (extract from probe.py)
│       ├── verifier.py         # Independent verification
│       ├── browser.py          # Playwright lifecycle, snapshot, RefResolver
│       ├── a11y.py             # Passive a11y audit (new)
│       ├── report.py           # Data models, JSON + HTML report generation
│       ├── suite.py            # YAML suite loader + runner (new)
│       ├── auth.py             # Storage state management (new)
│       └── config.py           # Env vars, defaults, model routing
├── tests/
│   ├── test_snapshot.py        # Unit: AX tree → element list
│   ├── test_ref_resolver.py    # Unit: ref → locator mapping
│   ├── test_verdict.py         # Unit: reconciliation logic
│   ├── test_a11y.py            # Unit: a11y finding detection
│   └── test_cli.py             # Integration: CLI smoke tests
├── pyproject.toml
├── README.md
├── LICENSE                     # MIT
├── CHANGELOG.md
└── .github/
    └── workflows/
        ├── ci.yml              # Lint + test on PR
        └── release.yml         # Publish to PyPI on tag
```

---

## Milestones

### M0 — Extract and package (day 1)

**Goal:** `pip install qaprobe && qaprobe run --url ... --story ...` works identically to the current `python probe.py` invocation.

- [x] Create repo, `pyproject.toml` with `[project.scripts] qaprobe = "qaprobe.cli:main"`
- [x] Split `probe.py` into modules (`agent.py`, `verifier.py`, `browser.py`, `report.py`, `config.py`, `cli.py`)
- [x] Zero behavior changes — just restructure
- [x] Add basic tests for snapshot parsing, ref resolution, verdict reconciliation
- [x] README with install, usage, design notes (adapted from current README)
- [x] MIT license
- [x] CI: lint (ruff) + test (pytest) on PR

**Ship criterion:** `pip install .` from the repo, run against example.com, get a report.

---

### M1 — Cost and speed (day 2)

**Goal:** Cut per-run cost and time roughly in half.

- [x] **Prompt caching.** System prompt + tool defs are identical every step. Add `cache_control: {"type": "ephemeral"}` to `system` and `tools` blocks. ~30 API calls per run, each one saves the cache-miss penalty.
- [x] **Storage-state auth.** `qaprobe login --url <login-page> --save .auth/state.json` — agent logs in once, saves Playwright storage state. `qaprobe run --auth .auth/state.json` reuses it. Eliminates the 7-step login overhead on every authed story.
- [x] **Model routing (optional stretch).** Haiku for trivial steps (low element count + obvious next action), Sonnet for ambiguous ones. Config flag to enable/disable.

**Ship criterion:** A 5-story authed suite that used to cost ~$2.50 and take 5 min now costs ~$1.00 and takes 2.5 min.

---

### M2 — A11y audit (day 2–3)

**Goal:** Every run emits an `a11y_findings` array in the report, even on pass.

- [x] **Passive collection during agent loop.** While driving, silently flag:
  - Inputs with no accessible name
  - Buttons with only icon children (no label)
  - Headings that skip levels (h1 → h3)
  - Images with empty alt text
  - Live regions with empty names
  - Form fields with no associated label
- [ ] **Contrast check** via CDP `DOM.getNodeForLocation` + computed style on elements the agent interacted with (stretch)
- [x] Add `a11y_findings` to `report.json` schema
- [x] CLI flag `--a11y-only` to run a passive audit without a user story (just crawl the page)

**Ship criterion:** Run against a known-bad page, get a non-empty `a11y_findings` array with real issues.

---

### M3 — Suite runner + HTML report (day 3–4)

**Goal:** `qaprobe suite probes/myapp.yml` runs N stories and produces a single HTML report.

- [x] **Suite YAML format:**
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
- [x] **Suite runner:** Parse YAML, resolve `depends_on` ordering, run sequentially (parallel later), aggregate results
- [x] **HTML report:** Single `index.html` per suite run with:
  - Status grid (green/red/yellow per story)
  - Expandable step log per story
  - Inline a11y findings
  - Link to video and trace for each story
- [ ] `qaprobe suite --watch` re-runs on file change (stretch)

**Ship criterion:** Run a 3-story suite, get an HTML report you'd be comfortable attaching to a PR.

---

### M4 — Reliability fixes (day 4–5)

**Goal:** Fix the real bugs encountered during ShipAndFound testing.

- [x] **Stable refs.** Hash `(role, name, parent_path)` into deterministic refs like `btn:save-changes@form.edit`. Refs survive across snapshots so the verifier's history makes sense.
- [x] **Duplicate-name disambiguation.** When `get_by_role(role, name=name)` matches >1 element, encode the DOM index in the ref and use `nth()` on the locator.
- [x] **SPA snapshot debouncing.** After navigation/click, wait for network idle OR AX node count to stabilize before snapshotting. Prevents capturing mid-hydration garbage.
- [x] **Verifier gets full snapshot history.** Feed every post-step snapshot (truncated) to the verifier, not just the final one. Catches transient success indicators (toast messages, banners) that vanish.
- [x] **Screenshots as verifier input.** Attach final screenshot as an image block for visual-adjacent stories.

**Ship criterion:** Re-run the ShipAndFound stories that failed due to ref confusion — they pass now.

---

### M5 — Safety and CI (day 5–6)

**Goal:** Safe enough to run in CI against staging, with results posted to PRs.

- [x] **Origin pinning.** Constrain `navigate` to `base_url`'s origin unless `allowed_origins` is set in the suite file. Prevents runaway agents.
- [x] **Secret masking.** Redact `fill(text=...)` values in reports by default. Allowlist specific fields in suite config.
- [x] **GitHub Action:**
  ```yaml
  - uses: qaprobe/action@v1
    with:
      suite: probes/myapp.yml
      auth-state: .auth/qa.json
  ```
  - Upload trace + video as artifacts only on failure
  - Post HTML report summary as PR comment
  - Exit code 1 on any fail/inconclusive
- [x] **Baseline mode.** `qaprobe suite --baseline` saves current results. Subsequent runs compare against baseline — only regressions from known-green stories block merge.

**Ship criterion:** PR-triggered CI run that posts results as a comment and blocks merge on regressions.

---

### M6 — Multi-provider + DX polish (week 2)

**Goal:** Not locked to Anthropic. Pleasant to use daily.

- [x] **Provider abstraction.** Support OpenAI (`gpt-4.1`), Anthropic, and local models via a provider interface. Agent and verifier can use different providers.
- [x] **`qaprobe record`** — headed browser mode where the user does the flow manually, QAProbe generates the natural-language story from observed events. User edits and commits.
- [x] **Story macros.** `{{login_as("qa-user")}}` expands to a reusable auth preamble defined in the suite file.
- [x] **`qaprobe init`** — scaffold a `probes/` directory with a sample suite YAML and auth setup.
- [x] **Confidence calibration.** If both models agree but verifier confidence is `low`, mark inconclusive.
- [ ] **Deterministic time/random.** Inject fixed clock and RNG seed via CDP for diffable screenshots.

---

## Open questions

1. ~~**Name.**~~ Settled: **qaprobe** — domain (`qaprobe.com`) and PyPI name both available.
2. **LLM cost transparency.** Should the report include token counts and estimated cost per run? Useful for teams evaluating adoption.
3. **Parallel story execution.** Safe if stories are independent (separate browser contexts). Worth adding in M3 or defer to M6?
4. **Plugin system.** Custom actions beyond the built-in tool set (e.g., `check_email_inbox` for verification flows). Too early? Probably. But worth designing the action interface to be extensible from M0.

---

## What NOT to build

Keeping this list explicit to avoid scope creep:

- **Visual regression / screenshot diffing** — that's Percy/Chromatic
- **A DSL or Gherkin layer** — natural language is the interface
- **Self-healing selectors** — AX-tree refs already degrade gracefully
- **A web dashboard** — JSON + HTML reports are the interface until there's demand
- **Multi-tab support** — single tab covers 95% of QA stories
- **File download verification** — upload works, download is a different problem

---

## Launch checklist

- [ ] Register `qaprobe.com`
- [ ] GitHub org or repo: `qaprobe/qaprobe` or personal `hectorjasso/qaprobe`
- [x] Repo created, MIT licensed
- [ ] `pip install qaprobe` works from PyPI
- [x] README with: 30-second install, localhost example, staging example, architecture diagram, "why this exists"
- [x] 3+ example suites (public sites: example.com, TodoMVC, a HN clone)
- [ ] Blog post or thread: "I built an E2E runner that uses the a11y tree — it finds real bugs AND a11y issues as a side effect. Point it at localhost and describe what should work."
- [ ] Post to HN, r/Python, r/webdev, X
