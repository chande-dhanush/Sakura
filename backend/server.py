"""
Sakura V10 Backend Server

FastAPI wrapper around SmartAssistant with SSE streaming.
Designed to run as a Tauri sidecar.

Endpoints:
    POST /chat   - SSE stream for chat responses
    POST /stop   - Interrupt current generation
    POST /shutdown - Graceful shutdown (saves World Graph)
    GET /state   - World Graph state for UI
    GET /health  - Health check
"""
import os
import sys
import json
import asyncio
from typing import Optional
from contextlib import asynccontextmanager

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sakura_assistant.core.memory.reflection import get_reflection_engine  # V14: Unified

# V14: Sleep Cycle for startup crystallization
from sakura_assistant.core.scheduler import run_sleep_cycle_on_startup, get_dream_journal

# V15: Cognitive Architecture
from sakura_assistant.core.scheduler import schedule_cognitive_tasks

from fastapi import FastAPI, Request, BackgroundTasks, WebSocket, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import warnings

# Initialize structured logging
try:
    from sakura_assistant.utils.logging import configure_logging, get_logger
    configure_logging(json_output=False)  # Human-readable for basic run
    log = get_logger("backend")
except ImportError:
    import logging
    log = logging.getLogger("backend")
    log.setLevel(logging.INFO)

# =============================================================================
# NOTE: Auth removed - this is a localhost-only desktop app
# The frontend and backend communicate only via localhost:3210
# =============================================================================

# Lazy import to avoid loading models at import time
assistant = None
voice_engine = None  # Initialized if SAKURA_ENABLE_VOICE=true
current_task: Optional[asyncio.Task] = None
generation_cancelled = False


# State flags
SETUP_REQUIRED = False
INIT_ERROR = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global assistant, SETUP_REQUIRED, INIT_ERROR
    print("🚀 Starting Sakura Backend...")
    
    # Import here to delay model loading until server starts
    from sakura_assistant.core.llm import SmartAssistant
    
    # BOOTSTRAP: Ensure data files exist in persistent storage
    try:
        import shutil
        from sakura_assistant.utils.pathing import get_project_root, get_bundled_path
        
        # 1. Ensure Data Directory
        project_root = get_project_root()
        data_dir = os.path.join(project_root, "data")
        os.makedirs(data_dir, exist_ok=True)
        
        # 2. Copy Default Bookmarks if missing
        target_bookmarks = os.path.join(data_dir, "bookmarks.json")
        if not os.path.exists(target_bookmarks):
            bundled_bookmarks = get_bundled_path("data/bookmarks.json")
            if os.path.exists(bundled_bookmarks) and os.path.abspath(bundled_bookmarks) != os.path.abspath(target_bookmarks):
                print(f"📦 Bootstrapping default bookmarks to: {target_bookmarks}")
                shutil.copy2(bundled_bookmarks, target_bookmarks)
                
    except Exception as e:
        print(f"⚠️ Data bootstrap warning: {e}")

    try:
        assistant = SmartAssistant()
        print("✅ SmartAssistant initialized")
        
        # V11: Sync WorldGraph singleton for background threads
        from sakura_assistant.core.world_graph import set_world_graph
        if hasattr(assistant, 'world_graph'):
            set_world_graph(assistant.world_graph)
            
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"⚠️ SmartAssistant Init Failed (Likely missing keys). Entering Setup Mode.")
        # Don't crash - allow UI to show Setup Screen
        SETUP_REQUIRED = True
        INIT_ERROR = str(e)
        
        # Log to file for debug
        try:
            with open("sakura_startup_log.txt", "w") as f:
                f.write(f"Startup Error (Setup Mode Triggered):\n{err}")
        except:
            pass
    
    # Start Voice Engine if enabled via flag AND assistant is ready
    if os.getenv("SAKURA_ENABLE_VOICE") == "true" and assistant:
        try:
            from sakura_assistant.core.voice_engine import VoiceEngine
            global voice_engine
            voice_engine = VoiceEngine(assistant)
            voice_engine.start()
        except Exception as e:
            print(f"❌ Failed to start Voice Engine: {e}")
    
    # V13: Start Memory Maintenance Scheduler (Temporal Decay)
    if assistant:
        try:
            from sakura_assistant.core.scheduler import schedule_memory_maintenance, start_scheduler
            start_scheduler()
            schedule_memory_maintenance("03:00")  # Run at 3 AM daily
            print("🧹 Memory maintenance scheduler started (3:00 AM daily)")
            
            # V14: Run Sleep Cycle on startup (24h cooldown)
            run_sleep_cycle_on_startup()
            
            # V15: Schedule cognitive tasks (hourly desire tick)
            schedule_cognitive_tasks()
            
            # V15: Wire up proactive WebSocket callback
            setup_proactive_callback()
        except Exception as e:
            print(f"⚠️ Scheduler init warning: {e}")
    
    yield
    
    # Cleanup on shutdown
    print("🛑 Shutting down Sakura Backend...")
    if assistant and hasattr(assistant, 'world_graph'):
        assistant.world_graph.save()
        print("💾 World Graph saved")
    
    # Flash conversation history to disk
    try:
        from sakura_assistant.memory.faiss_store import get_memory_store
        store = get_memory_store()
        store.flush_saves()
        print(f"💾 Conversation history saved ({len(store.conversation_history)} messages)")
    except Exception as e:
        print(f"⚠️ Failed to save history: {e}")

    # V11.3 Cleanup Ephemeral Stores
    try:
        from sakura_assistant.core.ephemeral_manager import get_ephemeral_manager
        print("🧹 Cleaning up ephemeral stores...")
        get_ephemeral_manager().cleanup_old(max_age_minutes=0) # Force delete all
    except Exception as e:
        print(f"⚠️ Ephemeral cleanup error: {e}")


app = FastAPI(
    title="Sakura Backend",
    version="10.0",
    lifespan=lifespan
)

# CORS for Tauri WebView
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """
    Real-time status stream for V12 features (Thought Stream).
    
    V15.2.2: Origin validation to prevent WebSocket hijacking.
    """
    # V15.2.2: Security - Validate origin to prevent hijacking from malicious websites
    origin = websocket.headers.get("origin", "")
    allowed_origins = [
        "tauri://localhost",
        "http://localhost:1420",  # Tauri dev server
        "http://127.0.0.1:1420",
        "http://localhost:3210",  # Backend (for debugging)
        "http://127.0.0.1:3210",
    ]
    
    if origin and origin not in allowed_origins:
        print(f"🛡️ [Security] Rejected WebSocket from origin: {origin}")
        await websocket.close(code=1008, reason="Invalid origin")
        return
    
    await websocket.accept()
    from sakura_assistant.core.broadcaster import get_broadcaster
    import asyncio
    
    q = asyncio.Queue()
    
    def listener(event, data):
        q.put_nowait({"event": event, "data": data})
        
    broadcaster = get_broadcaster()
    broadcaster.add_listener(listener)
    
    try:
        while True:
            item = await q.get()
            await websocket.send_json(item)
    except Exception as e:
        print(f"⚠️ WebSocket disconnect: {e}")
    finally:
        # Ideally remove listener, but current simple broadcaster doesn't support removal
        pass

@app.post("/setup")
async def save_setup(request: Request):
    """Save API keys to .env and re-initialize assistant."""
    global assistant, SETUP_REQUIRED, INIT_ERROR
    
    try:
        data = await request.json()
        
        # 1. Validate keys (Groq required only for first-time setup)
        groq_key = data.get("GROQ_API_KEY", "").strip()
        
        # 2. Load existing .env to MERGE (not overwrite)
        from sakura_assistant.utils.pathing import get_project_root
        env_path = os.path.join(get_project_root(), ".env")
        
        existing_env = {}
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        existing_env[key.strip()] = val.strip()
        
        # 3. Merge new values with existing (only update if provided)
        def merge_key(key, new_val):
            """Only update if new value is provided, otherwise keep existing."""
            if new_val:
                return new_val
            return existing_env.get(key, "")
        
        merged = {
            "GROQ_API_KEY": merge_key("GROQ_API_KEY", groq_key),
            "TAVILY_API_KEY": merge_key("TAVILY_API_KEY", data.get("TAVILY_API_KEY", "").strip()),
            "OPENROUTER_API_KEY": merge_key("OPENROUTER_API_KEY", data.get("OPENROUTER_API_KEY", "").strip()),
            "GOOGLE_API_KEY": merge_key("GOOGLE_API_KEY", data.get("GOOGLE_API_KEY", "").strip()),
            "SPOTIFY_CLIENT_ID": merge_key("SPOTIFY_CLIENT_ID", data.get("SPOTIFY_CLIENT_ID", "").strip()),
            "SPOTIFY_CLIENT_SECRET": merge_key("SPOTIFY_CLIENT_SECRET", data.get("SPOTIFY_CLIENT_SECRET", "").strip()),
            "SPOTIFY_DEVICE_NAME": merge_key("SPOTIFY_DEVICE_NAME", data.get("SPOTIFY_DEVICE_NAME", "").strip()),
            "MICROPHONE_INDEX": merge_key("MICROPHONE_INDEX", data.get("MICROPHONE_INDEX", "").strip()),
            "SAKURA_ENABLE_VOICE": "true",
        }
        
        # Validate: Groq key must exist (either new or existing)
        if not merged["GROQ_API_KEY"]:
            return JSONResponse({"success": False, "message": "Groq API Key is required"}, status_code=400)
        
        # 4. Write merged .env
        env_lines = ["# Sakura V10 User Configuration"]
        for key, val in merged.items():
            if val:  # Only write non-empty values
                env_lines.append(f"{key}={val}")
        
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(env_lines) + "\n")
        
        # 5. Save User Personalization to separate JSON (not in .env)
        user_settings = {
            "user_name": data.get("USER_NAME", "").strip(),
            "user_location": data.get("USER_LOCATION", "").strip(),
            "user_bio": data.get("USER_BIO", "").strip(),
        }
        
        # Merge with existing user_settings.json
        settings_path = os.path.join(get_project_root(), "data", "user_settings.json")
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        
        existing_settings = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    existing_settings = json.load(f)
            except:
                pass
        
        # Only update if new value provided
        for key, val in user_settings.items():
            if val:
                existing_settings[key] = val
        
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(existing_settings, f, indent=2)
        
        # V16: Refresh IdentityManager and broadcast via EventBus
        try:
            from sakura_assistant.core.identity_manager import get_identity_manager
            get_identity_manager().refresh()
            print("✅ [V16] Identity refreshed and broadcasted")
        except Exception as e:
            print(f"⚠️ Identity refresh warning: {e}")
            
        # 6. Reload Env (Update os.environ from merged values)
        for key, val in merged.items():
            if val:
                os.environ[key] = val
        
        # 4. RESET CONTAINER & Re-init Assistant
        # Critical: Container caches LLM config at init. Must reset to pick up env vars.
        from sakura_assistant.core.container import reset_container
        reset_container()
        
        from sakura_assistant.core.llm import SmartAssistant
        try:
            assistant = SmartAssistant()
            SETUP_REQUIRED = False
            INIT_ERROR = None
            
            # Start Voice Engine if previously failed or not started
            if os.getenv("SAKURA_ENABLE_VOICE") == "true":
                try:
                    from sakura_assistant.core.voice_engine import VoiceEngine
                    global voice_engine
                    if 'voice_engine' not in globals() or voice_engine is None:
                        voice_engine = VoiceEngine(assistant)
                        voice_engine.start()
                except Exception as ve:
                    print(f"⚠️ Voice start warning: {ve}")

            return {"success": True, "message": "Setup complete! Sakura is ready."}
        except Exception as e:
            return JSONResponse({"success": False, "message": f"Keys saved, but initialization failed: {str(e)}"}, status_code=500)
            
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


@app.get("/settings")
async def get_settings():
    """Return current settings for frontend pre-population (V10.2 UX fix)."""
    from sakura_assistant.utils.pathing import get_project_root
    
    # Load .env values (masked for security)
    def mask_key(key: str) -> str:
        val = os.getenv(key, "")
        if val and len(val) > 8:
            return val[:4] + "..." + val[-4:]
        return "***" if val else ""
    
    # Load user settings
    settings_path = os.path.join(get_project_root(), "data", "user_settings.json")
    user_settings = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                user_settings = json.load(f)
        except:
            pass
    
    return {
        # API Keys (masked)
        "GROQ_API_KEY": mask_key("GROQ_API_KEY"),
        "TAVILY_API_KEY": mask_key("TAVILY_API_KEY"),
        "GOOGLE_API_KEY": mask_key("GOOGLE_API_KEY"),
        "OPENROUTER_API_KEY": mask_key("OPENROUTER_API_KEY"),
        "SPOTIFY_CLIENT_ID": mask_key("SPOTIFY_CLIENT_ID"),
        # User personalization (not masked)
        "USER_NAME": user_settings.get("user_name", ""),
        "USER_LOCATION": user_settings.get("user_location", ""),
        "USER_BIO": user_settings.get("user_bio", ""),
        # Flags
        "has_groq": bool(os.getenv("GROQ_API_KEY")),
        "has_google": bool(os.getenv("GOOGLE_API_KEY")),
    }


@app.patch("/settings")
async def update_settings(request: Request):
    """
    Update specific settings (V13: Fix for frontend PATCH calls).
    Only updates provided fields - doesn't overwrite all settings.
    """
    from sakura_assistant.utils.pathing import get_project_root
    
    try:
        data = await request.json()
        
        # 1. Load existing .env
        env_path = os.path.join(get_project_root(), ".env")
        env_lines = []
        env_dict = {}
        
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        env_dict[key] = val
                    env_lines.append(line)
        
        # 2. Update only provided API keys
        api_key_fields = {"GROQ_API_KEY", "TAVILY_API_KEY", "OPENROUTER_API_KEY", 
                          "GOOGLE_API_KEY", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"}
        
        updated_keys = []
        for key in api_key_fields:
            if key in data and data[key].strip():
                env_dict[key] = data[key].strip()
                updated_keys.append(key)
        
        # 3. Write back .env if API keys changed
        if updated_keys:
            with open(env_path, "w") as f:
                for key, val in env_dict.items():
                    f.write(f"{key}={val}\n")
            
            # Reload env
            from dotenv import load_dotenv
            load_dotenv(env_path, override=True)
        
        # 4. Update user settings
        user_fields = {"USER_NAME": "user_name", "USER_LOCATION": "user_location", "USER_BIO": "user_bio"}
        settings_path = os.path.join(get_project_root(), "data", "user_settings.json")
        
        user_settings = {}
        if os.path.exists(settings_path):
            with open(settings_path, "r") as f:
                user_settings = json.load(f)
        
        updated_user = []
        for frontend_key, backend_key in user_fields.items():
            if frontend_key in data:
                user_settings[backend_key] = data[frontend_key].strip()
                updated_user.append(frontend_key)
        
        if updated_user:
            os.makedirs(os.path.dirname(settings_path), exist_ok=True)
            with open(settings_path, "w") as f:
                json.dump(user_settings, f, indent=2)
        
        return {
            "success": True,
            "updated_keys": updated_keys + updated_user,
            "message": f"Updated {len(updated_keys) + len(updated_user)} settings"
        }
        
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


@app.post("/settings/google-auth")
async def upload_google_auth(file: UploadFile = File(...)):
    """
    Upload Google credentials.json for Gmail/Calendar OAuth.
    V13: Fix for frontend Google Auth upload.
    """
    from sakura_assistant.utils.pathing import get_project_root
    
    try:
        # Validate file type
        if not file.filename.endswith('.json'):
            return JSONResponse({
                "success": False, 
                "message": "File must be a .json file"
            }, status_code=400)
        
        # Save to data/google/credentials.json
        google_dir = os.path.join(get_project_root(), "data", "google")
        os.makedirs(google_dir, exist_ok=True)
        
        creds_path = os.path.join(google_dir, "credentials.json")
        
        contents = await file.read()
        
        # Validate JSON structure
        try:
            creds_data = json.loads(contents)
            # Check for required OAuth keys
            if not ("installed" in creds_data or "web" in creds_data):
                return JSONResponse({
                    "success": False,
                    "message": "Invalid credentials.json - missing 'installed' or 'web' key"
                }, status_code=400)
        except json.JSONDecodeError:
            return JSONResponse({
                "success": False,
                "message": "Invalid JSON file"
            }, status_code=400)
        
        # Write file
        with open(creds_path, "wb") as f:
            f.write(contents)
        
        print(f"✅ Google credentials saved to: {creds_path}")
        
        return {
            "success": True,
            "message": "Google credentials uploaded! You may need to authorize on first use."
        }
        
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


@app.get("/health")
async def health_check():
    """Combined health check - returns ready status."""
    status = "ready"
    if SETUP_REQUIRED:
        status = "setup_required"
    elif assistant is None:
        status = "starting"
        
    return {
        "status": status,
        "system": "Sakura V10",
        "ready": assistant is not None,
        "error": INIT_ERROR
    }


@app.get("/health/live")
async def liveness():
    """Liveness probe - server process is running."""
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    """Readiness probe - fully initialized and ready to serve."""
    status = "ready"
    if SETUP_REQUIRED:
        status = "setup_required"
    elif assistant is None:
        status = "initializing"
        
    return {
        "status": status,
        "ready": assistant is not None
    }


# ============================================================================
# OBSERVABILITY API (V10.5)
# ============================================================================

@app.get("/api/logs")
async def get_logs(limit: int = 100):
    """
    Return parsed flight recorder logs for the dashboard.
    
    Response:
        {
            "traces": [...],
            "stats": {
                "total_queries": int,
                "success_rate": float,
                "avg_latency_s": float
            }
        }
    """
    from sakura_assistant.utils.flight_recorder import get_recorder
    recorder = get_recorder()
    return recorder.get_logs_for_api(limit=limit)

# ============================================================================
# FILE UPLOAD FOR RAG
# ============================================================================

from fastapi import UploadFile, File

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a file for RAG ingestion.
    Supports: PDF, TXT, MD, DOCX, images (PNG, JPG)
    """
    try:
        from sakura_assistant.utils.pathing import get_project_root
        from sakura_assistant.memory.ingestion.pipeline import get_ingestion_pipeline
        
        # 1. Save file to uploads directory
        uploads_dir = os.path.join(get_project_root(), "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        # Use original filename (sanitized)
        safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ")
        file_path = os.path.join(uploads_dir, safe_name)
        
        # Write file
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        print(f"📥 Saved uploaded file: {file_path}")
        
        # Check if audio file (handled by audio_tools, not RAG)
        audio_extensions = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac'}
        file_ext = os.path.splitext(safe_name)[1].lower()
        
        if file_ext in audio_extensions:
            # Audio files: Just save, don't ingest to RAG
            return {
                "success": True,
                "file_id": safe_name,
                "filename": safe_name,
                "message": f"✅ Audio file saved: '{safe_name}' (use transcribe_audio or summarize_audio)"
            }
        
        # 2. Ingest into RAG (non-audio files)
        pipeline = get_ingestion_pipeline()
        result = pipeline.ingest_file_sync(file_path)
        
        if result.get("error"):
            return JSONResponse({
                "success": False, 
                "message": result.get("message", "Ingestion failed")
            }, status_code=400)
        
        return {
            "success": True,
            "file_id": result.get("file_id"),
            "filename": result.get("filename"),
            "message": f"✅ Ingested '{result.get('filename')}'"
        }
        
    except Exception as e:
        import traceback
        print(f"❌ Upload error: {traceback.format_exc()}")
        return JSONResponse({
            "success": False,
            "message": str(e)
        }, status_code=500)


@app.get("/voice/status")
async def voice_status():
    """Check voice engine and wake word template status."""
    import os
    
    # Check templates directory
    templates_dir = os.path.join(os.path.dirname(__file__), "data", "voice", "wake_templates")
    template_count = 0
    
    if os.path.exists(templates_dir):
        template_count = len([f for f in os.listdir(templates_dir) if f.endswith('.wav')])
    
    # Check if voice engine is enabled
    voice_enabled = os.getenv("SAKURA_ENABLE_VOICE") == "true"
    
    return {
        "enabled": voice_enabled,
        "wake_word_configured": template_count >= 3,
        "template_count": template_count,
        "required_templates": 3
    }


@app.post("/voice/record-template")
async def record_voice_template():
    """Record a voice template using the backend's microphone (PyAudio)."""
    import os
    import wave
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.responses import JSONResponse
    
    templates_dir = os.path.join(os.path.dirname(__file__), "data", "voice", "wake_templates")
    os.makedirs(templates_dir, exist_ok=True)
    
    # Count existing templates
    existing = len([f for f in os.listdir(templates_dir) if f.endswith('.wav')])
    
    if existing >= 3:
        return {"success": True, "message": "Already have 3 templates", "template_count": existing}
    
    def do_record():
        """Record audio using PyAudio (blocking, runs in thread)."""
        try:
            import pyaudio
            
            RATE = 16000
            CHUNK = 1024
            RECORD_SECONDS = 2
            
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK
            )
            
            print(f"🎙️ Recording template {existing + 1}...")
            frames = []
            for _ in range(int(RATE / CHUNK * RECORD_SECONDS)):
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            # Save to WAV
            filename = f"sakura_template_{existing + 1}.wav"
            filepath = os.path.join(templates_dir, filename)
            
            wf = wave.open(filepath, 'wb')
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(RATE)
            wf.writeframes(b''.join(frames))
            wf.close()
            
            print(f"✅ Saved voice template: {filename}")
            return {"success": True, "filename": filename, "template_count": existing + 1}
            
        except Exception as e:
            print(f"❌ Recording failed: {e}")
            return {"success": False, "error": str(e)}
    
    # Run recording in thread pool to not block async
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, do_record)
    
    if not result.get("success"):
        return JSONResponse(result, status_code=500)
    
    return result


# =============================================================================
# V13: ASYNC REFLECTION HELPER
# =============================================================================

async def _run_async_reflection(user_msg: str, assistant_response: str):
    """
    Run V13 reflection engine analysis as a background task.
    This doesn't block the chat response - user sees result immediately.
    """
    try:
        if assistant and hasattr(assistant, 'reflection_engine'):
            await assistant.reflection_engine.analyze_turn_async(user_msg, assistant_response)
            print(f"🔄 [Reflection] Async analysis completed")
    except Exception as e:
        print(f"⚠️ [Reflection] Background analysis failed: {e}")


# =============================================================================
# V13: CONSTRAINT STATE API (For Svelte Frontend)
# =============================================================================

@app.get("/api/constraints")
async def get_constraints():
    """
    Return all active constraints for UI visibility.
    
    Response:
        {
            "active": [
                {
                    "id": "phys_001",
                    "type": "physical",
                    "constraint": "Cannot walk - corn removal surgery",
                    "implications": ["walking", "exercise"],
                    "criticality": 0.9,
                    "created_at": "2026-01-15T20:00:00",
                    "expires_at": "2026-01-22T20:00:00"
                }
            ],
            "count": 1
        }
    """
    try:
        state_manager = get_state_manager()
        active_states = state_manager.get_all_active()
        
        return {
            "active": active_states,
            "count": len(active_states),
            "token_budget": state_manager.token_budget,
            "archived_count": len(state_manager.archived_states)
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/constraints/{constraint_id}/retire")
async def retire_constraint(constraint_id: str, request: Request):
    """
    Manually retire a constraint (user says "Mark as Resolved").
    
    Request body (optional):
        {"reason": "User marked as resolved"}
    """
    try:
        data = {}
        try:
            data = await request.json()
        except:
            pass
        
        reason = data.get("reason", "Manual retirement via UI")
        
        state_manager = get_state_manager()
        success = state_manager.retire_state(constraint_id, reason=reason)
        
        if success:
            return {"success": True, "message": f"Constraint {constraint_id} retired"}
        else:
            return JSONResponse(
                {"success": False, "message": f"Constraint {constraint_id} not found"},
                status_code=404
            )
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/api/constraints/add")
async def add_constraint(request: Request):
    """
    Manually add a constraint (emergency override / user-facing API).
    
    Request body:
        {
            "type": "physical|temporal|emotional|social|resource",
            "constraint": "Description of constraint",
            "implications": ["action1", "action2"],
            "criticality": 0.8,
            "duration_days": 7  (optional)
        }
    """
    from datetime import datetime, timedelta
    
    try:
        data = await request.json()
        
        # Validate required fields
        if not data.get("constraint"):
            return JSONResponse(
                {"success": False, "message": "constraint field is required"},
                status_code=400
            )
        
        # Generate unique ID
        state_id = f"manual_{datetime.now().strftime('%H%M%S')}"
        
        # Calculate expiry
        expires_at = None
        if data.get("duration_days"):
            expires_at = datetime.now() + timedelta(days=int(data["duration_days"]))
        
        # Create constraint
        state = ConstraintState(
            id=state_id,
            type=StateType(data.get("type", "physical")),
            status=StateStatus.ACTIVE,
            constraint=data.get("constraint", "")[:100],
            implications=data.get("implications", [])[:10],
            created_at=datetime.now(),
            expires_at=expires_at,
            last_mentioned=datetime.now(),
            criticality=min(1.0, max(0.0, float(data.get("criticality", 0.8)))),
            user_emphasis=1.0,  # Max priority for manual additions
            auto_expire=expires_at is not None
        )
        
        state_manager = get_state_manager()
        success = state_manager.add_state(state)
        
        if success:
            return {"success": True, "id": state_id, "message": "Constraint added"}
        else:
            return JSONResponse(
                {"success": False, "message": "Failed to add constraint (duplicate ID?)"},
                status_code=400
            )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.post("/chat")
async def chat(request: Request):
    """
    SSE stream for chat responses.
    
    Request body:
        {"query": str, "image_data": Optional[str]}
    
    SSE events:
        {"type": "route", "classification": "DIRECT|PLAN|CHAT", "tool_hint": str}
        {"type": "tool_start", "tool": str, "args": dict}
        {"type": "tool_end", "tool": str, "result": str, "success": bool}
        {"type": "token", "content": str}
        {"type": "done", "full_response": str}
        {"type": "error", "message": str}
    """
    global current_task, generation_cancelled
    generation_cancelled = False
    
    # Note: Auth removed - localhost-only desktop app
    
    try:
        data = await request.json()
    except:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    
    query = data.get("query", "").strip()
    image_data = data.get("image_data")
    
    if not query:
        return JSONResponse({"error": "No query provided"}, status_code=400)
    
    async def event_generator():
        global generation_cancelled
        
        # Queue for cross-task communication
        q = asyncio.Queue()
        
        # 1. Setup Flight Recorder Listener
        from sakura_assistant.utils.flight_recorder import get_recorder
        
        def trace_callback(entry):
            """Push trace events to queue."""
            try:
                # Filter useful events to reduce noise
                if entry.get("event") in ["span", "trace_start", "trace_end"]:
                    q.put_nowait({"type": "timing", "data": entry})
            except:
                pass
                
        # Register callback (Note: Single user assumption holds)
        get_recorder().set_callback(trace_callback)
        
        # 2. Define runners
        async def run_pipeline():
            """Run the actual pipeline and push result to queue."""
            try:
                # Get history context
                from sakura_assistant.memory.faiss_store import get_memory_store
                store = get_memory_store()
                current_history = store.conversation_history
                
                # Execute True Async Pipeline
                result = await assistant.arun(query, current_history, image_data=image_data)
                
                # Push success result
                q.put_nowait({"type": "pipeline_result", "data": result})
                
            except asyncio.CancelledError:
                print("🛑 Pipeline cancelled")
                q.put_nowait({"type": "pipeline_cancelled"})
            except Exception as e:
                import traceback
                print(f"❌ Pipeline Error: {e}")
                traceback.print_exc()
                q.put_nowait({"type": "pipeline_error", "error": str(e)})

        # 3. Start Pipeline Task
        task = asyncio.create_task(run_pipeline())
        global current_task
        current_task = task
        
        # 4. Stream Loop
        yield f"data: {json.dumps({'type': 'thinking'})}\n\n"
        
        try:
            while True:
                # Wait for next event
                event = await q.get()
                
                if generation_cancelled:
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                    break
                
                msg_type = event.get("type")
                
                # --- A. Result Handling ---
                if msg_type == "pipeline_result":
                    result = event["data"]
                    content = result.get("content", "")
                    mode = result.get("mode", "")
                    
                    # Persistence
                    try:
                        from sakura_assistant.memory.faiss_store import get_memory_store
                        store = get_memory_store()
                        store.append_to_history({"role": "user", "content": query})
                        store.append_to_history({"role": "assistant", "content": content})
                    except Exception as e:
                        print(f"⚠️ Save failed: {e}")
                    
                    # Tool events (extracted from metadata or result if available)
                    tool_used = result.get("tool_used", "None")
                    if tool_used != "None":
                        yield f"data: {json.dumps({'type': 'tool_used', 'tool': tool_used})}\n\n"
                        
                    # Stream Content
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                    
                    # TTS Trigger
                    if data.get("tts_enabled", False) and content:
                        try:
                            from sakura_assistant.utils.tts import speak_async
                            speak_async(content)
                        except: pass
                        
                    # V13: Schedule async reflection (BackgroundTask - doesn't block response)
                    try:
                        if assistant and hasattr(assistant, 'reflection_engine'):
                            asyncio.create_task(_run_async_reflection(query, content))
                    except Exception as e:
                        print(f"⚠️ Reflection scheduling failed: {e}")
                        
                    # Done
                    yield f"data: {json.dumps({'type': 'done', 'mode': mode})}\n\n"
                    break
                
                # --- B. Error/Cancel Handling ---
                elif msg_type == "pipeline_error":
                    yield f"data: {json.dumps({'type': 'error', 'message': event['error']})}\n\n"
                    break
                
                elif msg_type == "pipeline_cancelled":
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                    break
                
                # --- C. Timing/Observability Events ---
                elif msg_type == "timing":
                    entry = event["data"]
                    # Map Trace Event -> UI Event
                    if entry["event"] == "span":
                        # Convert specific log stages to UI-friendly events
                        stage = entry.get("stage", "")
                        status = entry.get("status", "")
                        content = entry.get("content", "")
                        elapsed = entry.get("elapsed_ms", 0)
                        
                        # Yield raw timing event for advanced UI
                        payload = {
                            "type": "timing",
                            "stage": stage,
                            "status": status,
                            "ms": elapsed,
                            "info": content
                        }
                        yield f"data: {json.dumps(payload)}\n\n"
                        
                    elif entry["event"] == "trace_start":
                        yield f"data: {json.dumps({'type': 'trace_start', 'id': entry['trace_id']})}\n\n"
                
                else:
                    print(f"⚠️ Unknown queue event: {msg_type}")

        except asyncio.CancelledError:
             yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
        finally:
            # Cleanup listener
            get_recorder().set_callback(None)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/stop")
async def stop():
    """Interrupt current generation."""
    global generation_cancelled
    generation_cancelled = True
    return {"status": "stopped"}


@app.get("/history")
async def get_history():
    """
    Return recent chat history for UI persistence.
    Loads from the conversation memory stored by SmartAssistant.
    """
    # print("📜 [/history] Fetching chat history...")
    try:
        from sakura_assistant.memory.faiss_store import get_memory_store
        
        store = get_memory_store()
        history = getattr(store, 'conversation_history', [])
        
        # print(f"📜 [/history] Found {len(history)} messages in memory")
        
        # Convert to UI format and limit to last 50 messages
        messages = []
        for msg in history[-50:]:
            role = msg.get("role", "unknown")
            # Normalize role names for frontend
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            
            messages.append({
                "role": role,
                "content": msg.get("content", "")
            })
        
        # print(f"📜 [/history] Returning {len(messages)} messages to frontend")
        return {"messages": messages}
    except ImportError as e:
        print(f"⚠️ History module not available: {e}")
        return {"messages": []}
    except Exception as e:
        print(f"⚠️ History load failed: {e}")
        return {"messages": [], "error": str(e)}


@app.post("/clear")
async def clear_all():
    """
    Clear all chat history, World Graph, and episodic memory.
    Used by UI "Clear Chat" button.
    """
    global assistant
    
    if not assistant:
        return {"success": False, "error": "Assistant not initialized"}
    
    try:
        # 1. Clear conversation memory (in-memory)
        if hasattr(assistant, 'memory') and assistant.memory:
            assistant.memory.clear()
            print("🗑️ Conversation memory cleared")
        
        # 2. Reset World Graph
        if hasattr(assistant, 'world_graph'):
            assistant.world_graph.reset()
            assistant.world_graph.save()
            print("🗑️ World Graph reset")
        
        # 3. Clear FAISS store's in-memory conversation history
        try:
            from sakura_assistant.memory.faiss_store import get_memory_store
            store = get_memory_store()
            store.conversation_history.clear()
            print("🗑️ FAISS conversation history cleared (in-memory)")
        except Exception as e:
            print(f"⚠️ FAISS clear failed: {e}")
        
        # 4. Delete conversation_history.json file
        import os
        history_path = os.path.join(os.path.dirname(__file__), "data", "conversation_history.json")
        if os.path.exists(history_path):
            os.remove(history_path)
            print(f"🗑️ Deleted {history_path}")
        
        return {"success": True, "message": "All memory cleared"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.post("/shutdown")
async def shutdown():
    """
    Graceful shutdown - save World Graph and conversation history before exit.
    Called by Tauri before force-killing the process.
    """
    if assistant and hasattr(assistant, 'world_graph'):
        assistant.world_graph.save()
        print("💾 World Graph saved via /shutdown")
    
    # CRITICAL: Flush conversation history to disk
    try:
        from sakura_assistant.memory.faiss_store import get_memory_store
        store = get_memory_store()
        store.flush_saves()
        print(f"💾 Conversation history saved ({len(store.conversation_history)} messages)")
    except Exception as e:
        print(f"⚠️ Failed to flush history on shutdown: {e}")
    
    # Exit after response is sent
    import threading
    def delayed_exit():
        import time
        time.sleep(0.1)
        os._exit(0)
    
    threading.Thread(target=delayed_exit, daemon=True).start()
    return {"status": "shutting_down"}


@app.post("/voice/speak")
async def voice_speak(request: Request):
    """Manually trigger TTS for a given text."""
    try:
        data = await request.json()
        text = data.get("text", "")
        if not text:
            return {"status": "error", "message": "No text provided"}
            
        # Use existing TTS utility
        from sakura_assistant.utils.tts import speak_async
        speak_async(text)
        return {"status": "speaking"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/voice/trigger")
async def voice_trigger():
    """Manually trigger the Voice Engine logic."""
    if "voice_engine" in globals() and globals()["voice_engine"]:
        globals()["voice_engine"].manual_trigger()
        return {"status": "triggered"}
    return {"status": "error", "message": "Voice Engine not active (run with --voice)"}



@app.get("/state")
async def get_state():
    """
    Return World Graph state for UI visualization.
    
    Response:
        {
            "mood": "neutral|frustrated|playful|urgent|curious",
            "intent_adjustment": str,
            "recent_actions": [str],
            "focus_entity": str|null,
            "entities": {entity_id: {...}}
        }
    """
    if not assistant or not hasattr(assistant, 'world_graph'):
        return {"error": "Assistant not ready"}
    
    graph = assistant.world_graph
    
    # Get recent actions
    recent_actions = []
    try:
        for action in graph.get_recent_actions(5):
            recent_actions.append({
                "tool": action.tool,
                "result_preview": str(action.result)[:100] if action.result else None,
                "success": action.success
            })
    except:
        pass
    
    # Get current mood/intent
    mood = "neutral"
    try:
        if hasattr(graph, 'current_user_intent'):
            mood = graph.current_user_intent.value
    except:
        pass
    
    # Get intent adjustment (EQ layer)
    intent_adjustment = ""
    try:
        intent_adjustment = graph.get_intent_adjustment()
    except:
        pass
    
    return {
        "mood": mood,
        "intent_adjustment": intent_adjustment,
        "recent_actions": recent_actions,
        "focus_entity": getattr(graph, 'focus_entity', None),
    }


# ══════════════════════════════════════════════════════════════════════════════
# V14: DREAM JOURNAL API
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/dreams")
async def get_dreams(limit: int = 10):
    """
    V14: Get recent Dream Journal entries.
    Shows what Sakura "learned" during sleep cycles.
    """
    try:
        dreams = get_dream_journal(limit)
        
        if not dreams:
            return {
                "dreams": [],
                "message": "No dreams yet. Check back after app restart!",
                "tip": "Dreams are crystallized from conversation summaries on startup (24h cooldown)."
            }
        
        return {
            "dreams": dreams,
            "total": len(dreams),
            "description": "Each entry represents a 'sleep cycle' where facts were extracted from conversations."
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.get("/api/constraints")
async def get_active_constraints():
    """
    V14: Get active constraints from World Graph.
    """
    if not assistant:
        return {"constraints": [], "error": "Assistant not initialized"}
    
    try:
        wg = assistant.world_graph
        constraints = [
            {
                "id": e.id,
                "summary": e.summary,
                "type": e.attributes.get("constraint_type", "unknown"),
                "implications": e.attributes.get("implications", []),
                "criticality": e.attributes.get("criticality", 0.5),
                "lifecycle": e.lifecycle.value if hasattr(e.lifecycle, 'value') else str(e.lifecycle)
            }
            for e in wg.entities.values()
            if e.id.startswith("constraint:")
        ]
        
        return {
            "constraints": sorted(constraints, key=lambda x: x["criticality"], reverse=True),
            "total": len(constraints)
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


# ══════════════════════════════════════════════════════════════════════════════
# V15: PROACTIVE NOTIFICATION SYSTEM
# ══════════════════════════════════════════════════════════════════════════════

from datetime import datetime

# Connected WebSocket clients for proactive messages
proactive_clients: list = []


@app.websocket("/ws/proactive")
async def proactive_websocket(websocket: WebSocket):
    """
    V15: WebSocket for proactive notifications.
    Frontend connects here to receive Sakura's check-in messages.
    """
    await websocket.accept()
    proactive_clients.append(websocket)
    print(f"💌 [Proactive] Client connected ({len(proactive_clients)} total)")
    
    try:
        while True:
            # Keep connection alive, wait for disconnect
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        if websocket in proactive_clients:
            proactive_clients.remove(websocket)
        print(f"💌 [Proactive] Client disconnected ({len(proactive_clients)} total)")


async def send_proactive_message(message: str):
    """
    V15: Broadcast proactive message to all connected clients.
    Also triggers TTS if available.
    """
    if not proactive_clients:
        print("⚠️ [Proactive] No clients connected, message lost")
        return False
    
    payload = {
        "type": "proactive_message",
        "content": message,
        "timestamp": datetime.now().isoformat(),
        "action": "focus_window"
    }
    
    # Broadcast to all connected clients
    disconnected = []
    for client in proactive_clients:
        try:
            await client.send_json(payload)
        except Exception:
            disconnected.append(client)
    
    for client in disconnected:
        if client in proactive_clients:
            proactive_clients.remove(client)
    
    print(f"💌 [Proactive] Sent to {len(proactive_clients)} clients: {message[:50]}...")
    
    # V15: Speak with Kokoro TTS, then offload
    await speak_and_offload(message)
    
    return True


async def speak_and_offload(message: str):
    """
    V15.2.1: Speak message with Kokoro TTS, then offload to conserve CPU.
    Includes CPU Guard to skip TTS when system is under heavy load.
    """
    try:
        # V15.2.1: CPU Guard - Skip TTS if system is under heavy load
        try:
            import psutil
            cpu_usage = psutil.cpu_percent(interval=0.1)
            if cpu_usage > 80:
                print(f"🛡️ [TTS] CPU Guard: {cpu_usage:.0f}% > 80%, skipping TTS")
                return
        except ImportError:
            pass  # psutil not available, proceed without guard
        
        from sakura_assistant.core.tts import get_tts_engine
        
        tts = get_tts_engine()
        if tts is None:
            print("🔇 [TTS] Not available, skipping voice")
            return
        
        print(f"🔊 [TTS] Speaking: {message[:50]}...")
        await tts.speak_async(message)
        
        tts.offload()
        print("💾 [TTS] Offloaded to conserve CPU")
        
    except ImportError:
        print("🔇 [TTS] Module not available")
    except Exception as e:
        print(f"⚠️ [TTS] Speak failed: {e}")


@app.get("/api/desire")
async def get_desire_state():
    """V15.2.1: Get current DesireSystem state with reactive theme."""
    try:
        from sakura_assistant.core.cognitive.desire import get_desire_system
        from sakura_assistant.core.cognitive.state import get_proactive_state
        
        ds = get_desire_system()
        pstate = get_proactive_state()
        state = ds.get_state()
        mood = ds.get_mood()
        should_initiate, reason = ds.should_initiate()
        
        # V15.2.1: Get theme for current mood
        theme = MOOD_THEMES.get(mood.value, MOOD_THEMES["content"])
        
        return {
            "state": {
                "social_battery": round(state.social_battery, 2),
                "loneliness": round(state.loneliness, 2),
                "curiosity": round(state.curiosity, 2),
                "duty": round(state.duty, 2),
                "messages_today": state.messages_today,
                "initiations_today": state.initiations_today
            },
            "mood": mood.value,
            "theme": theme,  # V15.2.1: Reactive UI theme
            "ui_visible": pstate.ui_visible,  # V15.2.1: Bubble state
            "would_initiate": should_initiate,
            "initiation_reason": reason
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/proactive/test")
async def test_proactive_message():
    """V15: Test endpoint to trigger a proactive message."""
    from sakura_assistant.core.cognitive.proactive import get_proactive_scheduler
    
    scheduler = get_proactive_scheduler()
    message = scheduler.pop_initiation()
    
    if not message:
        return {"status": "no_messages", "tip": "Run sleep cycle to generate icebreakers"}
    
    success = await send_proactive_message(message)
    return {
        "status": "sent" if success else "no_clients",
        "message": message,
        "clients_connected": len(proactive_clients)
    }


def setup_proactive_callback():
    """V15: Wire up the proactive scheduler to use WebSocket sender."""
    try:
        from sakura_assistant.core.cognitive.proactive import get_proactive_scheduler
        scheduler = get_proactive_scheduler()
        scheduler.websocket_callback = send_proactive_message
        print("🔗 [Proactive] WebSocket callback wired")
    except Exception as e:
        print(f"⚠️ [Proactive] Callback setup failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# V15.2.1: BUBBLE-GATE VISIBILITY API
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/ui/visibility")
async def set_ui_visibility(request: Request):
    """
    V15.2.1: Set UI visibility state (Bubble-Gate).
    
    When visibility becomes True and there's a pending message,
    it will be immediately delivered (if not expired by TTL).
    """
    try:
        body = await request.json()
        visible = body.get("visible", True)
        
        from sakura_assistant.core.cognitive.state import get_proactive_state
        state = get_proactive_state()
        
        # Update visibility and check for pending messages
        pending_message = state.set_visibility(visible)
        
        response = {
            "status": "ok",
            "ui_visible": state.ui_visible,
            "had_pending": pending_message is not None
        }
        
        # If there was a pending message, send it now
        if pending_message:
            success = await send_proactive_message(pending_message)
            response["message_sent"] = success
            response["message_preview"] = pending_message[:50] + "..." if len(pending_message) > 50 else pending_message
        
        return response
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/ui/state")
async def get_ui_state():
    """V15.2.1: Get current UI visibility state for debugging."""
    try:
        from sakura_assistant.core.cognitive.state import get_proactive_state
        state = get_proactive_state()
        
        return {
            "ui_visible": state.ui_visible,
            "has_pending": state.pending_initiation is not None,
            "pending_age_seconds": (
                time.time() - state.pending_initiation["timestamp"]
                if state.pending_initiation else None
            )
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# V15.2.1: MOOD THEME PALETTES
# ══════════════════════════════════════════════════════════════════════════════

MOOD_THEMES = {
    "energetic": {
        "primary": "#ff69b4",      # Hot Pink
        "bg": "#1e1e24",           # Dark
        "glow": "rgba(255, 105, 180, 0.4)",
        "accent": "#ffd700"        # Gold
    },
    "content": {
        "primary": "#ffb7b2",      # Soft Pink
        "bg": "#1e1e24",
        "glow": "rgba(255, 183, 178, 0.3)",
        "accent": "#8888ff"
    },
    "tired": {
        "primary": "#a89f91",      # Muted
        "bg": "#18181c",           # Darker
        "glow": "rgba(168, 159, 145, 0.2)",
        "accent": "#666666"
    },
    "melancholic": {
        "primary": "#7b9eb8",      # Blue-Gray
        "bg": "#1a1a22",           # Slightly blue-dark
        "glow": "rgba(123, 158, 184, 0.3)",
        "accent": "#5588aa"
    },
    "curious": {
        "primary": "#00e6cc",      # Teal
        "bg": "#1e1e24",
        "glow": "rgba(0, 230, 204, 0.3)",
        "accent": "#00ffcc"
    }
}


if __name__ == "__main__":
    import uvicorn
    import argparse
    import threading
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", action="store_true", help="Enable Voice Engine (Wake Word)")
    args = parser.parse_args()
    
    port = int(os.getenv("SAKURA_PORT", "3210"))
    print(f"🚀 Sakura Backend starting on port {port}")
    
    # Start Voice Engine if requested
    if args.voice:
        try:
            print("🎙️ Starting Voice Engine...")
            from sakura_assistant.core.llm import SmartAssistant
            from sakura_assistant.core.voice_engine import VoiceEngine
            
            # We need to wait for 'assistant' to be init by lifespan, 
            # BUT uvicorn lifespan runs async.
            # Workaround: VoiceEngine needs the assistant instance.
            # Easier approach: Init VoiceEngine inside lifespan startup if flag set.
            # But we can't easily pass args to lifespan.
            # So we set a global flag here.
            os.environ["SAKURA_ENABLE_VOICE"] = "true"
        except Exception as e:
            print(f"❌ Failed to queue Voice Engine: {e}")
    
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False  # Reduce noise
    )
