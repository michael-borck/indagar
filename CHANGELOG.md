# Changelog

All notable changes to Indagar are documented here. The format follows Keep a
Changelog, and the project uses semantic versioning.

## [0.6.3] - 2026-11-21

### Desktop

- Sign and notarize the Apple Silicon macOS desktop app with the shared App
  Store Connect credentials.
- Download pinned `uv` into app data on first run instead of shipping live
  Mach-O sidecars; the wheel remains bundled.
- Keep the first-run Python engine setup from 0.6.2.

## [0.6.2] - 2026-11-21

### Desktop

- Bundle `uv` and the Indagar wheel in the desktop app.
- Create an app-local Python environment on first run and reinstall when the
  app version changes.
- Add a setup window with installation progress.
- Keep automatic engine upgrades in step with desktop auto-updates.
- No system Python or separate Indagar install is required for the packaged
  app. First-time setup needs network access for Python and dependencies.

## [0.6.1] - 2026-11-21

### Fixed

- Load `INDAGAR_MEDIA` and `INDAGAR_MEDIA_ORDER` from the environment.

### Desktop

- Electron-builder packaging for macOS (universal), Windows (NSIS), and Linux
  (AppImage).
- GitHub release workflow via the shared `app-hq` Electron workflow.
- Landing page with platform detection and direct release-asset downloads.
- `electron-updater` update checks in packaged builds.

## [0.6.0] - 2026-11-21

### Added

- Optional Tavily and Exa provider-native search adapters.
- YouTube search and transcript reading via yt-dlp, with a `media` extra.
- Podcast episode search through the iTunes Search API.
- `indagar media` command and `research --media`.
- Media toggle in the web UI and media metadata in runs.
- Electron desktop shell under `desktop/`, with server startup, health checks,
  external-link handling, and clean shutdown.
- Tests for native providers, media search, transcript parsing, and media
  integration.

## [0.5.0] - 2026-11-21

### Added

- OpenAlex, Crossref, and arXiv academic search providers, plus optional
  Semantic Scholar support.
- `indagar academic` command for direct academic search.
- Academic results merged with web results in deep research, with
  `--no-academic` and an API/UI toggle.
- Publication year and author metadata on sources.
- Tests for academic providers, academic-only research, and metadata.

## [0.4.0] - 2026-11-21

### Added

- Source type and confidence labels for academic, institution, news,
  practitioner, media, and web sources.
- Bounded concurrent source reading and extraction (`INDAGAR_CONCURRENCY`).
- Checkpointed deep-research runs with resume support in the CLI, API, and web
  history.
- DOCX and PDF exports in addition to Markdown and JSON.
- Web export buttons and resumable-run history entries.
- Tests for checkpoints, resume, concurrency, source labels, and document
  exports.

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
