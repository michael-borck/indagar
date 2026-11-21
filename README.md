# Indagar

**Deep research from the command line.**

[Website](https://michael-borck.github.io/indagar/) · [PyPI](https://pypi.org/project/indagar/) · [GitHub](https://github.com/michael-borck/indagar)

Indagar asks a question, plans sub-questions, searches multiple sources, reads
what it finds, and produces a cited research report or a source dossier. The name is Spanish for
*to investigate, inquire, or probe*.

Phase 3 is complete. `research` is retrieval-only by default; adding `--llm`
turns on LLM planning, source reading, grounded quote extraction, academic,
web, and optional media sources, a bounded gap check, concurrency, checkpoints,
and citation-checked synthesis. `indagar serve` opens the local web workspace,
and an Electron shell wraps it as a desktop app.

## Install

```bash
uv pip install indagar
# or: pip install 'indagar[web]' to include the local web UI
```

## Quick start

```bash
git clone https://github.com/michael-borck/indagar.git
cd indagar
uv venv
source .venv/bin/activate
uv pip install -e '.[dev]'

indagar doctor
indagar academic "retrieval augmented generation" --limit 5
indagar media "retrieval augmented generation" --limit 5
indagar search "retrieval augmented generation" --limit 5
indagar research "Does retrieval augmented generation reduce hallucination?" \
  --max-sources 10

# Full Phase 1 loop; requires an LLM provider and model.
indagar research "Does retrieval augmented generation reduce hallucination?" \
  --llm --max-sources 10 --depth 1

# See the rough budget before running.
indagar estimate "Does retrieval augmented generation reduce hallucination?" \
  --max-sources 10 --depth 1
indagar research "Does retrieval augmented generation reduce hallucination?" \
  --llm --dry-run
indagar research --resume <run-id> --llm
```

If the checkout is on an exFAT drive, create the virtual environment on a
local disk instead: `uv venv ~/.venvs/indagar`.

The `research` command writes a Markdown report and a JSON run record under
`runs/`. Every source keeps its URL, provider, type, confidence, and
sub-question. With `--llm`, quotes are checked against the source text,
citations are validated before the report is accepted, and per-model token
usage is recorded. Reads are concurrent, and checkpoints let an interrupted run
continue. `--depth 0` disables follow-up rounds; the default is one.

## LLM smoke test

Anthropic:

```bash
export ANTHROPIC_API_KEY="..."
export INDAGAR_LLM_PROVIDER=anthropic
export INDAGAR_LLM_MODEL=claude-sonnet-4-5

indagar llm "In one sentence, what makes a source trustworthy?"
```

A local OpenAI-compatible server such as Ollama or LM Studio:

```bash
export OPENAI_BASE_URL=http://localhost:11434/v1
export INDAGAR_LLM_PROVIDER=openai-compatible
export INDAGAR_LLM_MODEL=llama3.1

indagar llm "In one sentence, what makes a source trustworthy?"
```

Use `--role planner|reader|writer` to exercise a role-specific model, and
`--json` to request JSON output.

The same provider powers the full research loop:

```bash
indagar research "What limits photosynthesis in C4 plants?" --llm --depth 1
```

Planning, extraction, gap checks, and synthesis use the planner, reader, and
writer roles. If synthesis uses an unknown citation ID, Indagar rejects it and
falls back to the grounded evidence table rather than keeping an unverifiable
claim.

## Academic search

Academic providers are keyless by default:

- OpenAlex
- Crossref
- arXiv
- Semantic Scholar, when `SEMANTIC_SCHOLAR_API_KEY` is set

Deep research queries academic providers alongside web providers and merges
the results. Use `--no-academic` to skip them. Sources keep their type,
confidence, publication year, and authors. Set `OPENALEX_MAILTO` for OpenAlex's
polite pool.

## Video and podcasts

Install the media extra for YouTube search and transcript extraction:

```bash
uv pip install 'indagar[media]'
indagar media "photosynthesis" --limit 5
```

Media search is opt-in for research: `indagar research "..." --llm --media`. It
uses YouTube search and transcripts via yt-dlp, plus podcast episodes from the
iTunes Search API. Media sources are labelled low confidence. Podcast pages
fall back to the normal page reader when no transcript is available.

## Provider-native search

Tavily and Exa are optional provider-native search adapters. Set
`TAVILY_API_KEY` or `EXA_API_KEY`, then put them in `INDAGAR_SEARCH_ORDER`.
They join the existing ordered fallback chain.

## Desktop app

Download the installer from the [landing page](https://michael-borck.github.io/indagar/).

The app includes its own Python engine. On first launch it uses bundled `uv` to
download Python 3.12 into the app data folder, installs the bundled Indagar
wheel with the web and media extras, and starts the local server. No system
Python and no separate `pip install indagar` are required. The engine is
reinstalled when the desktop app version changes. First-time setup needs an
internet connection for Python and dependencies.

For development:

```bash
cd desktop
npm install
INDAGAR_BIN="$(which indagar)" npm start
```

Packaged builds check GitHub for updates; macOS auto-update needs a signed
build.

## Web UI

```bash
uv pip install 'indagar[web]'
indagar serve
# open http://127.0.0.1:8765
```

The local UI starts Phase 0 or `--llm` runs, streams progress over SSE, shows
sources, labels, and citations, and exports Markdown, JSON, DOCX, or PDF. A run
can be stopped, and interrupted checkpoints can be resumed from history. The
source inspector is included.

The server binds `127.0.0.1` by default and has no authentication. Use
`--host`/`--port` to change the bind address; do not expose it to an untrusted
network.

## Configuration

Copy `.env.example` to `.env` and set the providers you have.

| Variable | Purpose |
|---|---|
| `FIRECRAWL_URL` | Self-hosted or cloud Firecrawl base URL, e.g. `http://localhost:3002` |
| `FIRECRAWL_API_KEY` | Optional key when Firecrawl is behind an auth gate |
| `BRAVE_API_KEY` | Brave Search API key |
| `SERPER_API_KEY` | Serper API key |
| `SEARXNG_URL` | Self-hosted SearXNG base URL |
| `INDAGAR_SEARCH_ORDER` | Provider order. Default `firecrawl,brave,serper,searxng,tavily,exa` |
| `TAVILY_API_KEY` | Optional Tavily native search key |
| `EXA_API_KEY` | Optional Exa native search key |
| `INDAGAR_ACADEMIC` | Enable academic search. Default `true` |
| `INDAGAR_ACADEMIC_ORDER` | Academic order. Default `openalex,crossref,arxiv,semantic-scholar` |
| `OPENALEX_MAILTO` | Optional email for the OpenAlex polite pool |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional Semantic Scholar key |
| `INDAGAR_MEDIA` | Enable video/podcast search. Default `false` |
| `INDAGAR_MEDIA_ORDER` | Media order. Default `youtube,podcast` |
| `ANTHROPIC_API_KEY` | Anthropic key |
| `ANTHROPIC_BASE_URL` | Anthropic API base. Default `https://api.anthropic.com` |
| `OPENAI_API_KEY` | OpenAI-compatible key |
| `OPENAI_BASE_URL` | OpenAI-compatible base URL, including Ollama/LM Studio |
| `INDAGAR_LLM_PROVIDER` | `anthropic` or `openai-compatible`. Defaults to the first configured |
| `INDAGAR_LLM_MODEL` | Global model ID for every role |
| `INDAGAR_PLANNER_MODEL` | Model for sub-question planning and gap checks |
| `INDAGAR_READER_MODEL` | Model for source extraction |
| `INDAGAR_WRITER_MODEL` | Model for the final synthesis |
| `INDAGAR_LLM_MAX_TOKENS` | Tokens per call. Default `1024` |
| `INDAGAR_LLM_TEMPERATURE` | Sampling temperature. Default `0.2` |
| `INDAGAR_LLM_TIMEOUT` | LLM request timeout in seconds. Default `60` |
| `INDAGAR_LLM_MAX_RETRIES` | Retries on 429/5xx/transport errors. Default `2` |
| `INDAGAR_RETRY_BASE_SECONDS` | Exponential backoff base. Default `0.5` |
| `INDAGAR_LLM_MIN_INTERVAL` | Minimum seconds between LLM calls. Default `0` |
| `INDAGAR_INPUT_COST_PER_MTOK` | Optional input USD per million tokens |
| `INDAGAR_OUTPUT_COST_PER_MTOK` | Optional output USD per million tokens |
| `INDAGAR_MAX_SOURCES` | Sources per run. Default `12` |
| `INDAGAR_MAX_SECONDS` | Wall-clock budget. Default `300` |
| `INDAGAR_SEARCH_LIMIT` | Results requested per sub-question. Default `8` |
| `INDAGAR_CONCURRENCY` | Concurrent source reads. Default `2`, max `8` |
| `INDAGAR_MAX_DEPTH` | Follow-up rounds for `--llm`. Default `1`, max `2` |
| `INDAGAR_MAX_FOLLOW_UPS` | Follow-up questions per gap check. Default `3` |
| `INDAGAR_MAX_CONTENT_CHARS` | Source text sent to the reader model. Default `12000` |
| `INDAGAR_MAX_CLAIMS` | Claims extracted per source. Default `5` |
| `INDAGAR_SYNTHESIS_MAX_TOKENS` | Synthesis output cap. Default `2048` |
| `INDAGAR_READER_TIMEOUT` | Page read timeout in seconds. Default `45` |

`indagar doctor` shows what is configured. `indagar estimate` is offline and
prints a rough upper bound for searches, sources, LLM calls, and tokens. Set
the two cost variables above to add a dollar estimate; rates are user-supplied
and model-specific.

LLM requests retry on `429`, `5xx`, and transport failures with exponential
backoff and `Retry-After` support. `INDAGAR_LLM_MIN_INTERVAL` spaces calls
across the planner, reader, and writer roles.

## Status

- [x] CLI with `doctor`, `llm`, `estimate`, `search`, and `research`
- [x] Firecrawl, Brave, Serper, and SearXNG adapters
- [x] Ordered fallback, over-fetch, URL dedupe, and a 10-minute cache
- [x] Deterministic research plan and cited source dossier
- [x] Anthropic and OpenAI-compatible LLM adapters with role-based models
- [x] LLM planner, source reader, verbatim quote extraction, gap loop, and synthesis
- [x] Citation ledger with dedupe, source grouping, and Markdown rendering
- [x] Per-run source-read and model-usage tables
- [x] Pre-run token/cost estimate, LLM retry/backoff, and request spacing
- [x] Local FastAPI service, job history, live SSE progress, stop, and resume
- [x] Web report, source inspector, citations, usage, and Markdown/JSON/DOCX/PDF export
- [x] Source type and confidence labels; bounded concurrent reading
- [x] Academic APIs: OpenAlex, Crossref, arXiv, and optional Semantic Scholar
- [x] Academic sources merged into deep research with year and author metadata
- [x] Provider-native search options: Tavily and Exa
- [x] Video/podcast search and YouTube transcript extraction
- [x] Electron desktop shell around the local server
- [ ] Bundled/signed desktop installers
- [ ] Academic, podcast, and video sources

PyPI has `0.6.2`. Desktop installers bundle `uv` and the Indagar wheel, create
their own Python environment on first run, and update the engine when the app
updates. macOS auto-update still requires a signed build.

See [SPEC.md](SPEC.md) for the design and roadmap.

## Development

```bash
uv pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest -q
```

## Licence

MIT. See [LICENSE](LICENSE).
