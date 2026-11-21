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
```

## Invariants

- Search providers are ordered. One provider failure never fails the chain.
- Every run records provider attempts, source URLs, and sub-questions.
- No API keys, tokens, or secrets are written to run records or reports.
- Phase 0 does not call an LLM. `research` collects and dedupes sources.
- Web and media sources are not peer-reviewed and must not be labelled as such.
- Keep the CLI flow: `doctor` is offline, `search` is retrieval-only, `research`
  writes a run record and dossier.
