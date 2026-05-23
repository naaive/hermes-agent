# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec freezing the Hermes dashboard + bundled backends.

Strategy: the build venv IS the manifest. The build installs ``.[desktop]``
(see the ``desktop`` extra in pyproject.toml) and this spec packs *every*
package found in that venv. To change what ships, change the extra — not this
file.

Produces a one-directory build (executable + ``_internal/``) shipped as a Tauri
resource. The Tauri shell copies it to a writable per-user dir on first run so
the dashboard launches with no per-launch extraction.

Optional backends excluded from the desktop bundle (voice/faster-whisper,
matrix) are documented on the ``desktop`` extra in pyproject.toml.
"""
import os
from importlib.metadata import distributions

from PyInstaller.utils.hooks import collect_all, collect_submodules

REPO = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

# Build tooling that lives in the venv but must never ship in the app.
_SKIP = {
    "pip",
    "pyinstaller",
    "pyinstaller-hooks-contrib",
    "altgraph",
    "hermes-agent",  # our own source is added via the launcher's import graph
}

datas = []
binaries = []
hiddenimports = list(collect_submodules("uvicorn"))

# Pack every installed distribution (data files, native libs, submodules) so
# lazily-imported backends — invisible to static analysis — are present.
_seen = set()
for dist in distributions():
    name = (dist.metadata["Name"] or "").strip()
    if not name or name.lower() in _SKIP:
        continue
    top_level = dist.read_text("top_level.txt")
    tops = top_level.split() if top_level else [name.replace("-", "_")]
    for top in tops:
        if not top or top in _seen or top.endswith((".pth", ".py")):
            continue
        _seen.add(top)
        try:
            d, b, h = collect_all(top)
        except Exception:
            continue
        datas += d
        binaries += b
        hiddenimports += h

# The built SPA, served by the dashboard.
web_dist = os.path.join(REPO, "hermes_cli", "web_dist")
if os.path.isdir(web_dist):
    datas.append((web_dist, "web_dist"))

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[REPO],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "_pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="hermes-desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Windowed: no console flashes on Windows. The shell still inherits the
    # sidecar's stdio. No effect on Linux/macOS plain executables.
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="hermes-desktop",
)
