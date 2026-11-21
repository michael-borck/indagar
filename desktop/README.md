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

```bash
npm run dist
```

`electron-builder.yml` builds a universal macOS DMG/ZIP, a Windows NSIS
installer, and a Linux AppImage. The GitHub `Desktop release` workflow runs on
`v*` tags, publishes the assets, and uploads `latest*.yml` for auto-update.

Packaged builds check GitHub releases every six hours. macOS auto-update
requires a signed build; add `APPLE_CERTIFICATE` and
`APPLE_CERTIFICATE_PASSWORD` repository secrets and the release workflow signs
the app. Windows and Linux update unsigned builds but still show OS security
warnings. The app is still a shell around the installed `indagar` command, not a
bundled Python distribution.
