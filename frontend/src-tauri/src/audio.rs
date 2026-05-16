use rodio::{Decoder, OutputStream, Sink};
use std::fs::File;
use std::io::BufReader;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::State;

enum AudioCommand {
    Play(String),
    Stop,
    Volume(f32),
}

pub struct AudioState {
    sender: Sender<AudioCommand>,
    playing: Arc<AtomicBool>,
}

impl AudioState {
    pub fn new() -> Self {
        let (sender, receiver) = mpsc::channel();
        let playing = Arc::new(AtomicBool::new(false));
        let volume = Arc::new(Mutex::new(1.0));

        start_audio_thread(receiver, Arc::clone(&playing), Arc::clone(&volume));

        Self {
            sender,
            playing,
        }
    }
}

fn start_audio_thread(
    receiver: Receiver<AudioCommand>,
    playing: Arc<AtomicBool>,
    volume: Arc<Mutex<f32>>,
) {
    thread::spawn(move || {
        let mut _current_stream: Option<OutputStream> = None;
        let mut current_sink: Option<Sink> = None;

        loop {
            match receiver.recv_timeout(Duration::from_millis(100)) {
                Ok(AudioCommand::Play(path)) => {
                    if let Some(sink) = current_sink.as_ref() {
                        sink.stop();
                    }
                    current_sink = None;
                    _current_stream = None;
                    playing.store(false, Ordering::Relaxed);

                    match play_path(&path, current_volume(&volume)) {
                        Ok((stream, sink)) => {
                            _current_stream = Some(stream);
                            current_sink = Some(sink);
                            playing.store(true, Ordering::Relaxed);
                            println!("[NativeAudio] Playing: {}", path);
                        }
                        Err(e) => {
                            eprintln!("[NativeAudio] Playback failed: {}", e);
                        }
                    }
                }
                Ok(AudioCommand::Stop) => {
                    if let Some(sink) = current_sink.as_ref() {
                        sink.stop();
                    }
                    current_sink = None;
                    _current_stream = None;
                    playing.store(false, Ordering::Relaxed);
                    println!("[NativeAudio] Playback stopped");
                }
                Ok(AudioCommand::Volume(value)) => {
                    let clamped = value.clamp(0.0, 1.0);
                    if let Ok(mut guard) = volume.lock() {
                        *guard = clamped;
                    }
                    if let Some(sink) = current_sink.as_ref() {
                        sink.set_volume(clamped);
                    }
                    println!("[NativeAudio] Volume set to: {:.2}", clamped);
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    if let Some(sink) = current_sink.as_ref() {
                        if sink.empty() {
                            current_sink = None;
                            _current_stream = None;
                            playing.store(false, Ordering::Relaxed);
                        }
                    }
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }
    });
}

fn current_volume(volume: &Arc<Mutex<f32>>) -> f32 {
    volume.lock().map(|guard| *guard).unwrap_or(1.0)
}

fn play_path(path: &str, volume: f32) -> Result<(OutputStream, Sink), String> {
    let file = File::open(path).map_err(|e| format!("Failed to open audio file: {}", e))?;
    let reader = BufReader::new(file);
    let source = Decoder::new(reader).map_err(|e| format!("Failed to decode audio: {}", e))?;

    let (stream, handle) = OutputStream::try_default()
        .map_err(|e| format!("Failed to open audio output: {}", e))?;
    let sink = Sink::try_new(&handle).map_err(|e| e.to_string())?;
    sink.append(source);
    sink.set_volume(volume.clamp(0.0, 1.0));
    sink.play();

    Ok((stream, sink))
}

#[tauri::command]
pub fn play_audio(state: State<'_, AudioState>, path: String) -> Result<(), String> {
    state
        .sender
        .send(AudioCommand::Play(path))
        .map_err(|e| format!("Failed to send play command: {}", e))
}

#[tauri::command]
pub fn stop_audio(state: State<'_, AudioState>) -> Result<(), String> {
    state
        .sender
        .send(AudioCommand::Stop)
        .map_err(|e| format!("Failed to send stop command: {}", e))
}

#[tauri::command]
pub fn set_audio_volume(state: State<'_, AudioState>, volume: f32) -> Result<(), String> {
    state
        .sender
        .send(AudioCommand::Volume(volume))
        .map_err(|e| format!("Failed to send volume command: {}", e))
}

#[tauri::command]
pub fn is_audio_playing(state: State<'_, AudioState>) -> bool {
    state.playing.load(Ordering::Relaxed)
}
