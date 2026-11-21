# Indagar desktop

An Electron shell around the local Indagar FastAPI server.

## Run

```bash
pip install 'indagar[web,media]'
cd desktop
npm install
npm start
```

The shell finds a free local port, starts `indagar serve`, waits for
`/api/health`, then opens the web UI in a native window. Closing the window
stops the server.

If `indagar` is not on `PATH`, point the shell at it:

```bash
INDAGAR_BIN=/path/to/venv/bin/indagar npm start
```

The server binds `127.0.0.1` and has no authentication. Do not expose it to an
untrusted network.

## Packaging

This is a source shell, not a bundled Python distribution. Packaging needs to
bundle a Python environment or install Indagar on the target machine. Add
`electron-builder` later for a signed `.app`/`.dmg`.
