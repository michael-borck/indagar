"""Download uv binaries for the current platform into desktop/sidecar/uv."""

from __future__ import annotations

import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

UV_VERSION = "0.13.9"
BASE = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}"
OUT = Path(__file__).resolve().parents[1] / "sidecar" / "uv"

ASSETS = {
    "darwin-arm64": ("uv-aarch64-apple-darwin.tar.gz", "uv-arm64"),
    "darwin-x64": ("uv-x86_64-apple-darwin.tar.gz", "uv-x64"),
    "win32-x64": ("uv-x86_64-pc-windows-msvc.zip", "uv-x64.exe"),
    "linux-x64": ("uv-x86_64-unknown-linux-gnu.tar.gz", "uv-x64"),
}


def download(url: str, destination: Path) -> None:
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                destination.write_bytes(response.read())
            return
        except Exception:
            if attempt == 3:
                raise
            print(f"retry {attempt}: {url}", file=sys.stderr)


def extract(archive: Path, destination: Path) -> None:
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(destination)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(destination, filter="data")


def main() -> None:
    if sys.platform == "darwin":
        keys = ["darwin-arm64", "darwin-x64"]
    elif sys.platform == "win32":
        keys = ["win32-x64"]
    else:
        keys = ["linux-x64"]

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        for key in keys:
            asset, output_name = ASSETS[key]
            archive = root / asset
            print(f"downloading {asset}")
            download(f"{BASE}/{asset}", archive)
            extract_dir = root / key
            extract_dir.mkdir()
            extract(archive, extract_dir)
            candidates = [
                p for p in extract_dir.rglob("*") if p.is_file() and p.name in {"uv", "uv.exe"}
            ]
            if not candidates:
                raise SystemExit(f"uv binary not found in {asset}")
            target = OUT / output_name
            shutil.copy2(candidates[0], target)
            if sys.platform != "win32":
                target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            print(f"wrote {target}")


if __name__ == "__main__":
    main()
