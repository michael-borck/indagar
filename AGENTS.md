# Indagar — agent notes

## Commands

```bash
uv venv
source .venv/bin/activate
uv pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest -q
indagar doctor
indagar llm "Say hello" --role writer
indagar research "What is X?" --llm --depth 0 --max-sources 3
```

## Invariants

- Search providers are ordered. One provider failure never fails the chain.
- Every run records provider attempts, source URLs, and sub-questions.
- No API keys, tokens, or secrets are written to run records or reports.
- `research` without `--llm` stays retrieval-only. `research --llm` is the
  full Phase 1 loop and must fail clearly when no provider or model is set.
- Every citation needs a source and a non-empty quote. Extraction must verify
  that the quote actually appears in the source text; drop it otherwise.
- Synthesis may cite only ledger IDs. Unknown IDs are a hard error and trigger
  the evidence-table fallback.
- Do not store raw LLM prompts or provider payloads in run records. Store the final report, citations, source-read status, and usage.
- Web and media sources are not peer-reviewed and must not be labelled as such.
- Keep the CLI flow: `doctor` is offline, `search` is retrieval-only, `research`
  writes a run record and a report or dossier.
