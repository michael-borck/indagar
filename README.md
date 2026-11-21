# Indagar

**Deep research from the command line.**

Indagar asks a question, plans sub-questions, searches multiple sources, reads
what it finds, and produces a cited research report or a source dossier. The name is Spanish for
*to investigate, inquire, or probe*.

Phase 1 core loop is implemented. `research` is retrieval-only by default;
adding `--llm` turns on LLM planning, source reading, grounded quote
extraction, a bounded gap check, and citation-checked synthesis.

## Install

```bash
uv pip install indagar
# or: pip install indagar
```

## Quick start

```bash
git clone https://github.com/michael-borck/indagar.git
cd indagar
uv venv
source .venv/bin/activate
uv pip install -e '.[dev]'

indagar doctor
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
```

If the checkout is on an exFAT drive, create the virtual environment on a
local disk instead: `uv venv ~/.venvs/indagar`.

The `research` command writes a Markdown report and a JSON run record under
`runs/`. Every source keeps its URL, provider, and sub-question. With `--llm`,
quotes are checked against the source text, citations are validated before the
report is accepted, and per-model token usage is recorded. `--depth 0` disables
follow-up rounds; the default is one.

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

## Configuration

Copy `.env.example` to `.env` and set the providers you have.

| Variable | Purpose |
|---|---|
| `FIRECRAWL_URL` | Self-hosted or cloud Firecrawl base URL, e.g. `http://localhost:3002` |
| `FIRECRAWL_API_KEY` | Optional key when Firecrawl is behind an auth gate |
| `BRAVE_API_KEY` | Brave Search API key |
| `SERPER_API_KEY` | Serper API key |
| `SEARXNG_URL` | Self-hosted SearXNG base URL |
| `INDAGAR_SEARCH_ORDER` | Provider order. Default `firecrawl,brave,serper,searxng` |
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
- [ ] Resume, concurrency, and web UI
- [ ] Desktop shell
- [ ] Academic, podcast, and video sources

PyPI has `0.2.0`, which includes the Phase 1 core loop. Phase 2 is next.

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
