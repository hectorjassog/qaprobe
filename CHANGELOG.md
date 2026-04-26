# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
