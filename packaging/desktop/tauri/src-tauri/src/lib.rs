use std::net::{SocketAddr, TcpStream};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const PORT: u16 = 9119;

// Holds the Python dashboard child so it can be killed when the app exits.
struct SidecarChild(Mutex<Option<CommandChild>>);

// The dashboard binds the port before it can serve; a successful TCP connect is
// our readiness signal (uvicorn accepts connections only once it is serving).
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
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarChild(Mutex::new(None)))
        .setup(|app| {
            // Spawn the bundled Python dashboard (onefile PyInstaller binary
            // declared in tauri.conf.json -> bundle.externalBin).
            let (mut rx, child) = app
                .shell()
                .sidecar("hermes-desktop")?
                .env("HERMES_DESKTOP_PORT", PORT.to_string())
                .spawn()?;
            app.state::<SidecarChild>().0.lock().unwrap().replace(child);

            // Forward sidecar output to the host process logs for debugging.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            print!("[hermes] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprint!("[hermes] {}", String::from_utf8_lossy(&line));
                        }
                        _ => {}
                    }
                }
            });

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
                    if let Some(child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
