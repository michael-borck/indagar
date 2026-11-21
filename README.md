# Indagar

**Deep research from the command line.**

Indagar asks a question, plans sub-questions, searches multiple sources, reads
what it finds, and produces a cited research dossier. The name is Spanish for
*to investigate, inquire, or probe*.

This repository is the Phase 0 skeleton: a working CLI, a multi-provider search
chain, a deterministic research plan, and a source dossier. LLM planning,
extraction, and synthesis are the next phase.

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
| `ANTHROPIC_API_KEY` | Anthropic key for the next LLM phase |
| `OPENAI_API_KEY` | OpenAI-compatible key |
| `OPENAI_BASE_URL` | OpenAI-compatible base URL, including Ollama/LM Studio |
| `INDAGAR_MAX_SOURCES` | Sources per run. Default `12` |
| `INDAGAR_MAX_SECONDS` | Wall-clock budget. Default `300` |
| `INDAGAR_SEARCH_LIMIT` | Results requested per sub-question. Default `8` |

`indagar doctor` shows what is configured.

## Status

- [x] CLI with `doctor`, `search`, and `research`
- [x] Firecrawl, Brave, Serper, and SearXNG adapters
- [x] Ordered fallback, over-fetch, URL dedupe, and a 10-minute cache
- [x] Deterministic research plan and cited source dossier
- [ ] LLM planner, claim extraction, and synthesis
- [ ] Web UI and desktop shell
- [ ] Academic, podcast, and video sources

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
