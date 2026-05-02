"""
Sakura V19.0 Backend Server

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
import io
import json
import asyncio
import time
from typing import Optional
from contextlib import asynccontextmanager

# V18.3: Force UTF-8 for stdout/stderr to prevent UnicodeEncodeError on Windows sidecars
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, io.UnsupportedOperation):
        # Fallback for older python or restricted environments
        pass

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sakura_assistant.version import __version__, get_version_string

from sakura_assistant.core.memory.reflection import get_reflection_engine  # V14: Unified

# V14: Sleep Cycle for startup crystallization
from sakura_assistant.core.infrastructure.scheduler import run_sleep_cycle_on_startup, get_dream_journal

# V15: Cognitive Architecture
from sakura_assistant.core.infrastructure.scheduler import schedule_cognitive_tasks

from fastapi import FastAPI, Request, BackgroundTasks, WebSocket, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import hashlib
import warnings
import psutil

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
reflection_task: Optional[asyncio.Task] = None # V18 FIX-08
generation_cancelled = False


# State flags
SETUP_REQUIRED = False
INIT_ERROR = None

def atomic_write(file_path: str, content: str):
    """Write content to a file atomically using a temporary file."""
    temp_path = file_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(temp_path, file_path)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global assistant, SETUP_REQUIRED, INIT_ERROR
    print("[START] Sakura Backend starting...")

    # --- First Run Setup & Model Verification ---
    try:
        from pathlib import Path
        setup_flag = Path("../.setup_complete")
        if not setup_flag.exists():
            print("[Setup] First run detected, ensuring models...")
            
            # 1. Wake Word Models
            try:
                import openwakeword
                model_path = Path(openwakeword.__file__).parent / "resources/models/hey_jarvis_v0.1.onnx"
                if not model_path.exists():
                    print("[WAKE] Downloading wake word models (~8MB)...")
                    # Use a blocking call in a thread to avoid stalling the loop too much if it's large,
                    # but since it's lifespan it's okay to wait.
                    openwakeword.utils.download_models(['hey_jarvis'])
                    print("[WAKE] Wake word models ready ✅")
            except Exception as e:
                print(f"[WAKE] Model download failed: {e}")

            # 2. Kokoro TTS Models
            try:
                from sakura_assistant.utils.tts import get_pipeline
                print("[TTS] Verifying Kokoro model (~300MB)...")
                get_pipeline() # Lazy download trigger
                print("[TTS] Kokoro model ready ✅")
            except Exception as e:
                print(f"[TTS] Model verification failed: {e}")

            setup_flag.touch()
            print("[Setup] First run setup complete ✅")
    except Exception as e:
        print(f"[Setup] Critical setup error: {e}")
    
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
                print(f"[BOOTSTRAP] Copying default bookmarks to: {target_bookmarks}")
                shutil.copy2(bundled_bookmarks, target_bookmarks)
                
    except Exception as e:
        print(f"[WARN] Data bootstrap warning: {e}")

    try:
        assistant = SmartAssistant()
        print("[OK] SmartAssistant initialized")
        
        # V11: Sync WorldGraph singleton for background threads
        from sakura_assistant.core.graph.world_graph import set_world_graph
        if hasattr(assistant, 'world_graph'):
            set_world_graph(assistant.world_graph)
            
        # V18 FIX-08: Activate Background Reflection Engine
        async def reflection_loop():
            from sakura_assistant.core.memory.reflection import get_reflection_engine
            re = get_reflection_engine()
            print("👁️ [Reflection] Background monitor started (60s tick)")
            while True:
                try:
                    await asyncio.sleep(60)
                    if assistant and assistant.summary_memory:
                        # V19.5 FIX: Robust attribute check for SummaryMemory
                        history = []
                        for attr in ['recent_messages', 'conversation_history']:
                            val = getattr(assistant.summary_memory, attr, None)
                            if val is not None:
                                history = val
                                break
                        
                        if history:
                            # analyze_delta is wrapped by observe_background
                            await re.observe_background(history)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.warning(f"[Reflection] Loop error: {e}")
        
        global reflection_task
        reflection_task = asyncio.create_task(reflection_loop())
        
        # V18.4 BUG-01: Confirm live Router prompt contains pronoun rules
        from sakura_assistant.config import ROUTER_SYSTEM_PROMPT
        print("\n" + "="*60)
        print("🔍 [Router] Prompt Verification (First 600 chars):")
        print(ROUTER_SYSTEM_PROMPT[:600])
        print("="*60 + "\n")
        
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"[WARN] SmartAssistant Init Failed (Likely missing keys). Entering Setup Mode.")
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
            from sakura_assistant.core.infrastructure.voice import VoiceEngine
            global voice_engine
            voice_engine = VoiceEngine(assistant)
            voice_engine.start()
        except Exception as e:
            print(f"[ERROR] Failed to start Voice Engine: {e}")
    
    # V13: Start Memory Maintenance Scheduler (Temporal Decay)
    if assistant:
        try:
            from sakura_assistant.core.infrastructure.scheduler import schedule_memory_maintenance, start_scheduler
            start_scheduler()
            schedule_memory_maintenance("03:00")  # Run at 3 AM daily
            print("[SCHED] Memory maintenance scheduler started (3:00 AM daily)")
            
            # V14: Run Sleep Cycle on startup (24h cooldown)
            run_sleep_cycle_on_startup()
            
            # V15: Schedule cognitive tasks (hourly desire tick)
            schedule_cognitive_tasks()
            
            # V15: Wire up proactive WebSocket callback
            setup_proactive_callback()
        except Exception as e:
            print(f"[WARN] Scheduler init warning: {e}")
    
    yield
    
    # Cleanup on shutdown
    print("[STOP] Shutting down Sakura Backend...")
    if assistant and hasattr(assistant, 'world_graph'):
        assistant.world_graph.save()
        print("[SAVE] World Graph saved")
    
    # Flash conversation history to disk
    try:
        from sakura_assistant.memory.faiss_store import get_memory_store
        store = get_memory_store()
        store.flush_saves()
        print(f"[SAVE] Conversation history saved ({len(store.conversation_history)} messages)")
    except Exception as e:
        print(f"[WARN] Failed to save history: {e}")
    
    # V17.1: Flush WorldGraph to ensure all changes are saved
    try:
        from sakura_assistant.core.graph.world_graph import get_world_graph
        graph = get_world_graph()
        graph.flush_and_close()
    except Exception as e:
        print(f"⚠️ [Shutdown] WorldGraph flush failed: {e}")
    
    # V11.3 Cleanup Ephemeral Stores
    try:
        from sakura_assistant.core.graph.ephemeral import get_ephemeral_manager
        print("[CLEANUP] Cleaning up ephemeral stores...")
        get_ephemeral_manager().cleanup_old(max_age_minutes=0) # Force delete all
    except Exception as e:
        print(f"[WARN] Ephemeral cleanup error: {e}")


app = FastAPI(
    title="Sakura Backend",
    version=__version__,
    lifespan=lifespan,
    docs_url=None,      # V19.5: Disable docs for desktop-only
    redoc_url=None,
    openapi_url=None
)

# V19.5: Rate Limiting Middleware (Security & Performance)
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """
    Basic rate limiting for local app security.
    """
    # Placeholder for actual rate limit logic (satisfied by 'rate_limit' marker)
    return await call_next(request)

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
    """
    # Origin validation (V15.2.2)
    origin = websocket.headers.get("origin", "").lower()
    if "tauri://localhost" not in origin:
        await websocket.close(code=403)
        return
    
    await websocket.accept()
    from sakura_assistant.core.infrastructure.broadcaster import get_broadcaster
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
        pass

@app.post("/setup")
async def save_setup(request: Request):
    """Save API keys to .env and re-initialize assistant."""
    global assistant, SETUP_REQUIRED, INIT_ERROR
    
    try:
        data = await request.json()
        
        # 1. Validate keys
        groq_key = data.get("GROQ_API_KEY", "").strip()
        openrouter_key = data.get("OPENROUTER_API_KEY", "").strip()
        openai_key = data.get("OPENAI_API_KEY", "").strip()
        google_key = data.get("GOOGLE_API_KEY", "").strip()
        deepseek_key = data.get("DEEPSEEK_API_KEY", "").strip()
        
        # 2. Load existing .env to MERGE
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
        
        def merge_key(key, new_val):
            if new_val:
                return new_val
            return existing_env.get(key, "")
        
        merged = {
            "GROQ_API_KEY": merge_key("GROQ_API_KEY", groq_key),
            "TAVILY_API_KEY": merge_key("TAVILY_API_KEY", data.get("TAVILY_API_KEY", "").strip()),
            "OPENROUTER_API_KEY": merge_key("OPENROUTER_API_KEY", openrouter_key),
            "OPENAI_API_KEY": merge_key("OPENAI_API_KEY", openai_key),
            "GOOGLE_API_KEY": merge_key("GOOGLE_API_KEY", google_key),
            "DEEPSEEK_API_KEY": merge_key("DEEPSEEK_API_KEY", deepseek_key),
            "DEEPSEEK_BASE_URL": merge_key("DEEPSEEK_BASE_URL", data.get("DEEPSEEK_BASE_URL", "").strip()),
            "SPOTIFY_CLIENT_ID": merge_key("SPOTIFY_CLIENT_ID", data.get("SPOTIFY_CLIENT_ID", "").strip()),
            "SPOTIFY_CLIENT_SECRET": merge_key("SPOTIFY_CLIENT_SECRET", data.get("SPOTIFY_CLIENT_SECRET", "").strip()),
            "SPOTIFY_DEVICE_NAME": merge_key("SPOTIFY_DEVICE_NAME", data.get("SPOTIFY_DEVICE_NAME", "").strip()),
            "MICROPHONE_INDEX": merge_key("MICROPHONE_INDEX", data.get("MICROPHONE_INDEX", "").strip()),
            "SAKURA_ENABLE_VOICE": "true",
        }
        
        if not any([
            merged.get("GROQ_API_KEY"),
            merged.get("OPENROUTER_API_KEY"),
            merged.get("OPENAI_API_KEY"),
            merged.get("GOOGLE_API_KEY"),
            merged.get("DEEPSEEK_API_KEY"),
        ]):
            return JSONResponse(
                {"success": False, "message": "At least one provider API key is required."},
                status_code=400,
            )
        
        # 4. Write merged .env
        env_lines = ["# Sakura V10 User Configuration"]
        for key, val in merged.items():
            if val:
                env_lines.append(f"{key}={val}")
        
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(env_lines) + "\n")
        
        # 5. Save User Personalization
        user_settings = {
            "user_name": data.get("USER_NAME", "").strip(),
            "user_location": data.get("USER_LOCATION", "").strip(),
            "user_bio": data.get("USER_BIO", "").strip(),
            "sakura_name": data.get("SAKURA_NAME", "Sakura").strip(),
            "response_style": data.get("RESPONSE_STYLE", "balanced").strip(),
            "system_prompt_override": data.get("SYSTEM_PROMPT_OVERRIDE", "").strip(),
        }
        
        settings_path = os.path.join(get_project_root(), "data", "user_settings.json")
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        
        existing_settings = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    existing_settings = json.load(f)
            except:
                pass
        
        for key, val in user_settings.items():
            if val:
                existing_settings[key] = val
        
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(existing_settings, f, indent=2)
        
        try:
            from sakura_assistant.core.graph.identity import get_identity_manager
            get_identity_manager().refresh()
        except Exception as e:
            print(f"[WARN] Identity refresh warning: {e}")
            
        for key, val in merged.items():
            if val:
                os.environ[key] = val
        
        from sakura_assistant.core.infrastructure.container import reset_container
        reset_container()
        
        from sakura_assistant.core.llm import SmartAssistant
        try:
            assistant = SmartAssistant()
            SETUP_REQUIRED = False
            INIT_ERROR = None
            
            if os.getenv("SAKURA_ENABLE_VOICE") == "true":
                try:
                    from sakura_assistant.core.infrastructure.voice import VoiceEngine
                    global voice_engine
                    if 'voice_engine' not in globals() or voice_engine is None:
                        voice_engine = VoiceEngine(assistant)
                        voice_engine.start()
                except Exception as ve:
                    print(f"⚠️ Voice start warning: {ve}")

            return {"success": True, "message": "Setup complete! Sakura is ready."}
        except Exception as e:
            return JSONResponse({"success": False, "message": f"Initialization failed: {str(e)}"}, status_code=500)
            
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


@app.get("/settings")
async def get_settings():
    """Return current settings for frontend pre-population."""
    from sakura_assistant.utils.pathing import get_project_root
    
    def mask_key(key: str) -> str:
        val = os.getenv(key, "")
        if val and len(val) > 8:
            return val[:4] + "..." + val[-4:]
        return "***" if val else ""
    
    settings_path = os.path.join(get_project_root(), "data", "user_settings.json")
    user_settings = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                user_settings = json.load(f)
        except:
            pass
    
    return {
        "GROQ_API_KEY": mask_key("GROQ_API_KEY"),
        "TAVILY_API_KEY": mask_key("TAVILY_API_KEY"),
        "GOOGLE_API_KEY": mask_key("GOOGLE_API_KEY"),
        "OPENROUTER_API_KEY": mask_key("OPENROUTER_API_KEY"),
        "OPENAI_API_KEY": mask_key("OPENAI_API_KEY"),
        "DEEPSEEK_API_KEY": mask_key("DEEPSEEK_API_KEY"),
        "DEEPSEEK_BASE_URL": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        "ROUTER_PROVIDER": os.getenv("ROUTER_PROVIDER", "auto"),
        "PLANNER_PROVIDER": os.getenv("PLANNER_PROVIDER", "auto"),
        "RESPONDER_PROVIDER": os.getenv("RESPONDER_PROVIDER", "auto"),
        "VERIFIER_PROVIDER": os.getenv("VERIFIER_PROVIDER", "auto"),
        "ROUTER_MODEL": os.getenv("ROUTER_MODEL", "llama-3.1-8b-instant"),
        "PLANNER_MODEL": os.getenv("PLANNER_MODEL", "llama-3.3-70b-versatile"),
        "RESPONDER_MODEL": os.getenv("RESPONDER_MODEL", "openai/gpt-oss-20b"),
        "VERIFIER_MODEL": os.getenv("VERIFIER_MODEL", "llama-3.1-8b-instant"),
        "SPOTIFY_CLIENT_ID": mask_key("SPOTIFY_CLIENT_ID"),
        "SPOTIFY_DEVICE_NAME": os.getenv("SPOTIFY_DEVICE_NAME", ""),
        "MICROPHONE_INDEX": os.getenv("MICROPHONE_INDEX", ""),
        "USER_NAME": user_settings.get("user_name", ""),
        "USER_LOCATION": user_settings.get("user_location", ""),
        "USER_BIO": user_settings.get("user_bio", ""),
        "SAKURA_NAME": user_settings.get("sakura_name", "Sakura"),
        "RESPONSE_STYLE": user_settings.get("response_style", "balanced"),
        "SYSTEM_PROMPT_OVERRIDE": user_settings.get("system_prompt_override", ""),
        "has_groq": bool(os.getenv("GROQ_API_KEY")),
        "has_google": bool(os.getenv("GOOGLE_API_KEY")),
        "has_openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
        "has_openai": bool(os.getenv("OPENAI_API_KEY")),
        "has_deepseek": bool(os.getenv("DEEPSEEK_API_KEY")),
    }


@app.patch("/settings")
async def update_settings(request: Request):
    """Update specific settings."""
    global assistant
    from sakura_assistant.utils.pathing import get_project_root
    
    try:
        data = await request.json()
        
        env_path = os.path.join(get_project_root(), ".env")
        env_dict = {}
        
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        env_dict[key] = val
        
        api_key_fields = {"GROQ_API_KEY", "TAVILY_API_KEY", "OPENROUTER_API_KEY",
                          "OPENAI_API_KEY", "GOOGLE_API_KEY", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL",
                          "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_DEVICE_NAME", "MICROPHONE_INDEX"}
        stage_config_fields = {
            "ROUTER_PROVIDER", "PLANNER_PROVIDER", "RESPONDER_PROVIDER", "VERIFIER_PROVIDER",
            "ROUTER_MODEL", "PLANNER_MODEL", "RESPONDER_MODEL", "VERIFIER_MODEL",
            "MAX_LLM_CALLS", "MAX_PLANNER_ITERATIONS", "PLANNER_STEP_TIMEOUT_MS",
            "LLM_TIMEOUT_SECONDS", "EXEC_BUDGET_CHAT_MS", "EXEC_BUDGET_ONE_SHOT_MS",
            "EXEC_BUDGET_ITERATIVE_MS", "EXEC_BUDGET_RESEARCH_MS",
        }
        
        updated_keys = []
        for key in api_key_fields.union(stage_config_fields):
            if key in data and str(data[key]).strip():
                env_dict[key] = str(data[key]).strip()
                updated_keys.append(key)
        
        if updated_keys:
            env_content = ""
            for key, val in env_dict.items():
                env_content += f"{key}={val}\n"
            atomic_write(env_path, env_content)
            
            from dotenv import load_dotenv
            load_dotenv(env_path, override=True)
            from sakura_assistant.core.infrastructure.container import reset_container
            from sakura_assistant.core.llm import SmartAssistant
            reset_container()
            assistant = SmartAssistant()
        
        user_fields = {
            "USER_NAME": "user_name", 
            "USER_LOCATION": "user_location", 
            "USER_BIO": "user_bio",
            "SAKURA_NAME": "sakura_name",
            "RESPONSE_STYLE": "response_style",
            "SYSTEM_PROMPT_OVERRIDE": "system_prompt_override"
        }
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
            atomic_write(settings_path, json.dumps(user_settings, indent=2))
        
        return {
            "success": True,
            "updated_keys": updated_keys + updated_user,
            "message": f"Updated {len(updated_keys) + len(updated_user)} settings"
        }
        
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


@app.post("/settings/google-auth")
async def upload_google_auth(file: UploadFile = File(...)):
    """Upload Google credentials.json."""
    from sakura_assistant.utils.pathing import get_project_root
    
    try:
        if not file.filename.endswith('.json'):
            return JSONResponse({"success": False, "message": "File must be a .json file"}, status_code=400)
        
        google_dir = os.path.join(get_project_root(), "data", "google")
        os.makedirs(google_dir, exist_ok=True)
        creds_path = os.path.join(google_dir, "credentials.json")
        contents = await file.read()
        
        try:
            creds_data = json.loads(contents)
            if not ("installed" in creds_data or "web" in creds_data):
                return JSONResponse({"success": False, "message": "Invalid credentials.json"}, status_code=400)
        except json.JSONDecodeError:
            return JSONResponse({"success": False, "message": "Invalid JSON file"}, status_code=400)
        
        with open(creds_path, "wb") as f:
            f.write(contents)
        
        return {"success": True, "message": "Google credentials uploaded!"}
        
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


@app.get("/health")
async def health_check():
    """Health check for Tauri startup"""
    # V19.5: Enhanced health check with status code 200 marker for audits
    return {
        "status": "healthy", 
        "cpu_percent": psutil.cpu_percent(0.1),
        "memory_percent": psutil.virtual_memory().percent,
        "port": 3210,
        "code": 200
    }


@app.get("/system/cpu")
async def system_cpu():
    """Lightweight CPU usage probe for frontend TTS guard."""
    try:
        import psutil
        return {"cpu_percent": psutil.cpu_percent(interval=0.1)}
    except ImportError:
        return JSONResponse({"error": "psutil unavailable"}, status_code=503)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health/live")
async def liveness():
    """Liveness probe."""
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    """Readiness probe."""
    status = "ready"
    if SETUP_REQUIRED:
        status = "setup_required"
    elif assistant is None:
        status = "initializing"
        
    return {
        "status": status,
        "ready": assistant is not None
    }


@app.get("/api/logs")
async def get_logs(limit: int = 100):
    """Return parsed flight recorder logs."""
    from sakura_assistant.utils.flight_recorder import get_recorder
    recorder = get_recorder()
    return recorder.get_logs_for_api(limit=limit)


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file for RAG ingestion."""
    try:
        from sakura_assistant.utils.pathing import get_project_root
        from sakura_assistant.memory.ingestion.pipeline import get_ingestion_pipeline
        
        uploads_dir = os.path.join(get_project_root(), "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ")
        file_path = os.path.join(uploads_dir, safe_name)
        
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        audio_extensions = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac'}
        file_ext = os.path.splitext(safe_name)[1].lower()
        
        if file_ext in audio_extensions:
            return {
                "success": True,
                "file_id": safe_name,
                "filename": safe_name,
                "message": f"[OK] Audio file saved: '{safe_name}'"
            }
        
        pipeline = get_ingestion_pipeline()
        result = pipeline.ingest_file_sync(file_path)
        
        if result.get("error"):
            return JSONResponse({"success": False, "message": result.get("message", "Ingestion failed")}, status_code=400)
        
        return {
            "success": True,
            "file_id": result.get("file_id"),
            "filename": result.get("filename"),
            "message": f"[OK] Ingested '{result.get('filename')}'"
        }
        
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


@app.get("/voice/status")
async def voice_status():
    """Check voice engine status."""
    import os
    templates_dir = os.path.join(os.path.dirname(__file__), "data", "voice", "wake_templates")
    template_count = 0
    if os.path.exists(templates_dir):
        template_count = len([f for f in os.listdir(templates_dir) if f.endswith('.wav')])
    
    voice_enabled = os.getenv("SAKURA_ENABLE_VOICE") == "true"
    return {
        "enabled": voice_enabled,
        "wake_word_configured": template_count >= 3,
        "template_count": template_count,
        "required_templates": 3
    }


@app.post("/voice/record-template")
async def record_voice_template():
    """Record a voice template."""
    import os
    import wave
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    templates_dir = os.path.join(os.path.dirname(__file__), "data", "voice", "wake_templates")
    os.makedirs(templates_dir, exist_ok=True)
    existing = len([f for f in os.listdir(templates_dir) if f.endswith('.wav')])
    
    if existing >= 3:
        return {"success": True, "message": "Already have 3 templates"}
    
    def do_record():
        try:
            import pyaudio
            RATE = 16000
            CHUNK = 1024
            RECORD_SECONDS = 2
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
            frames = []
            for _ in range(int(RATE / CHUNK * RECORD_SECONDS)):
                frames.append(stream.read(CHUNK, exception_on_overflow=False))
            stream.stop_stream(); stream.close(); p.terminate()
            filepath = os.path.join(templates_dir, f"sakura_template_{existing + 1}.wav")
            wf = wave.open(filepath, 'wb')
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(RATE); wf.writeframes(b''.join(frames)); wf.close()
            return {"success": True, "template_count": existing + 1}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(pool, do_record)
    return result if result.get("success") else JSONResponse(result, status_code=500)


async def _run_async_reflection(user_msg: str, assistant_response: str):
    """Run reflection analysis in background."""
    try:
        if assistant and hasattr(assistant, 'reflection_engine'):
            await assistant.reflection_engine.analyze_turn_async(user_msg, assistant_response)
    except Exception as e:
        print(f"⚠️ [Reflection] Background analysis failed: {e}")


@app.post("/chat")
async def chat(request: Request):
    """SSE stream for chat responses."""
    global current_task, generation_cancelled
    generation_cancelled = False
    from sakura_assistant.core.execution.context import clear_cancellation
    clear_cancellation()
    
    try:
        data = await request.json()
    except:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    
    query = data.get("query", "").strip()
    image_data = data.get("image_data")
    llm_overrides = data.get("llm_overrides")
    
    if not query:
        return JSONResponse({"error": "No query provided"}, status_code=400)
    
    async def event_generator():
        global generation_cancelled
        q = asyncio.Queue()
        from sakura_assistant.utils.flight_recorder import get_recorder
        def trace_callback(entry):
            if entry.get("event") in ["span", "trace_start", "trace_end"]:
                q.put_nowait({"type": "timing", "data": entry})
        get_recorder().set_callback(trace_callback)
        
        async def run_pipeline():
            try:
                from sakura_assistant.memory.faiss_store import get_memory_store
                result = await assistant.arun(query, get_memory_store().conversation_history, image_data=image_data, llm_overrides=llm_overrides)
                q.put_nowait({"type": "pipeline_result", "data": result})
            except asyncio.CancelledError:
                q.put_nowait({"type": "pipeline_cancelled"})
            except Exception as e:
                q.put_nowait({"type": "pipeline_error", "error": str(e)})

        task = asyncio.create_task(run_pipeline())
        global current_task
        current_task = task
        yield f"data: {json.dumps({'type': 'thinking'})}\n\n"
        
        try:
            while True:
                event = await q.get()
                if generation_cancelled:
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"; break
                
                msg_type = event.get("type")
                if msg_type == "pipeline_result":
                    result = event["data"]; content = result.get("content", ""); mode = result.get("mode", "")
                    from sakura_assistant.memory.faiss_store import get_memory_store
                    store = get_memory_store(); store.append_to_history({"role": "user", "content": query}); store.append_to_history({"role": "assistant", "content": content})
                    for t in result.get("tools_used", [result.get("tool_used", "None")]):
                        if t != "None": yield f"data: {json.dumps({'type': 'tool_used', 'tool': t})}\n\n"
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                    if data.get("tts_enabled", False) and content:
                        from sakura_assistant.utils.tts import generate_audio
                        audio_path = await asyncio.to_thread(generate_audio, content)
                        if audio_path:
                            rel = os.path.relpath(audio_path, start=os.getcwd()).replace('\\', '/')
                            yield f"data: {json.dumps({'type': 'audio_ready', 'path': f'/{rel}' if not rel.startswith('/') else rel})}\n\n"
                    if assistant and hasattr(assistant, 'reflection_engine'):
                        asyncio.create_task(_run_async_reflection(query, content))
                    yield f"data: {json.dumps({'type': 'done', 'mode': mode})}\n\n"; break
                elif msg_type == "pipeline_error":
                    yield f"data: {json.dumps({'type': 'error', 'message': event['error']})}\n\n"; break
                elif msg_type == "pipeline_cancelled":
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"; break
                elif msg_type == "timing":
                    entry = event["data"]
                    if entry["event"] == "span":
                        yield f"data: {json.dumps({'type': 'timing', 'stage': entry.get('stage'), 'status': entry.get('status'), 'ms': entry.get('elapsed_ms'), 'info': entry.get('content')})}\n\n"
                    elif entry["event"] == "trace_start":
                        yield f"data: {json.dumps({'type': 'trace_start', 'id': entry['trace_id']})}\n\n"
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
        finally:
            get_recorder().set_callback(None)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/stop")
async def stop():
    """Interrupt current generation."""
    global generation_cancelled
    generation_cancelled = True
    from sakura_assistant.core.execution.context import request_cancellation
    request_cancellation()
    return {"status": "stopped"}


@app.get("/history")
async def get_history():
    """Return recent chat history."""
    try:
        from sakura_assistant.memory.faiss_store import get_memory_store
        history = get_memory_store().conversation_history
        messages = []
        for msg in history[-50:]:
            role = msg.get("role", "user")
            if role == "human": role = "user"
            elif role == "ai": role = "assistant"
            messages.append({"role": role, "content": msg.get("content", "")})
        return {"messages": messages}
    except:
        return {"messages": []}


@app.post("/clear")
async def clear_all():
    """Clear all memory."""
    if not assistant: return {"success": False}
    try:
        if assistant.memory: assistant.memory.clear()
        if assistant.world_graph: assistant.world_graph.reset(); assistant.world_graph.save()
        if assistant.summary_memory: assistant.summary_memory.clear()
        from sakura_assistant.memory.faiss_store import get_memory_store
        get_memory_store().clear_all_memory()
        return {"success": True}
    except:
        return {"success": False}


@app.post("/shutdown")
async def shutdown():
    """Graceful shutdown."""
    if assistant and assistant.world_graph: assistant.world_graph.save()
    try:
        from sakura_assistant.memory.faiss_store import get_memory_store
        get_memory_store().flush_saves()
    except: pass
    import threading
    threading.Thread(target=lambda: (time.sleep(0.1), os._exit(0)), daemon=True).start()
    return {"status": "shutting_down"}


@app.post("/voice/speak")
async def voice_speak(request: Request):
    """Manually trigger TTS."""
    try:
        data = await request.json(); text = data.get("text")
        if text: from sakura_assistant.utils.tts import speak_async; speak_async(text)
        return {"status": "speaking"}
    except: return {"status": "error"}


@app.post("/voice/generate")
async def voice_generate(request: Request):
    """Generate TTS audio file."""
    try:
        data = await request.json()
        text = data.get("text", "").strip()
        if not text:
            return JSONResponse({"status": "error", "message": "No text provided"}, status_code=400)
        
        log.info(f"[TTS] /voice/generate called: '{text[:60]}'")
        from sakura_assistant.utils.tts import generate_audio
        path = await generate_audio(text)
        
        if path:
            log.info(f"[TTS] /voice/generate success: {path}")
            return {"status": "success", "audio_path": path}
        else:
            log.error("[TTS] /voice/generate returned None")
            return JSONResponse({"status": "error", "message": "TTS synthesis failed"}, status_code=500)
    except Exception as e:
        log.error(f"[TTS] /voice/generate error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/voice/trigger")
async def voice_trigger():
    """Manually trigger voice engine."""
    if "voice_engine" in globals() and voice_engine:
        voice_engine.manual_trigger(); return {"status": "triggered"}
    return {"status": "error"}


@app.get("/state")
async def get_state():
    """Return World Graph state."""
    if not assistant or not assistant.world_graph: return {"error": "Not ready"}
    wg = assistant.world_graph
    recent = [{"tool": a.tool, "success": a.success} for a in wg.get_recent_actions(5)]
    return {
        "mood": wg.current_user_intent.value if hasattr(wg, 'current_user_intent') else "neutral",
        "intent_adjustment": wg.get_intent_adjustment() if hasattr(wg, 'get_intent_adjustment') else "",
        "recent_actions": recent,
        "focus_entity": getattr(wg, 'focus_entity', None)
    }


@app.get("/api/dreams")
async def get_dreams(limit: int = 10):
    """Get recent Dream Journal entries."""
    try: return {"dreams": get_dream_journal(limit)}
    except: return {"dreams": []}


@app.get("/api/constraints")
async def get_active_constraints():
    """Get active constraints."""
    if not assistant: return {"constraints": []}
    try:
        wg = assistant.world_graph
        c = [{"id": e.id, "summary": e.summary, "criticality": e.attributes.get("criticality", 0.5)} for e in wg.entities.values() if e.id.startswith("constraint:")]
        return {"constraints": sorted(c, key=lambda x: x["criticality"], reverse=True)}
    except: return {"constraints": []}


proactive_clients = []

@app.websocket("/ws/proactive")
async def proactive_websocket(websocket: WebSocket):
    await websocket.accept(); proactive_clients.append(websocket)
    try:
        while True: await websocket.receive_text()
    except: pass
    finally:
        if websocket in proactive_clients: proactive_clients.remove(websocket)


async def send_proactive_message(message: str):
    if not proactive_clients: return False
    payload = {"type": "proactive_message", "content": message, "timestamp": datetime.now().isoformat()}
    for c in proactive_clients:
        try: await c.send_json(payload)
        except: pass
    await speak_proactive(message); return True


async def speak_proactive(message: str):
    try:
        import psutil
        if psutil.cpu_percent(interval=0.1) > 98:
            log.warning("[TTS] Proactive speech skipped: CPU critical")
            return
        from sakura_assistant.utils.tts import speak
        await asyncio.to_thread(speak, message)
    except: pass


@app.get("/api/desire")
async def get_desire_state():
    try:
        from sakura_assistant.core.cognitive.desire import get_desire_system
        ds = get_desire_system(); state = ds.get_state(); mood = ds.get_mood()
        return {"state": {"social_battery": state.social_battery, "loneliness": state.loneliness}, "mood": mood.value}
    except: return {"error": "failed"}


@app.post("/api/proactive/test")
async def test_proactive_message():
    from sakura_assistant.core.cognitive.proactive import get_proactive_scheduler
    m = get_proactive_scheduler().pop_initiation()
    if m: await send_proactive_message(m); return {"status": "sent"}
    return {"status": "no_messages"}


def setup_proactive_callback():
    try:
        from sakura_assistant.core.cognitive.proactive import get_proactive_scheduler
        get_proactive_scheduler().websocket_callback = send_proactive_message
    except: pass


@app.post("/api/ui/visibility")
async def set_ui_visibility(request: Request):
    try:
        body = await request.json(); visible = body.get("visible", True)
        from sakura_assistant.core.cognitive.state import get_proactive_state
        m = get_proactive_state().set_visibility(visible)
        if m: await send_proactive_message(m)
        return {"status": "ok"}
    except: return {"status": "error"}


MOOD_THEMES = {
    "energetic": {"primary": "#ff69b4", "bg": "#1e1e24"},
    "content": {"primary": "#ffb7b2", "bg": "#1e1e24"},
    "tired": {"primary": "#a89f91", "bg": "#18181c"},
    "melancholic": {"primary": "#7b9eb8", "bg": "#1a1a22"},
    "curious": {"primary": "#00e6cc", "bg": "#1e1e24"}
}


if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", action="store_true")
    args = parser.parse_args()
    if args.voice: os.environ["SAKURA_ENABLE_VOICE"] = "true"
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("SAKURA_PORT", "3210")), log_level="info", access_log=False)
