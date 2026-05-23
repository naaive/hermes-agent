# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec freezing the Hermes dashboard (core + web extra).

Produces a one-directory build (executable + ``_internal/``) shipped as a Tauri
resource. The Tauri shell copies it to a writable per-user dir on first run
(and on version change) so the dashboard launches with no per-launch
extraction — unlike onefile, which re-inflates the whole bundle to a temp dir
every time it starts.

Scope: only the ``hermes dashboard`` code path. Optional backends
(voice/matrix/messaging) are intentionally excluded — they are lazy-installed
at runtime today, which does not work inside a frozen bundle.
"""
import os

from PyInstaller.utils.hooks import collect_submodules

REPO = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

# uvicorn picks loop/protocol/lifespan implementations via runtime imports,
# so its submodules are invisible to PyInstaller's static analysis.
hiddenimports = collect_submodules("uvicorn")

datas = []
web_dist = os.path.join(REPO, "hermes_cli", "web_dist")
if os.path.isdir(web_dist):
    datas.append((web_dist, "web_dist"))

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[REPO],
    binaries=[],
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
