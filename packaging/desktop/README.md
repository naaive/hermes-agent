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
└─────────────────────────────┘     ~460 MB: dashboard + bundled backends
                                     FastAPI/uvicorn + SPA (web_dist) embedded
```

## What ships (the `desktop` extra)

A normal install lazy-installs opt-in backends on first use via
`tools/lazy_deps.py`. A frozen PyInstaller bundle can't pip-install at runtime,
so the desktop app **eager-bundles** its supported backends. The set is defined
once as the `desktop` extra in `pyproject.toml`; the build installs `.[desktop]`
and the spec packs whatever the venv contains (the venv *is* the manifest).

Bundled: providers (anthropic, bedrock, azure-identity), search (exa, firecrawl,
parallel), TTS (edge, elevenlabs), image (fal), memory (honcho, hindsight),
messaging (telegram, discord, slack), dingtalk, feishu, terminals (modal,
daytona, vercel), mcp, google-workspace, youtube, acp.

Excluded on purpose:
- **voice / faster-whisper** — pulls ctranslate2 + av + onnxruntime + numpy
  (~370 MB) and still downloads model weights at runtime; left for on-demand.
- **matrix** (`mautrix[encryption]` → `python-olm`) — Linux-only wheels, no
  Windows/macOS build path, so it would break the cross-platform build.

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
| `hermes-desktop.spec` | PyInstaller spec → onedir `hermes-desktop/`; packs every package in the build venv (the `.[desktop]` set), SPA embedded. |
| `tauri/ui/index.html` | Splash shown until the server is ready. |
| `tauri/src-tauri/` | Tauri app: `lib.rs` (copy/chmod/spawn + navigate), `tauri.conf.json`, `capabilities/`, `icons/`. |
| `tauri/src-tauri/sidecar/` | The onedir bundle, staged by the build as a Tauri resource (git-ignored). |
| `../../.github/workflows/desktop.yml` | macOS / Windows / Linux build matrix. |

## Sizes (Linux build, `.[desktop]` set)

| | |
|---|---|
| onedir sidecar | ~460 MB |
| `.deb` (xz-compressed) | ~200 MB (estimate) |
| First-run copy to `app_data_dir` | ~460 MB (one-time, then reused) |

Dashboard-only (no extra backends) is ~86 MB onedir / ~46 MB `.deb` if you
swap `.[desktop]` for `.[web]` in the build.

## Scope & known limitations

- **Excluded backends.** voice/faster-whisper and matrix are not bundled (see
  above). faster-whisper also downloads model weights at runtime, so bundling
  it would not make voice fully offline anyway.
- **No runtime install.** Unlike a normal install, the frozen bundle can't
  lazy-install new backends — `tools/lazy_deps.py` would need a user-writable
  target on `sys.path` to work here (a possible follow-up). For now, what ships
  is the `desktop` extra and nothing more.
- **No cross-compilation.** Each OS builds its own sidecar + installer; that is
  why the workflow uses a per-OS matrix.
- Unsigned. macOS/Windows code signing + notarization are not configured.

## Build locally (Linux example)

```bash
# 1. Build the SPA (writes to hermes_cli/web_dist)
cd web && npm ci && npm run build && cd ..

# 2. Build the Python sidecar (onedir). `.[desktop]` bundles the backends;
#    use `.[web]` for a lean dashboard-only build.
uv venv .venv-desktop --python 3.11
VIRTUAL_ENV=.venv-desktop uv pip install -e ".[desktop]" pyinstaller
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
