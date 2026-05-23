use std::fs;
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::Child;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent};

const PORT: u16 = 9119;

// Holds the dashboard child so it can be killed when the app exits.
struct SidecarChild(Mutex<Option<Child>>);

fn sidecar_exe_name() -> &'static str {
    if cfg!(windows) {
        "hermes-desktop.exe"
    } else {
        "hermes-desktop"
    }
}

fn copy_dir_all(src: &Path, dst: &Path) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let from = entry.path();
        let to = dst.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_dir_all(&from, &to)?;
        } else {
            fs::copy(&from, &to)?;
        }
    }
    Ok(())
}

// The onedir sidecar is shipped as a read-only Tauri resource. Tauri does not
// preserve the executable bit on resources, and the resource dir is read-only
// on macOS (signed .app) and on a system-wide Linux install. So on first run —
// and whenever the app version changes — copy the bundle to a writable per-user
// dir, mark it with the version, and make the binary executable. Subsequent
// launches reuse it and spawn instantly (no per-launch extraction).
fn ensure_sidecar(app: &AppHandle) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let src = app.path().resource_dir()?.join("sidecar");
    let version = app.package_info().version.to_string();

    let dest = app.path().app_data_dir()?.join("sidecar");
    let marker = dest.join(".version");
    let exe = dest.join(sidecar_exe_name());

    let up_to_date = exe.exists()
        && fs::read_to_string(&marker)
            .map(|v| v.trim() == version)
            .unwrap_or(false);

    if !up_to_date {
        if dest.exists() {
            fs::remove_dir_all(&dest)?;
        }
        copy_dir_all(&src, &dest)?;
        fs::write(&marker, &version)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perm = fs::metadata(&exe)?.permissions();
            perm.set_mode(0o755);
            fs::set_permissions(&exe, perm)?;
        }
    }

    Ok(exe)
}

// A successful TCP connect means uvicorn is accepting connections, i.e. serving.
fn wait_for_port(port: u16, timeout: Duration) -> bool {
    let addr: SocketAddr = ([127, 0, 0, 1], port).into();
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(SidecarChild(Mutex::new(None)))
        .setup(|app| {
            let exe = ensure_sidecar(app.handle())?;
            let child = std::process::Command::new(&exe)
                .env("HERMES_DESKTOP_PORT", PORT.to_string())
                .spawn()?;
            app.state::<SidecarChild>().0.lock().unwrap().replace(child);

            // Once the dashboard is listening, navigate the window from the
            // bundled splash to the live local server.
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let ready = wait_for_port(PORT, Duration::from_secs(45));
                let h = handle.clone();
                let _ = handle.run_on_main_thread(move || {
                    let Some(window) = h.get_webview_window("main") else {
                        return;
                    };
                    if ready {
                        if let Ok(url) = format!("http://127.0.0.1:{PORT}").parse::<tauri::Url>() {
                            let _ = window.navigate(url);
                        }
                    } else {
                        let _ = window.eval(
                            "var m=document.getElementById('msg');\
                             if(m)m.textContent='Hermes failed to start — check the logs.';",
                        );
                    }
                });
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Hermes desktop app")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app_handle.try_state::<SidecarChild>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
