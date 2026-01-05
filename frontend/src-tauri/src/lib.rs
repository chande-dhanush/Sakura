// Sakura V10 Tauri Backend
// Multi-Window Architecture: Bubble + Main
// Bubble: 64x64 widget pinned to bottom-right
// Main: Interface window, hidden until triggered

use std::process::{Command, Child, Stdio};
use std::sync::Mutex;
use std::path::PathBuf;
use tauri::{Manager, WebviewWindow, PhysicalPosition, Emitter, Listener};

// Global sidecar process handle
static BACKEND: Mutex<Option<Child>> = Mutex::new(None);

#[tauri::command]
fn get_backend_status() -> String {
    match BACKEND.lock() {
        Ok(guard) => {
            if guard.is_some() {
                "running".to_string()
            } else {
                "stopped".to_string()
            }
        }
        Err(_) => "error".to_string()
    }
}

#[tauri::command]
fn toggle_main_window(app: tauri::AppHandle) {
    if let Some(main_window) = app.get_webview_window("main") {
        if main_window.is_visible().unwrap_or(false) {
            let _ = main_window.hide();
        } else {
            let _ = main_window.show();
            let _ = main_window.set_focus();
        }
    }
}

#[tauri::command]
fn show_main_window(app: tauri::AppHandle) {
    if let Some(main_window) = app.get_webview_window("main") {
        let _ = main_window.show();
        let _ = main_window.set_focus();
    }
}

#[tauri::command]
fn hide_main_window(app: tauri::AppHandle) {
    if let Some(main_window) = app.get_webview_window("main") {
        let _ = main_window.hide();
    }
}

#[tauri::command]
fn force_quit() {
    println!("💥 Force quitting app and backend...");
    // Kill the Python backend immediately
    if let Ok(mut guard) = BACKEND.lock() {
        if let Some(ref mut child) = *guard {
            let _ = child.kill();
        }
        *guard = None;
    }
    // Hard exit the Tauri app
    std::process::exit(0);
}

fn find_backend_dir() -> Option<PathBuf> {
    let exe_path = std::env::current_exe().ok()?;
    let exe_dir = exe_path.parent()?;
    
    let dev_paths = [
        exe_dir.parent()?.parent()?.parent()?.parent()?.join("backend"),
        exe_dir.parent()?.parent()?.parent()?.join("backend"),
    ];
    
    for path in dev_paths.iter() {
        let server_py = path.join("server.py");
        if server_py.exists() {
            println!("✅ Found backend at: {:?}", path);
            return Some(path.to_path_buf());
        }
    }
    
    let cwd = std::env::current_dir().ok()?;
    let cwd_paths = [
        cwd.join("backend"),
        cwd.parent()?.join("backend"),
        cwd.parent()?.parent()?.join("backend"),
    ];
    
    for path in cwd_paths.iter() {
        let server_py = path.join("server.py");
        if server_py.exists() {
            println!("✅ Found backend (via CWD) at: {:?}", path);
            return Some(path.to_path_buf());
        }
    }
    
    println!("❌ Could not find backend/server.py");
    None
}

fn start_backend(app: &tauri::App) -> Result<(), String> {
    // PRODUCTION MODE: Use bundled sidecar
    // Check if bundled sidecar exists (indicates production build)
    let sidecar_path = app.path().resource_dir()
        .ok()
        .map(|p| p.join("binaries").join(if cfg!(windows) { "sakura-backend.exe" } else { "sakura-backend" }));
    
    if let Some(path) = sidecar_path.filter(|p| p.exists()) {
        println!("🚀 Starting bundled backend sidecar...");
        println!("   Path: {:?}", path);
        
        let mut cmd = Command::new(&path);
        cmd.stdout(Stdio::inherit());
        cmd.stderr(Stdio::inherit());
        
        // Set working directory to resource dir for data access
        if let Ok(resource_dir) = app.path().resource_dir() {
            cmd.current_dir(&resource_dir);
        }
        
        match cmd.spawn() {
            Ok(child) => {
                if let Ok(mut guard) = BACKEND.lock() {
                    *guard = Some(child);
                }
                println!("✅ Sidecar backend started on port 8000");
                return Ok(());
            }
            Err(e) => {
                eprintln!("⚠️ Sidecar failed, falling back to dev mode: {}", e);
            }
        }
    }
    
    // DEV MODE: Use Python with venv
    let backend_dir = find_backend_dir()
        .ok_or_else(|| "Could not find backend/server.py".to_string())?;
    
    let server_py = backend_dir.join("server.py");
    
    // V10: Use venv Python (PA/Scripts/python.exe on Windows)
    let venv_python = backend_dir.parent()
        .map(|root| root.join("PA").join("Scripts").join(if cfg!(windows) { "python.exe" } else { "python" }))
        .filter(|p| p.exists());
    
    let python_cmd = if let Some(venv_py) = venv_python {
        println!("🐍 Using venv Python: {:?}", venv_py);
        venv_py.to_string_lossy().to_string()
    } else {
        println!("⚠️ Venv not found, falling back to system Python");
        if cfg!(windows) { "python".to_string() } else { "python3".to_string() }
    };
    
    println!("🐍 Starting Python backend (dev mode)...");
    println!("   Script: {:?}", server_py);
    
    let mut cmd = Command::new(&python_cmd);
    cmd.arg(&server_py);
    cmd.arg("--voice"); // Enable Voice Mode by default
    cmd.current_dir(&backend_dir);
    cmd.env("PYTHONPATH", &backend_dir);
    cmd.stdout(Stdio::inherit());
    cmd.stderr(Stdio::inherit());
    
    match cmd.spawn() {
        Ok(child) => {
            if let Ok(mut guard) = BACKEND.lock() {
                *guard = Some(child);
            }
            println!("✅ Backend started on port 8000");
            Ok(())
        }
        Err(e) => {
            let msg = format!("Failed to start backend: {}", e);
            eprintln!("❌ {}", msg);
            Err(msg)
        }
    }
}

fn graceful_shutdown() {
    println!("🛑 Shutting down backend...");
    
    let client = reqwest::blocking::Client::new();
    let _ = client.post("http://localhost:8000/shutdown")
        .timeout(std::time::Duration::from_millis(500))
        .send();
    
    std::thread::sleep(std::time::Duration::from_millis(300));
    
    if let Ok(mut guard) = BACKEND.lock() {
        if let Some(ref mut child) = *guard {
            let _ = child.kill();
            println!("🛑 Backend process terminated");
        }
        *guard = None;
    }
    
    // Force exit the application
    std::process::exit(0);
}

fn position_bubble_bottom_right(bubble: &WebviewWindow) {
    // Get primary monitor and position bubble to bottom-right
    if let Some(monitor) = bubble.primary_monitor().ok().flatten() {
        let screen_size = monitor.size();
        let scale = monitor.scale_factor();
        
        // Calculate bottom-right position (physical pixels)
        // 220px window (contains 64px bubble + menu space)
        let bubble_size = (220.0 * scale) as i32;
        let margin = (20.0 * scale) as i32;
        let taskbar_height = (50.0 * scale) as i32;
        
        let x = screen_size.width as i32 - bubble_size - margin;
        let y = screen_size.height as i32 - bubble_size - taskbar_height;
        
        println!("📍 Positioning bubble to ({}, {}) on {}x{} screen", 
            x, y, screen_size.width, screen_size.height);
        
        let _ = bubble.set_position(PhysicalPosition::new(x, y));
    } else {
        println!("⚠️ Could not detect monitor, using default position");
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, Some(vec![])))
        .invoke_handler(tauri::generate_handler![
            get_backend_status,
            toggle_main_window,
            show_main_window,
            hide_main_window,
            force_quit
        ])
        .setup(|app| {
            // Start Python backend (sidecar in prod, python in dev)
            if let Err(e) = start_backend(app) {
                eprintln!("Warning: {}", e);
            }
            
            // Register Global Shortcut (Shift+S) for Quick Search
            #[cfg(desktop)]
            {
                use tauri_plugin_global_shortcut::{Code, Modifiers, ShortcutState};
                
                app.handle().plugin(
                    tauri_plugin_global_shortcut::Builder::new()
                        .with_shortcut("Alt+S")?
                        .with_shortcut("Alt+F")?
                        .with_shortcut("Alt+M")? // V10: Hide Mode
                        .with_handler(move |app, shortcut, event| {
                            if event.state == ShortcutState::Pressed {
                                if let Some(window) = app.get_webview_window("main") {
                                    
                                    // Alt+S: Quick Search Toggle
                                    if shortcut.matches(Modifiers::ALT, Code::KeyS) {
                                        println!("⌨️ Global Shortcut Alt+S pressed");
                                        if window.is_visible().unwrap_or(false) {
                                            // Hide AND Restore default size (so next normal open is big)
                                            let _ = window.hide();
                                            let _ = window.set_size(tauri::Size::Logical(tauri::LogicalSize { width: 1000.0, height: 800.0 }));
                                            let _ = window.center();
                                        } else {
                                            // Show Small
                                            let _ = window.set_size(tauri::Size::Logical(tauri::LogicalSize { width: 600.0, height: 60.0 }));
                                            let _ = window.center();
                                            let _ = window.show();
                                            let _ = window.set_focus();
                                            let _ = window.emit("quick_search_trigger", ());
                                        }
                                    }

                                    // Alt+F: Force Full Mode
                                    if shortcut.matches(Modifiers::ALT, Code::KeyF) {
                                        println!("⌨️ Global Shortcut Alt+F pressed");
                                        let _ = window.set_size(tauri::Size::Logical(tauri::LogicalSize { width: 400.0, height: 600.0 }));
                                        let _ = window.center();
                                        let _ = window.show();
                                        let _ = window.set_focus();
                                        let _ = window.emit("full_mode_trigger", ()); // Reset frontend state
                                    }
                                }
                                
                                // Alt+M: Hide Mode (Toggle Bubble)
                                if shortcut.matches(Modifiers::ALT, Code::KeyM) {
                                    println!("⌨️ Global Shortcut Alt+M pressed (Hide Mode)");
                                    if let Some(bubble) = app.get_webview_window("bubble") {
                                        if bubble.is_visible().unwrap_or(false) {
                                            let _ = bubble.hide();
                                            // Also hide main if visible
                                            if let Some(main) = app.get_webview_window("main") {
                                                let _ = main.hide();
                                            }
                                            println!("🫥 Bubble hidden (Movie Mode)");
                                        } else {
                                            let _ = bubble.show();
                                            println!("👁️ Bubble visible again");
                                        }
                                    }
                                }
                            }
                        })
                        .build(),
                )?;
            }

            // Enable Auto-Start by default (as per user request)
            use tauri_plugin_autostart::ManagerExt;
            let _ = app.handle().autolaunch().enable();
            
            // Position bubble to bottom-right
            if let Some(bubble) = app.get_webview_window("bubble") {
                position_bubble_bottom_right(&bubble);
            }
            
            // Listen for toggle_main event from bubble window
            let app_handle = app.handle().clone();
            app.listen("toggle_main", move |_event| {
                if let Some(main_window) = app_handle.get_webview_window("main") {
                    if main_window.is_visible().unwrap_or(false) {
                        let _ = main_window.hide();
                    } else {
                        // Reset to normal size if opening via bubble? 
                        // Or keep last state? Let's reset to default main window size for normal toggle
                        let _ = main_window.set_size(tauri::Size::Logical(tauri::LogicalSize { width: 480.0, height: 640.0 }));
                         // Reposition might be needed if it was centered... let's let OS handle or center?
                         // Ideally we want it draggable. 
                         // Let's just show it. The user manages position usually unless we force it.
                         // But if we just came from Quick Search (Centered), we might want to stay centered or move to last pos.
                         // For now, let's just show.
                        let _ = main_window.show();
                        let _ = main_window.set_focus();
                    }
                }
            });
            
            // V10: Check internet connectivity BEFORE waiting for backend
            let client = reqwest::blocking::Client::new();
            println!("🌐 Checking internet connectivity...");
            let mut has_internet = false;
            
            for attempt in 0..30 { // Wait up to 30 seconds for internet
                if let Ok(resp) = client.get("https://www.google.com")
                    .timeout(std::time::Duration::from_secs(2))
                    .send() 
                {
                    if resp.status().is_success() {
                        println!("✅ Internet connected!");
                        has_internet = true;
                        break;
                    }
                }
                
                if attempt == 0 {
                    println!("📡 No internet detected. Sakura requires internet to function.");
                    println!("   Waiting for connection...");
                    
                    // Emit event to frontend to show "No Internet" message
                    if let Some(main) = app.get_webview_window("main") {
                        let _ = main.emit("no_internet", ());
                    }
                }
                
                std::thread::sleep(std::time::Duration::from_secs(1));
            }
            
            if !has_internet {
                eprintln!("❌ No internet connection after 30 seconds. Some features may not work.");
            }
            
            // Wait for backend to be ready (Poll /health)
            // NOTE: SmartAssistant init takes 5-15s, so use generous timeout
            println!("⏳ Waiting for backend to start...");
            let mut ready = false;
            
            for _ in 0..45 { // Try for 45 seconds
                if let Ok(resp) = client.get("http://127.0.0.1:8000/health").send() {
                    if resp.status().is_success() {
                        println!("✅ Backend ready!");
                        ready = true;
                        break;
                    }
                }
                std::thread::sleep(std::time::Duration::from_secs(1));
            }
            
            if !ready {
                eprintln!("⚠️ Backend startup timed out or failed health check");
            }
            
            Ok(())
        })
        .on_window_event(|window, event| {
            match event {
                tauri::WindowEvent::Destroyed => {
                    // Only shutdown when bubble (main trigger) is destroyed
                    if window.label() == "bubble" {
                        graceful_shutdown();
                    }
                }
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    // Hide main window instead of closing
                    if window.label() == "main" {
                        api.prevent_close();
                        let _ = window.hide();
                    }
                }
                _ => {}
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
