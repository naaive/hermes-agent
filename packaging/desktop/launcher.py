"""Frozen desktop entry point for the Hermes dashboard.

Boots the FastAPI/uvicorn dashboard (``hermes dashboard``) from inside a
PyInstaller bundle, pointing the static-file mount at the SPA build that was
packed alongside the executable. A native shell (Tauri/pywebview) is expected
to point a window at http://127.0.0.1:<port>.
"""

import os
import sys
from pathlib import Path


def _bundle_dir() -> Path:
    # PyInstaller unpacks bundled data under sys._MEIPASS at runtime.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent


def _selftest() -> int:
    """Smoke-test the frozen bundle: confirm bundled provider profiles load.

    Provider profiles live in plugins/model-providers/ and are discovered by
    filesystem scan + file-path import, so they are invisible to PyInstaller's
    static analysis. This asserts they actually resolve from inside the bundle.
    Run: ``hermes-desktop --selftest``.
    """
    from providers import list_providers

    profiles = list_providers()
    print(f"providers discovered: {len(profiles)}")
    for p in profiles:
        print(f"  - {getattr(p, 'name', None) or type(p).__name__}")
    return 0 if profiles else 1


def main() -> None:
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())

    bundle = _bundle_dir()
    web_dist = bundle / "web_dist"
    # web_server reads WEB_DIST at import time, so set this before importing it.
    if web_dist.is_dir():
        os.environ.setdefault("HERMES_WEB_DIST", str(web_dist))

    port = int(os.environ.get("HERMES_DESKTOP_PORT", "9119"))

    from hermes_cli.web_server import start_server

    start_server(host="127.0.0.1", port=port, open_browser=False)


if __name__ == "__main__":
    main()
