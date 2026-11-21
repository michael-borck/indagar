# Indagar — design specification

**Status:** Phase 0 skeleton
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

Model roles:

| Role | Job | Default shape |
|---|---|---|
| Planner | Sub-questions, search terms, gap checks | Cheap, structured output |
| Reader/extractor | Notes and claims from one source | Cheap/local, chunked |
| Synthesizer | Final report with citations | Best affordable model |

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
  cli.py            Typer commands: doctor, search, research
  config.py         Environment settings and provider status
  models.py         Source, SubQuestion, ResearchPlan, SearchOutcome, Run
  store.py          Run JSON + Markdown storage
  search/
    base.py         SearchProvider protocol and SearchError
    providers.py    Firecrawl, Brave, Serper, SearXNG
    chain.py        Ordered fallback, dedupe, cache
  research/
    planner.py      Deterministic Phase 0 planner
    loop.py         Search, collect, dedupe, dossier
```

Phase 1 adds `providers/` for LLMs, `research/extract.py`,
`research/gaps.py`, `research/synthesize.py`, and a citation ledger.

## 9. Interfaces

### CLI (Phase 0)

```bash
indagar doctor
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
