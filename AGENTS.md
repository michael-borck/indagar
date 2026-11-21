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
```

## Invariants

- Search providers are ordered. One provider failure never fails the chain.
- Every run records provider attempts, source URLs, and sub-questions.
- No API keys, tokens, or secrets are written to run records or reports.
- `research` still collects and dedupes sources; do not make it call an LLM
  until the Phase 1 loop is wired.
- `indagar llm` is the only command that calls a model for now. It must fail
  clearly when no provider or model is configured.
- Every citation needs a source and a non-empty quote. Never fabricate one.
- Do not store raw LLM prompts or responses in run records.
- Web and media sources are not peer-reviewed and must not be labelled as such.
- Keep the CLI flow: `doctor` is offline, `search` is retrieval-only, `research`
  writes a run record and dossier.
