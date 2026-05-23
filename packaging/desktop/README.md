# Hermes Desktop (Tauri)

Packages the Hermes **dashboard** as a native desktop app: a small
[Tauri](https://tauri.app) shell wraps the existing React SPA, and the Python
agent runs as a bundled **PyInstaller "onefile" sidecar** that serves both the
SPA and the API on `127.0.0.1`.

```
┌─────────────────────────────┐
│ Tauri shell (Rust, ~13 MB)  │   native window + lifecycle
│  └─ webview                 │
│       │ navigates to        │
│       ▼                     │
│  http://127.0.0.1:9119  ◄───┼── hermes-desktop sidecar (PyInstaller, ~44 MB)
└─────────────────────────────┘     FastAPI/uvicorn + SPA (web_dist) embedded
```

On launch the shell shows `ui/index.html` (a splash), spawns the sidecar, waits
for the port to accept connections, then navigates the window to the live
dashboard. On exit it kills the sidecar.

## Layout

| Path | What |
|------|------|
| `launcher.py` | Frozen entry point — boots the dashboard headless, points the static mount at the bundled SPA via `HERMES_WEB_DIST`. |
| `hermes-desktop.spec` | PyInstaller spec → single `hermes-desktop` binary (core + `web` extra, SPA embedded). |
| `tauri/ui/index.html` | Splash shown until the server is ready. |
| `tauri/src-tauri/` | Tauri app: `lib.rs` (sidecar spawn + navigate), `tauri.conf.json`, `capabilities/`, `icons/`. |
| `tauri/src-tauri/binaries/` | Per-platform sidecar, named `hermes-desktop-<target-triple>` (built in CI, git-ignored). |
| `../../.github/workflows/desktop.yml` | macOS / Windows / Linux build matrix. |

## Scope & known limitations

- **Dashboard only.** Optional backends (voice, matrix, messaging, alt
  providers) are excluded — they lazy-install via `tools/lazy_deps.py` at
  runtime, which does **not** work inside a frozen bundle (no pip, read-only
  bundle). Bundling them or routing lazy installs to a user-writable venv is a
  follow-up.
- **No cross-compilation.** Each OS builds its own sidecar + installer; that is
  why the workflow uses a per-OS matrix.
- Unsigned. macOS/Windows code signing + notarization are not configured.

## Build locally (Linux example)

```bash
# 1. Build the SPA (writes to hermes_cli/web_dist)
cd web && npm ci && npm run build && cd ..

# 2. Build the Python sidecar (onefile)
uv venv .venv-desktop --python 3.11
VIRTUAL_ENV=.venv-desktop uv pip install -e ".[web]" pyinstaller
VIRTUAL_ENV=.venv-desktop .venv-desktop/bin/pyinstaller \
  packaging/desktop/hermes-desktop.spec \
  --distpath packaging/desktop/dist --workpath packaging/desktop/build --noconfirm

# 3. Stage the sidecar for Tauri (suffix with your target triple)
cp packaging/desktop/dist/hermes-desktop \
   packaging/desktop/tauri/src-tauri/binaries/hermes-desktop-$(rustc -vV | sed -n 's/host: //p')

# 4. Build the desktop app
cd packaging/desktop/tauri && npm install && npm run build
# → src-tauri/target/release/bundle/
```

Linux build deps: `libwebkit2gtk-4.1-dev libgtk-3-dev
libayatana-appindicator3-dev librsvg2-dev patchelf`.

## CI

`.github/workflows/desktop.yml` is **manual** (`workflow_dispatch`). It builds
the SPA, the PyInstaller sidecar, and the Tauri installers for all three
platforms, uploading them as artifacts. Set the `release` input to `true` to
attach them to a draft GitHub Release.
