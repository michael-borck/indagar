# Changelog

All notable changes to Indagar are documented here. The format follows Keep a
Changelog, and the project uses semantic versioning.

## [0.2.0] - 2026-11-21

### Added

- Anthropic Messages and OpenAI-compatible LLM adapters.
- Provider selection plus per-role planner, reader, and writer models.
- `indagar llm` smoke-test command, with JSON mode and token usage.
- Citation model and ledger with stable IDs, dedupe, source grouping, and
  Markdown rendering.
- Citation section in dossiers, including an empty state.
- Tests for request shaping, responses, errors, provider selection, and
  citations.

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
