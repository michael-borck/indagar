# Indagar

**Deep research from the command line.**

Indagar asks a question, plans sub-questions, searches multiple sources, reads
what it finds, and produces a cited research dossier. The name is Spanish for
*to investigate, inquire, or probe*.

Phase 1 is in progress. The CLI, multi-provider search chain, LLM provider
adapters, and citation ledger are working. The research loop still runs in
Phase 0 mode until LLM planning, extraction, and synthesis are wired in.

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
```

If the checkout is on an exFAT drive, create the virtual environment on a
local disk instead: `uv venv ~/.venvs/indagar`.

The `research` command writes a Markdown dossier and a JSON run record under
`runs/`. Every source keeps its URL, provider, and sub-question.

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
`--json` to request JSON output. `research` does not call an LLM yet.

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
| `INDAGAR_MAX_SOURCES` | Sources per run. Default `12` |
| `INDAGAR_MAX_SECONDS` | Wall-clock budget. Default `300` |
| `INDAGAR_SEARCH_LIMIT` | Results requested per sub-question. Default `8` |

`indagar doctor` shows what is configured.

## Status

- [x] CLI with `doctor`, `llm`, `search`, and `research`
- [x] Firecrawl, Brave, Serper, and SearXNG adapters
- [x] Ordered fallback, over-fetch, URL dedupe, and a 10-minute cache
- [x] Deterministic research plan and cited source dossier
- [x] Anthropic and OpenAI-compatible LLM adapters with role-based models
- [x] Citation ledger with dedupe, source grouping, and Markdown rendering
- [ ] LLM planner, claim extraction, gap loop, and synthesis
- [ ] Web UI and desktop shell
- [ ] Academic, podcast, and video sources

PyPI has `0.1.0`. The Phase 1 work on `main` is version `0.2.0` and is not
published yet.

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
