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
indagar academic "photosynthesis" --limit 5
indagar media "photosynthesis" --limit 5
indagar llm "Say hello" --role writer
indagar research "What is X?" --llm --depth 0 --max-sources 3
indagar estimate "What is X?" --max-sources 3 --depth 0
indagar research "What is X?" --llm --dry-run
indagar research --resume <run-id> --llm
indagar serve --host 127.0.0.1 --port 8765
node --check src/indagar/web/static/app.js
node --check desktop/main.js
node --check desktop/preload.js
INDAGAR_DESKTOP_SMOKE=1 INDAGAR_BIN="$(which indagar)" \
  desktop/node_modules/.bin/electron desktop
cd desktop && npm run dist
```


## Invariants

- Search providers are ordered. One provider failure never fails the chain.
- Every run records provider attempts, source URLs, and sub-questions.
- No API keys, tokens, or secrets are written to run records or reports.
- `research` without `--llm` stays retrieval-only. `research --llm` is the
  full Phase 1 loop and must fail clearly when no provider or model is set.
- Every citation needs a source and a non-empty quote. Extraction must verify
  that the quote actually appears in the source text; drop it otherwise.
- Source type and confidence labels are URL heuristics, not verification.
  Never describe a web or media source as peer-reviewed. Academic search
  results are academic sources, not a systematic review.
- Checkpoints contain sources, quotes, and usage only; never API keys or raw
  prompts. Resume must preserve citation deduplication.
- Synthesis may cite only ledger IDs. Unknown IDs are a hard error and trigger
  the evidence-table fallback.
- Do not store raw LLM prompts or provider payloads in run records. Store the final report, citations, source-read status, and usage.
- Retry only transient failures (`408`, `425`, `429`, `5xx`, transport errors) and honour `Retry-After`.
- Estimates are rough upper bounds. Cost estimates use user-supplied per-million-token rates, not built-in pricing.
- Web and media sources are not peer-reviewed and must not be labelled as such.
- Keep the CLI flow: `doctor` is offline, `search` is retrieval-only, `research`
  writes a run record and a report or dossier.
- The web server binds `127.0.0.1` by default and has no auth. Do not expose it
  to untrusted networks without warning the user. The desktop shell is
  source-only and assumes Indagar is installed.
- Media transcripts may be unavailable; never invent transcript text. Media
  sources are low confidence.
- Desktop release builds run on `v*` tags via the shared app-hq Electron
  workflow. Direct download links use fixed asset names under
  `releases/latest/download/`.
