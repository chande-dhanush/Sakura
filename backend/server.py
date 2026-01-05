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

from fastapi import FastAPI, Request, BackgroundTasks
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
# The frontend and backend communicate only via localhost:8000
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
    
    yield
    
    # Cleanup on shutdown
    print("🛑 Shutting down Sakura Backend...")
    if assistant and hasattr(assistant, 'world_graph'):
        assistant.world_graph.save()
        print("💾 World Graph saved")
    
    # Flush conversation history to disk
    try:
        from sakura_assistant.memory.faiss_store import get_memory_store
        store = get_memory_store()
        store.flush_saves()
        print(f"💾 Conversation history saved ({len(store.conversation_history)} messages)")
    except Exception as e:
        print(f"⚠️ Failed to save history: {e}")


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

@app.post("/setup")
async def save_setup(request: Request):
    """Save API keys to .env and re-initialize assistant."""
    global assistant, SETUP_REQUIRED, INIT_ERROR
    
    try:
        data = await request.json()
        
        # 1. Validate keys
        groq_key = data.get("GROQ_API_KEY", "").strip()
        tavily_key = data.get("TAVILY_API_KEY", "").strip()
        
        if not groq_key:
            return JSONResponse({"success": False, "message": "Groq API Key is required"}, status_code=400)
            
        # 2. Write to .env in persistent storage
        from sakura_assistant.utils.pathing import get_project_root
        
        env_path = os.path.join(get_project_root(), ".env")
        
        # Optional fields
        openrouter_key = data.get("OPENROUTER_API_KEY", "").strip()
        spotify_id = data.get("SPOTIPY_CLIENT_ID", "").strip()
        spotify_secret = data.get("SPOTIPY_CLIENT_SECRET", "").strip()
        mic_index = data.get("MICROPHONE_INDEX", "").strip()

        env_content = f"""# Sakura V10 User Configuration
GROQ_API_KEY={groq_key}
TAVILY_API_KEY={tavily_key}
OPENROUTER_API_KEY={openrouter_key}
SPOTIPY_CLIENT_ID={spotify_id}
SPOTIPY_CLIENT_SECRET={spotify_secret}
MICROPHONE_INDEX={mic_index}
SAKURA_ENABLE_VOICE=true
"""
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content)
            
        # 3. Reload Env (Update os.environ for current process)
        os.environ["GROQ_API_KEY"] = groq_key
        if tavily_key: os.environ["TAVILY_API_KEY"] = tavily_key
        if openrouter_key: os.environ["OPENROUTER_API_KEY"] = openrouter_key
        if spotify_id: os.environ["SPOTIPY_CLIENT_ID"] = spotify_id
        if spotify_secret: os.environ["SPOTIPY_CLIENT_SECRET"] = spotify_secret
        if mic_index: os.environ["MICROPHONE_INDEX"] = mic_index
        os.environ["SAKURA_ENABLE_VOICE"] = "true"
        
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
        
        # 2. Ingest into RAG
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
        
        try:
            # Run LLM in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            
            # Emit routing event first
            yield f"data: {json.dumps({'type': 'thinking'})}\n\n"
            
            # Get latest history context
            from sakura_assistant.memory.faiss_store import get_memory_store
            store = get_memory_store()
            current_history = store.conversation_history

            # Execute the assistant (blocking call in thread pool)
            result = await loop.run_in_executor(
                None,
                lambda: assistant.run(query, current_history, image_data=image_data)
            )
            
            if generation_cancelled:
                yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                return
            
            # Extract response data
            content = result.get("content", "")
            mode = result.get("mode", "")
            tools_used = result.get("tools_used", "")
            
            # SAVE TO HISTORY for persistence
            try:
                from sakura_assistant.memory.faiss_store import get_memory_store
                store = get_memory_store()
                # Save user message
                store.append_to_history({"role": "user", "content": query})
                # Save assistant response
                store.append_to_history({"role": "assistant", "content": content})
                print(f"💾 Saved messages to history (total: {len(store.conversation_history)})")
            except Exception as save_err:
                print(f"⚠️ Failed to save to history: {save_err}")
            
            # Emit tool events if any
            if tools_used:
                for tool in tools_used.split(", "):
                    if tool:
                        yield f"data: {json.dumps({'type': 'tool_used', 'tool': tool})}\n\n"
            
            # Stream the response (for now, single chunk - can be enhanced later)
            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
            
            # [V10] Auto-TTS Trigger (Quick Search Mode)
            tts_enabled = data.get("tts_enabled", False)
            if tts_enabled and content:
                try:
                    from sakura_assistant.utils.tts import speak_async
                    print(f"🗣️ Auto-TTS (Quick Search): '{content[:30]}...'")
                    speak_async(content)
                except Exception as tts_e:
                    print(f"❌ Auto-TTS Failed: {tts_e}")

            # Done event
            yield f"data: {json.dumps({'type': 'done', 'mode': mode})}\n\n"
            
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
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


if __name__ == "__main__":
    import uvicorn
    import argparse
    import threading
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--voice", action="store_true", help="Enable Voice Engine (Wake Word)")
    args = parser.parse_args()
    
    port = int(os.getenv("SAKURA_PORT", "8000"))
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
