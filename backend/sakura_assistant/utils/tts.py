import sys
import os
import time
import uuid
import pygame
import torch
import threading
import gc
import numpy as np
import soundfile as sf
from pathlib import Path

try:
    from kokoro import KPipeline
    KOKORO_AVAILABLE = True
    print("SUCCESS: Kokoro TTS loaded!", file=sys.stderr)
except Exception as e:
    KOKORO_AVAILABLE = False
    print("=" * 60, file=sys.stderr)
    print("KOKORO IMPORT FAILED - FULL TRACEBACK:", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    print("=" * 60, file=sys.stderr)

# Fallback Imports
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

from .memory import cleanup_memory


# --- Audio Output Directory (works in dev and frozen mode) ---
def get_audio_output_dir() -> Path:
    """Get writable directory for audio files (works in dev and frozen mode)"""
    if getattr(sys, 'frozen', False):
        # Production: Use AppData (same as .env location)
        app_data = Path(os.getenv('APPDATA')) / 'SakuraV10' / 'audio'
    else:
        # Dev: Use backend/temp_audio
        app_data = Path(__file__).parent.parent.parent / 'temp_audio'
    
    # Create directory if it doesn't exist
    app_data.mkdir(parents=True, exist_ok=True)
    return app_data


# --- Global State ---
_pipeline = None
_last_used_time = 0
_pipeline_lock = threading.Lock()
IDLE_TIMEOUT = 300  # 5 minutes

# V4: TTS Interrupt Flag (UI-controlled)
_stop_flag = False
_is_speaking = False


def is_speaking() -> bool:
    """Returns True if TTS is currently playing audio."""
    return _is_speaking


def stop_speaking():
    """
    Immediately stop TTS playback.
    Called by UI button or when user sends new message.
    """
    global _stop_flag, _is_speaking
    _stop_flag = True
    _is_speaking = False
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    except Exception:
        pass
    # Resume wake word after manual stop
    _resume_wake_word("manual_stop")


def _pause_wake_word(reason: str = "tts"):
    """Pause wake word detection during TTS."""
    try:
        from .wake_word import pause_wake_detection
        pause_wake_detection()
    except Exception:
        pass


def _resume_wake_word(reason: str = "tts_done"):
    """Resume wake word detection after TTS completes."""
    try:
        from .wake_word import resume_wake_detection
        resume_wake_detection()
    except Exception:
        pass


# --- Pipeline Management ---

def get_pipeline():
    """Lazy loads the Kokoro pipeline."""
    global _pipeline, _last_used_time
    
    with _pipeline_lock:
        if _pipeline is None:
            if not KOKORO_AVAILABLE:
                return None
            try:
                _pipeline = KPipeline(lang_code='b', repo_id='hexgrad/Kokoro-82M') 
            except Exception as e:
                print(f" Kokoro TTS failed: {e}")
                _pipeline = None
        
        _last_used_time = time.time()
        return _pipeline


def _background_idle_checker():
    global _pipeline
    while True:
        time.sleep(30)
        with _pipeline_lock:
            if _pipeline is not None:
                if time.time() - _last_used_time > IDLE_TIMEOUT:
                    _pipeline = None
                    cleanup_memory()

# Start background thread
threading.Thread(target=_background_idle_checker, daemon=True).start()


# --- Playback Helper ---
def play_audio_file(file_path):
    """Robust Pygame Playback with interrupt support."""
    global _stop_flag, _is_speaking
    
    try:
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
            except Exception as e:
                print(f" Audio Init Failed: {e}")
                return False

        # Reset stop flag before playback
        _stop_flag = False
        _is_speaking = True
        
        # V4.2: Pause wake word during TTS
        _pause_wake_word("playback")

        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        
        # Poll with interrupt check
        while pygame.mixer.music.get_busy():
            # V4: Check stop flag during playback
            if _stop_flag:
                pygame.mixer.music.stop()
                print(" TTS interrupted by user")
                break
            pygame.time.Clock().tick(10)
        
        _is_speaking = False
        pygame.mixer.music.unload()
        
        # V4.2: Resume wake word after TTS completes
        _resume_wake_word("playback")
        
        return True
    except Exception as e:
        print(f"Playback Error: {e}")
        _is_speaking = False
        _resume_wake_word("playback_error")
        return False
    finally:
        _is_speaking = False
        if os.path.exists(file_path):
            try: os.remove(file_path)
            except: pass

# --- TTS Engines ---

def kokoro_tts(text, voice='af_heart'):
    """Primary: Kokoro 82M with interrupt support."""
    global _last_used_time, _stop_flag, _is_speaking
    
    if not KOKORO_AVAILABLE:
        return False

    pipe = get_pipeline()
    if not pipe:
        return False
    
    # Reset stop flag at start
    _stop_flag = False
    _is_speaking = True
    
    # V17: Use proper writable directory for audio files
    audio_dir = get_audio_output_dir()
    temp_file = audio_dir / f"kokoro_{uuid.uuid4().hex}.wav"
    
    # Debug logging for audio path
    print("=" * 60, file=sys.stderr)
    print("[TTS DEBUG] KOKORO AUDIO GENERATION", file=sys.stderr)
    print(f"[TTS] Current working directory: {os.getcwd()}", file=sys.stderr)
    if getattr(sys, 'frozen', False):
        print(f"[TTS] Running in FROZEN mode", file=sys.stderr)
        print(f"[TTS] PyInstaller temp dir: {sys._MEIPASS}", file=sys.stderr)
    else:
        print(f"[TTS] Running in DEV mode", file=sys.stderr)
    print(f"[TTS] Audio output directory: {audio_dir}", file=sys.stderr)
    print(f"[TTS] Audio output file: {temp_file}", file=sys.stderr)
    print(f"[TTS] Directory exists: {audio_dir.exists()}", file=sys.stderr)
    print(f"[TTS] Directory writable: {os.access(audio_dir, os.W_OK)}", file=sys.stderr)
    print(f"[TTS] Kokoro Request: '{text[:50]}...'", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    try:
        # Generate with interrupt checks
        gen = pipe(text, voice=voice, speed=1)
        
        # Collect chunks with interrupt check
        audio = None
        for (_, _, chunk) in gen:
            # V4: Check stop flag during generation
            if _stop_flag:
                print("[TTS] TTS generation interrupted", file=sys.stderr)
                _is_speaking = False
                return False
                
            if audio is None:
                audio = chunk
            else:
                audio = np.concatenate([audio, chunk])
        
        if audio is None:
             print("[TTS] ✗ Kokoro produced no audio.", file=sys.stderr)
             _is_speaking = False
             return False

        # Final interrupt check before save
        if _stop_flag:
            _is_speaking = False
            return False

        # Save to file
        sf.write(str(temp_file), audio, 24000)
        
        # Verify file creation
        if temp_file.exists():
            size = temp_file.stat().st_size
            print(f"[TTS] ✓ Audio file created: {size} bytes", file=sys.stderr)
        else:
            print(f"[TTS] ✗ ERROR: File NOT created at {temp_file}", file=sys.stderr)
            _is_speaking = False
            return False
        
        # Update usage time
        _last_used_time = time.time()
        
        # Free generation memory immediately
        del audio, gen
        cleanup_memory()
        
        # Play (has its own interrupt handling)
        print(f"[TTS] Attempting to play: {temp_file}", file=sys.stderr)
        return play_audio_file(str(temp_file))
        
    except Exception as e:
        print(f"[TTS] ✗ Kokoro Generation Failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        _is_speaking = False
        if temp_file.exists():
            try: os.remove(temp_file)
            except: pass
        return False


def generate_audio(text: str, voice: str = 'af_heart') -> str | None:
    """
    Generate audio file and return path (NO playback).
    Used by frontend for HTML5 Audio API playback.
    
    Returns:
        str: Absolute path to the generated WAV file, or None on failure.
    """
    global _pipeline, _last_used_time
    
    if not KOKORO_AVAILABLE:
        print("[TTS] ✗ Kokoro not available for generation", file=sys.stderr)
        return None

    pipe = get_pipeline()
    if not pipe:
        print("[TTS] ✗ Failed to get Kokoro pipeline", file=sys.stderr)
        return None
    
    # V18: Use proper writable directory for audio files
    audio_dir = get_audio_output_dir()
    temp_file = audio_dir / f"kokoro_{uuid.uuid4().hex}.wav"
    
    print(f"[TTS] Generating audio for frontend: '{text[:50]}...'", file=sys.stderr)
    print(f"[TTS] Output: {temp_file}", file=sys.stderr)

    try:
        # Generate audio chunks
        gen = pipe(text, voice=voice, speed=1)
        
        audio = None
        for (_, _, chunk) in gen:
            if audio is None:
                audio = chunk
            else:
                audio = np.concatenate([audio, chunk])
        
        if audio is None:
            print("[TTS] ✗ Kokoro produced no audio.", file=sys.stderr)
            return None

        # Save to file
        sf.write(str(temp_file), audio, 24000)
        
        # Verify file creation
        if not temp_file.exists():
            print(f"[TTS] ✗ ERROR: File NOT created at {temp_file}", file=sys.stderr)
            return None
        
        size = temp_file.stat().st_size
        print(f"[TTS] ✓ Audio file created: {size} bytes", file=sys.stderr)
        
        # === AGGRESSIVE MEMORY CLEANUP ===
        # Offload Kokoro immediately to save RAM
        del audio, gen
        if pipe:
            del pipe
            _pipeline = None
        cleanup_memory()
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("[TTS] ✓ Kokoro offloaded, memory freed", file=sys.stderr)
        
        _last_used_time = time.time()
        
        return str(temp_file)
        
    except Exception as e:
        print(f"[TTS] ✗ Generation Failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        if temp_file.exists():
            try: os.remove(temp_file)
            except: pass
        return None


def pyttsx3_tts(text):
    """Final Fallback: Pyttsx3 (lightweight, no model download)"""
    global _is_speaking
    
    if not PYTTSX3_AVAILABLE:
        print(" Final Fallback Failed: pyttsx3 not installed.")
        return False
        
    print("Switching to pyttsx3 (lightweight fallback)...")
    try:
        _is_speaking = True
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        _is_speaking = False
        return True
    except Exception as e:
        print(f" Pyttsx3 Error: {e}")
        _is_speaking = False
        return False

# --- API ---

def speak(text):
    global _stop_flag
    
    if not text or not text.strip():
        return

    # Reset stop flag before new speech
    _stop_flag = False

    # 1. Try Kokoro (primary, lazy-loaded)
    if kokoro_tts(text):
        return
    
    # P0: Silero removed - was downloading ~200MB model from torch.hub
    # Now falls back directly to lightweight pyttsx3
    
    # 2. Try Pyttsx3 (lightweight offline fallback)
    pyttsx3_tts(text)

def text_to_speech(text, callback=None):
    def _run():
        speak(text)
        if callback:
             try: callback()
             except: pass
             
    threading.Thread(target=_run, daemon=True).start()

speak_async = text_to_speech