# Indagar — design specification

**Status:** Phase 1 in progress
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

Academic records are verified separately. Web and media sources are never
presented as peer-reviewed.

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

Phase 0 uses a deterministic planner and stops after source collection. LLM
planning, extraction, and synthesis are Phase 1.

## 5. Search providers

Ordered fallback:

1. Firecrawl (`/v2/search`, self-hosted or cloud)
2. Brave Search
3. Serper
4. SearXNG

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
empty quotes, dedupes identical evidence, and renders a Markdown table. Raw LLM
prompts and responses are not written to run records; only the resulting
citations, models, and token counts should be.

## 7. Budgets and rate limits

Every run has explicit caps:

- `max_depth` follow-up rounds
- `max_sources` total sources
- `max_seconds` wall clock
- `max_tokens` per model call and per run
- `concurrency` 2-4 by default

Controls:

- Per-provider token-bucket rate limiter and exponential backoff.
- Search and page caches.
- Small/local model for extraction and summarisation.
- Stop and resume: a run is a saved state, not a single function call.
- Visible estimate before a run and actual usage after it.

Deep research is mostly a scheduling and grounding problem. Treat every network
call as budgeted.

## 8. Architecture

```
src/indagar/
  cli.py            Typer commands: doctor, llm, search, research
  config.py         Environment settings and provider status
  models.py         Source, Citation, SubQuestion, ResearchPlan, SearchOutcome, Run
  citations.py      Citation ledger, dedupe, Markdown rendering
  store.py          Run JSON + Markdown storage
  llm/
    base.py         LLMProvider protocol, response, errors
    anthropic.py    Anthropic Messages adapter
    openai_compatible.py  OpenAI Chat Completions adapter
    factory.py      Provider and role-based model selection
  search/
    base.py         SearchProvider protocol and SearchError
    providers.py    Firecrawl, Brave, Serper, SearXNG
    chain.py        Ordered fallback, dedupe, cache
  research/
    planner.py      Deterministic Phase 0 planner
    loop.py         Search, collect, dedupe, dossier
```

Phase 1 still adds `research/extract.py`, `research/gaps.py`, and
`research/synthesize.py`. The provider layer and citation ledger are done.

## 9. Interfaces

### CLI (current)

```bash
indagar doctor
indagar llm "prompt" --role writer
indagar search "question" --limit 8
indagar research "question" --max-sources 12 --out report.md
```

### Web UI (Phase 2)

- Question, budget, provider status.
- Live progress: plan, searches, sources read, gaps, synthesis.
- Source inspector with snippet, type, confidence, and citation.
- Report view and Markdown/DOCX/PDF export.
- Pause, resume, stop.
- Cost and rate-limit panel.

### Desktop (Phase 3)

Electron or Tauri shell around the local FastAPI server, with the same web UI.
Reuse the Winnow/HoneyGuide/Curriculum Curator shell pattern.

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
| 1 | LLM planner, reader/extractor, gap loop, synthesis, citation ledger, cost panel |
| 2 | Web UI, resume, source inspector, exports |
| 3 | Desktop shell, academic APIs, podcasts/videos, provider-native search as an option |

## 12. Phase 0 acceptance

- `indagar doctor` reports configured search and LLM providers.
- `indagar search` uses the ordered chain and reports attempts.
- `indagar research` writes a Markdown dossier and JSON run record.
- No provider key is required for tests.
- `ruff check`, `ruff format --check`, and `pytest` pass.

## 13. Phase 1 acceptance

- `indagar llm` works with Anthropic and OpenAI-compatible endpoints.
- Provider and model selection is role-aware and fails clearly when unset.
- The citation ledger rejects empty quotes and dedupes identical evidence.
- Dossiers render a citation section, including an empty state.
- Raw prompts, responses, and API keys never enter run records.
- Tests cover request shaping, responses, errors, and citation behaviour.
- `ruff check`, `ruff format --check`, and `pytest` pass.
