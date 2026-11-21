# Indagar desktop

An Electron shell around the local Indagar FastAPI server.

## Run (development)

```bash
npm install
INDAGAR_BIN="$(which indagar)" npm start
```

For development, `INDAGAR_BIN` uses an existing Indagar command. Without it,
the app looks for the bundled sidecar and creates an app-local Python
environment.

## Bundled engine

Release builds ship the `indagar` wheel under `sidecar/wheel/`. On first
launch, the app downloads a pinned `uv` binary, installs Python 3.12 into the
app data directory, creates a venv, and installs the bundled wheel with `web`
and `media` extras. The engine version marker makes the app reinstall the
engine after a desktop update. First-time setup needs an internet connection.

## Packaging

```bash
python -m build --wheel --outdir sidecar/wheel ..
npm run dist
```

`electron-builder.yml` builds an Apple Silicon macOS DMG/ZIP, a Windows NSIS
installer, and a Linux AppImage. The GitHub `Desktop release` workflow runs on
`v*` tags, builds the wheel, bundles `uv`, publishes the assets, and uploads
`latest*.yml` for auto-update.

Packaged builds check GitHub releases every six hours. macOS auto-update
requires a signed build; add `APPLE_CERTIFICATE` and
`APPLE_CERTIFICATE_PASSWORD` repository secrets and the release workflow signs
the app. Windows and Linux update unsigned builds but still show OS security
warnings.
