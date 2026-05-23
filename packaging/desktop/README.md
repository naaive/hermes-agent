# Hermes Desktop (Tauri)

Packages the Hermes **dashboard** as a native desktop app: a small
[Tauri](https://tauri.app) shell wraps the existing React SPA, and the Python
agent runs as a bundled **PyInstaller one-directory sidecar** that serves both
the SPA and the API on `127.0.0.1`.

```
┌─────────────────────────────┐
│ Tauri shell (Rust, ~9 MB)   │   native window + lifecycle
│  └─ webview                 │
│       │ navigates to        │
│       ▼                     │
│  http://127.0.0.1:9119  ◄───┼── hermes-desktop sidecar (PyInstaller onedir)
└─────────────────────────────┘     exe ~20 MB + _internal ~67 MB
                                     FastAPI/uvicorn + SPA (web_dist) embedded
```

On launch the shell shows `ui/index.html` (a splash), starts the sidecar, waits
for the port to accept connections, then navigates the window to the live
dashboard. On exit it kills the sidecar.

## Why onedir (not onefile)

A PyInstaller **onefile** binary re-inflates its whole ~86 MB payload to a temp
dir on **every** launch — slow startup, every time. This uses **onedir**
instead: the shell copies the bundle to a writable per-user dir
(`app_data_dir/sidecar`) on first run — and whenever the app version changes —
then launches it directly. Subsequent starts do no extraction and no copy
(~0.6 s to ready, measured on Linux). Tauri does not preserve the executable
bit on resources and the resource dir is read-only on a signed macOS `.app`, so
the copy step also `chmod +x`es the binary in the writable location.

## Layout

| Path | What |
|------|------|
| `launcher.py` | Frozen entry point — boots the dashboard headless, points the static mount at the bundled SPA via `HERMES_WEB_DIST`. |
| `hermes-desktop.spec` | PyInstaller spec → onedir `hermes-desktop/` (core + `web` extra, SPA embedded). |
| `tauri/ui/index.html` | Splash shown until the server is ready. |
| `tauri/src-tauri/` | Tauri app: `lib.rs` (copy/chmod/spawn + navigate), `tauri.conf.json`, `capabilities/`, `icons/`. |
| `tauri/src-tauri/sidecar/` | The onedir bundle, staged by the build as a Tauri resource (git-ignored). |
| `../../.github/workflows/desktop.yml` | macOS / Windows / Linux build matrix. |

## Sizes (Linux build)

| | |
|---|---|
| `.deb` (xz-compressed) | ~46 MB |
| Installed on disk | ~93 MB |
| First-run copy to `app_data_dir` | ~86 MB (one-time, then reused) |

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

# 2. Build the Python sidecar (onedir)
uv venv .venv-desktop --python 3.11
VIRTUAL_ENV=.venv-desktop uv pip install -e ".[web]" pyinstaller
VIRTUAL_ENV=.venv-desktop .venv-desktop/bin/pyinstaller \
  packaging/desktop/hermes-desktop.spec \
  --distpath packaging/desktop/dist --workpath packaging/desktop/build --noconfirm

# 3. Stage the onedir bundle as a Tauri resource
rm -rf packaging/desktop/tauri/src-tauri/sidecar
cp -r packaging/desktop/dist/hermes-desktop packaging/desktop/tauri/src-tauri/sidecar

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
