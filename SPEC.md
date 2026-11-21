# Indagar — design specification

**Status:** Phase 3 complete (source desktop shell)
**Name:** Indagar (Spanish: to investigate, inquire, probe)
**Licence:** MIT

## 1. Vision

Turn a question into a researched report with a transparent trail:

1. Plan the question into sub-questions.
2. Search multiple providers.
3. Read the sources.
4. Extract notes and claims with source spans.
5. Find gaps and run focused follow-up rounds.
6. Synthesize a cited report.
7. Save the run so it can be inspected, resumed, or replayed.

The user should always be able to see what was searched, what was read, what
was cited, and what it cost.

## 2. Non-goals

- A systematic review engine. Winnow owns that.
- A NotebookLM clone over user-supplied sources. Open Notebook owns that.
- Provider-native deep research lock-in. The loop is ours so citations, budgets,
  and source policy stay portable.
- A general chat client.
- Scraping behind logins, paywalls, or CAPTCHAs.

## 3. Source model

Sources are not equal. Every source carries a type and a confidence label.

| Type | Examples | Default confidence |
|---|---|---|
| `academic` | OpenAlex, Crossref, Semantic Scholar, arXiv | High |
| `institution` | Government, university, standards body | High |
| `news` | Reputable outlet with a date and byline | Medium |
| `practitioner` | Practitioner blog, vendor report, consultancy | Low to medium |
| `media` | Podcast, video, interview | Low to medium, transcript required |
| `web` | General page | Low until checked |

Academic records are fetched from OpenAlex, Crossref, arXiv, and optional
Semantic Scholar. Venue and peer-review verification remains separate. Web and
media sources are never presented as peer-reviewed. Source type and confidence
labels are URL heuristics implemented in `classify.py`; they are routing hints,
not checks. Sources carry publication year and author metadata when available.

## 4. Research loop

```
question
  -> plan sub-questions
  -> for each sub-question
       -> search chain
       -> read / extract
       -> notes + claims + source spans
  -> gap check
  -> 0-2 follow-up rounds
  -> synthesize report
  -> save run
```

`indagar research` without `--llm` uses the deterministic planner and stops
after source collection. `indagar research --llm` runs the full loop: planner,
search, read, extract, gap check, and synthesis. A planner failure falls back
to the deterministic plan; extraction failures skip a source; synthesis with
unknown citations falls back to the evidence table.

## 5. Search providers

Ordered fallback:

1. Firecrawl (`/v2/search`, self-hosted or cloud)
2. Brave Search
3. Serper
4. SearXNG

Academic tier (keyless unless noted):

1. OpenAlex
2. Crossref
3. arXiv
4. Semantic Scholar, with `SEMANTIC_SCHOLAR_API_KEY`

Academic results are merged with web results, not used as fallback. They are
labelled `academic` / `high confidence`, carry year and authors, and can be
disabled with `INDAGAR_ACADEMIC=false` or `--no-academic`.

Provider-native search is optional: Tavily and Exa join the ordered web chain
when their keys are set. They are not required and do not replace the portable
loop.

Media tier (opt-in, `INDAGAR_MEDIA`):

- YouTube search and transcript reading via yt-dlp (`media` extra)
- Podcast episode search through the iTunes Search API
- Media sources are low confidence; transcripts may be unavailable

Rules:

- Over-fetch `limit * 2`, filter invalid URLs, dedupe by normalised URL, then
  slice.
- Stop at the first provider with usable results.
- Record every attempt: provider, status, count, latency, error.
- Cache identical queries for 10 minutes.
- Never let one provider failure fail the run.
- A keyless self-hosted Firecrawl or SearXNG is a valid only provider.

## 6. LLM providers

Two adapters cover the practical surface:

- **Anthropic native** (`/v1/messages`).
- **OpenAI-compatible** (`/v1/chat/completions`), covering OpenAI, Groq,
  Together, OpenRouter, Ollama, LM Studio, vLLM, DeepSeek, Mistral, and
  Gemini's OpenAI-compatible endpoint.

A Google Gemini native adapter is optional and only worth adding for native
grounding or citations.

Both adapters are implemented in `src/indagar/llm/`. Provider selection is
explicit (`INDAGAR_LLM_PROVIDER`) or the first configured provider. Model IDs
are never hard-coded: a role falls back to `INDAGAR_LLM_MODEL`, and the run
fails clearly if no model is set.

Model roles:

| Role | Job | Default shape |
|---|---|---|
| Planner | Sub-questions, search terms, gap checks | Cheap, structured output |
| Reader/extractor | Notes and claims from one source | Cheap/local, chunked |
| Synthesizer | Final report with citations | Best affordable model |

The citation ledger is an ordered, deduplicated list of claims. Every entry has
a stable ID, the source URL and title, a non-empty quote, an optional locator
(page, section, or timestamp), the sub-question, and a note. The ledger refuses
empty quotes, dedupes identical evidence, and renders a Markdown table. Raw
prompts and provider envelopes are not written to run records; the run stores
the final report, citations, source-read status, models, and token counts.

## 7. Budgets and rate limits

Every run has explicit caps:

- `max_depth` follow-up rounds
- `max_follow_ups` questions per gap check
- `max_sources` total sources
- `max_seconds` wall clock
- `max_tokens` per model call and per run
- `max_content_chars` per source and `max_claims` per source
- `concurrency` source reads, default `2` and capped at `8`

Controls:

- LLM requests retry on `429`, `5xx`, and transport failures with exponential
  backoff, jitter, and `Retry-After` support.
- A shared minimum interval spaces calls across the planner, reader, and writer
  roles (`INDAGAR_LLM_MIN_INTERVAL`).
- Search results and identical queries are cached; page-level caching is still
  to come.
- Small/local model for extraction and summarisation.
- Stop and resume: a run writes checkpoints after planning, searches, read
  batches, and gap rounds; `--resume` and the web history continue from the
  latest state.
- A pre-run estimate reports upper-bound searches, sources, calls, tokens, and
  an optional dollar cost from user-supplied per-million-token rates.
- Actual token usage is recorded per provider/model after the run.

Deep research is mostly a scheduling and grounding problem. Treat every network
call as budgeted.

## 8. Architecture

```
src/indagar/
  cli.py            Typer commands: doctor, llm, estimate, search, research, serve
  config.py         Environment settings and provider status
  models.py         Source, Citation, SubQuestion, ResearchPlan, ReadAttempt,
                    ModelUsage, SearchOutcome, Run
  citations.py      Citation ledger, dedupe, Markdown rendering
  classify.py       Source type and confidence heuristics
  exports.py        DOCX and PDF export
  store.py          Run JSON + Markdown storage
  usage.py          Per-model call and token accounting
  estimate.py       Pre-run tokens, calls, and optional cost estimate
  rate_limit.py     LLM retry/backoff and request spacing
  llm/
    base.py         LLMProvider protocol, response, errors
    anthropic.py    Anthropic Messages adapter
    openai_compatible.py  OpenAI Chat Completions adapter
    factory.py      Provider and role-based model selection
  search/
    base.py         SearchProvider protocol and SearchError
    providers.py    Firecrawl, Brave, Serper, SearXNG
    academic.py     OpenAlex, Crossref, arXiv, Semantic Scholar
    media.py        YouTube and podcast search
    chain.py        Ordered fallback, dedupe, cache
  web/
    app.py          FastAPI routes, SSE, static UI
    jobs.py         Background jobs, events, history, cancel, resume
    static/         index.html, app.js, styles.css
desktop/
  main.js           Electron shell: find port, start server, open window
  preload.js        Minimal context bridge
  research/
    planner.py      Deterministic and LLM planners
    reader.py       Firecrawl, simple HTTP, and fallback readers
    media_reader.py YouTube transcript reader
    extract.py      Verbatim claim extraction with source checks
    gaps.py         Bounded follow-up question check
    synthesize.py   Citation-checked narrative
    loop.py         Phase 0 search, collect, dedupe, dossier
    deep.py         Full planner -> read -> extract -> gap -> synthesize loop
    checkpoint.py   Checkpoint state, save/load, resumable runs
    json_utils.py   Tolerant JSON object parsing
```

Phases 1-3 are implemented in source form. Bundled/signed desktop installers
and systematic-review-grade verification remain future work.

## 9. Interfaces

### CLI (current)

```bash
indagar doctor
indagar llm "prompt" --role writer
indagar academic "question" --limit 8
indagar media "question" --limit 8
indagar estimate "question" --max-sources 12 --depth 1
indagar search "question" --limit 8
indagar research "question" --max-sources 12 --out report.md
indagar research "question" --llm --depth 1 --max-sources 12
indagar research "question" --llm --dry-run
indagar research "question" --llm --no-academic
indagar research "question" --llm --media
indagar research --resume <run-id> --llm
indagar serve --host 127.0.0.1 --port 8765
# desktop: cd desktop && npm install && npm start
```

### Web UI (Phase 2, complete)

- Question, budget, provider status.
- Live progress over SSE: plan, searches, reads, gaps, synthesis.
- Report view, source inspector, citations, run details, and usage.
- Source type and confidence labels.
- Markdown, JSON, DOCX, and PDF export.
- Job history, stop, and resume from checkpoints.
- Bounded concurrent reads.
- Academic source toggle and metadata.
- Media source toggle and metadata.

### Desktop (Phase 3, source shell)

Electron shell under `desktop/`: bundles `uv` and the Indagar wheel, creates
an app-local Python 3.12 environment on first run, starts `indagar serve`,
waits for `/api/health`, opens the web UI in a native window, routes external
links to the system browser, and stops the server on exit. The engine is
reinstalled when the desktop version changes. Packaging and signing are
separate; mac auto-update needs a signed build.

## 10. Reuse

| Source | Borrow |
|---|---|
| Firecrawl | Search plus scrape, PDF parsing, crawl/map, caching. Deep-research loop: generate queries, search+scrape, analyse, recurse, stop on depth/URLs/time. |
| Minions | Local/cloud split and map-reduce: local chunks and summaries, remote synthesis. |
| Open Notebook | Source processing engines (Firecrawl, Jina, Crawl4AI, simple), Ask strategy -> searches -> partial answers -> final synthesis, citations, notes, duplicate detection. |
| Winnow | CLI, local server, desktop shell, provider abstraction, run database, citation discipline. |
| HoneyGuide | Multi-source retrieval, diversity, source-type labels, verification. |
| Curriculum Curator | Python search router, fallback, cache, key hashing, quota. |

Do not fork these projects. Borrow patterns and keep Indagar thin.

## 11. Phases

| Phase | Scope |
|---|---|
| 0 | Skeleton: CLI, search chain, deterministic plan, source dossier, tests, CI |
| 1 | LLM planner, reader/extractor, gap loop, synthesis, citation ledger, usage panel |
| 2 | Web UI, job history, live progress, source inspector, Markdown/JSON/DOCX/PDF exports, resume |
| 3 | Academic APIs, media sources, provider-native search, Electron desktop shell |

## 12. Phase 0 acceptance

- `indagar doctor` reports configured search and LLM providers.
- `indagar search` uses the ordered chain and reports attempts.
- `indagar research` writes a Markdown dossier and JSON run record.
- No provider key is required for tests.
- `ruff check`, `ruff format --check`, and `pytest` pass.

## 13. Phase 1 acceptance

- `indagar llm` works with Anthropic and OpenAI-compatible endpoints.
- Provider and model selection is role-aware and fails clearly when unset.
- `indagar research --llm` plans, reads, extracts, gap-checks, and synthesizes.
- Extracted quotes must appear in the source text; ungrounded quotes are dropped.
- Synthesis rejects unknown citation IDs and falls back to the evidence table.
- The citation ledger rejects empty quotes and dedupes identical evidence.
- Reports render sources, citations, source-read status, and per-model usage.
- `indagar estimate` and `research --dry-run` report an upper-bound budget
  without calling a provider.
- LLM calls retry transient failures and can be spaced by a shared interval.
- Raw prompts, provider payloads, and API keys never enter run records.
- Tests cover request shaping, responses, errors, retries, rate limiting,
  estimates, readers, extraction, gaps, synthesis, citation validation, and the
  full loop with fakes.
- `ruff check`, `ruff format --check`, and `pytest` pass.

## 14. Phase 2 acceptance

- `indagar serve` starts the local FastAPI service and static UI.
- The UI starts Phase 0 or `--llm` runs and shows provider status.
- Progress streams over SSE; a running job can be stopped and resumed.
- Completed runs are saved, listed in history, and reloadable.
- The UI renders the report, sources, confidence labels, citations, run
  details, and usage.
- Markdown, JSON, DOCX, and PDF exports download from the run.
- Source labels are heuristics and never presented as peer review.
- Bounded concurrency is configurable and respected.
- API tests cover status, estimates, job lifecycle, SSE, cancellation, resume,
  exports, and missing runs.
- `ruff check`, `ruff format --check`, `pytest`, and `node --check` pass.

## 15. Phase 3 acceptance

- `indagar academic` queries OpenAlex, Crossref, and arXiv, plus Semantic
  Scholar when keyed.
- Academic results carry type, confidence, year, and author metadata.
- Deep research merges academic, web, and optional media results.
- `--no-academic` disables the academic tier; `--media` enables media.
- Media search covers YouTube and podcast episodes; YouTube transcripts are
  read from captions when available and never invented.
- Tavily and Exa can join the ordered web chain as native search options.
- The Electron shell starts the local server, opens the UI, and stops the
  server on exit.
- Tests cover academic and native providers, media search, transcript parsing,
  media integration, and desktop JavaScript syntax.
- `ruff check`, `ruff format --check`, `pytest`, and `node --check` pass.
