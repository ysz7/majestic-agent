use tauri::{
    Manager,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, TrayIconBuilder, TrayIconEvent},
};
use std::path::PathBuf;

// ── Path helpers ──────────────────────────────────────────────────────────────

/// Return the Majestic project root.
/// Priority: MAJESTIC_ROOT env var → executable's ancestor (dev layout) → error.
fn resolve_root() -> Option<PathBuf> {
    // 1. Explicit env var (set by launcher scripts)
    if let Ok(r) = std::env::var("MAJESTIC_ROOT") {
        let p = PathBuf::from(r);
        if p.exists() { return Some(p); }
    }
    // 2. In dev, binary lives at  …/desktop/src-tauri/target/debug/
    //    → go up 4 levels to reach project root
    if let Ok(exe) = std::env::current_exe() {
        for ancestor in exe.ancestors().skip(1) {
            if ancestor.join("majestic").is_dir() && ancestor.join("profiles").exists() {
                return Some(ancestor.to_path_buf());
            }
        }
    }
    None
}

// ── Tauri commands ────────────────────────────────────────────────────────────

/// Return the resolved project root path (for frontend to display).
#[tauri::command]
fn get_majestic_root() -> String {
    resolve_root()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_default()
}

/// Read data/agent_token from the project root. Returns empty string if absent.
#[tauri::command]
fn read_agent_token() -> String {
    resolve_root()
        .map(|root| root.join("data").join("agent_token"))
        .and_then(|p| std::fs::read_to_string(p).ok())
        .map(|s| s.trim().to_string())
        .unwrap_or_default()
}

/// Spawn `majestic run <profile>` as a detached background process.
#[tauri::command]
fn start_agent(profile: String) -> Result<(), String> {
    let root = resolve_root().ok_or("Cannot locate project root")?;

    // Prefer the venv Python so majestic is definitely importable
    #[cfg(target_os = "windows")]
    let python_candidates = vec![
        root.join(".venv").join("Scripts").join("python.exe"),
        PathBuf::from("python"),
        PathBuf::from("python3"),
    ];
    #[cfg(not(target_os = "windows"))]
    let python_candidates = vec![
        root.join(".venv").join("bin").join("python"),
        PathBuf::from("python3"),
        PathBuf::from("python"),
    ];

    let python = python_candidates
        .into_iter()
        .find(|p| p.exists() || p.components().count() == 1)
        .ok_or("Python not found")?;

    let mut cmd = std::process::Command::new(&python);
    cmd.args(["-m", "majestic.__background__", &profile])
        .current_dir(&root)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NEW_PROCESS_GROUP: u32 = 0x00000200;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW);
    }
    #[cfg(not(target_os = "windows"))]
    {
        use std::os::unix::process::CommandExt as _;
        unsafe { cmd.pre_exec(|| { libc::setsid(); Ok(()) }); }
    }

    cmd.spawn().map_err(|e| e.to_string())?;
    Ok(())
}

/// Return the platform data directory for installed users.
#[tauri::command]
fn get_data_dir(app: tauri::AppHandle) -> Result<String, String> {
    app.path()
        .app_data_dir()
        .map(|p| p.to_string_lossy().to_string())
        .map_err(|e| e.to_string())
}

/// Try `python --version` then `python3 --version`.
#[tauri::command]
fn check_python() -> Result<String, String> {
    for bin in &["python", "python3"] {
        if let Ok(out) = std::process::Command::new(bin).arg("--version").output() {
            let ver = String::from_utf8_lossy(&out.stdout).to_string()
                + &String::from_utf8_lossy(&out.stderr).to_string();
            let ver = ver.trim().to_string();
            if !ver.is_empty() { return Ok(ver); }
        }
    }
    Err("Python not found".to_string())
}

// ── App entry point ───────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let show_item = MenuItem::with_id(app, "show", "Show Window", true, None::<&str>)?;
            let sep       = PredefinedMenuItem::separator(app)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit Majestic", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &sep, &quit_item])?;

            let _ = TrayIconBuilder::new()
                .menu(&menu)
                .tooltip("Majestic Agent")
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, .. } = event {
                        let app = tray.app_handle();
                        if let Some(w) = app.get_webview_window("main") {
                            if w.is_visible().unwrap_or(false) {
                                let _ = w.hide();
                            } else {
                                let _ = w.show();
                                let _ = w.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            check_python,
            get_data_dir,
            get_majestic_root,
            read_agent_token,
            start_agent,
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                window.hide().unwrap();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
