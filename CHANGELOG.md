# Changelog

All notable changes to Indagar are documented here. The format follows Keep a
Changelog, and the project uses semantic versioning.

## [0.3.0] - 2026-11-21

### Added

- Local FastAPI service with background research jobs and SSE progress.
- Web UI for question/budget input, provider status, live timeline, history,
  stop, report, source inspector, citations, run details, and usage.
- Markdown and JSON downloads from the web UI.
- `indagar serve` command and optional `web` extra.
- API and job-manager tests with fake runners and a TestClient.

## [0.2.1] - 2026-11-21

### Added

- `indagar estimate` and `research --dry-run` for offline pre-run budgets.
- Optional input/output cost rates for dollar estimates.
- LLM retry/backoff on `429`, `5xx`, and transport errors, with `Retry-After`.
- Shared minimum interval between LLM calls.
- Tests for retries, rate limiting, estimates, and retry/cost settings.

### Changed

- `indagar doctor` reports retry count and minimum request interval.

## [0.2.0] - 2026-11-21

### Added

- Full Phase 1 loop behind `indagar research --llm`: LLM planning, page
  reading, verbatim quote extraction, a bounded gap check, and synthesis.
- Firecrawl, simple HTTP, and fallback readers with source text truncation.
- Citation-checked synthesis that rejects unknown IDs and falls back to a
  grounded evidence table.
- Anthropic Messages and OpenAI-compatible LLM adapters.
- Provider selection plus per-role planner, reader, and writer models.
- `indagar llm` smoke-test command, with JSON mode and token usage.
- Citation model and ledger with stable IDs, dedupe, source grouping, and
  Markdown rendering.
- Citation, source-read, and per-model usage sections in reports.
- Tests for request shaping, responses, errors, provider selection, readers,
  extraction, gap checks, synthesis, citations, usage, and the full loop.

### Changed

- `indagar doctor` now reports the selected LLM provider, role models, and
  the LLM token budget.
- The search user agent follows the package version.

## [0.1.0] - 2026-11-21

### Added

- Phase 0 CLI skeleton: `doctor`, `search`, and `research`.
- Firecrawl, Brave, Serper, and SearXNG search adapters.
- Ordered fallback, over-fetch, URL normalisation, dedupe, and a 10-minute
  query cache.
- Deterministic sub-question planner and a cited source dossier.
- Run JSON and Markdown storage.
- Tests for the search chain, planner, and research loop.
