import os
import time
import threading
from datetime import datetime
from typing import Optional
from langchain_core.tools import tool
from .common import log_api_call, log_api_result, _validate_path

# V18 Vision Integration
try:
    from ..models.vision_client import VisionClient
    from ..execution.context import execution_context_var
    from ...utils.flight_recorder import get_recorder
    _vision_client = VisionClient(flight_recorder=get_recorder())
except ImportError:
    _vision_client = None
    execution_context_var = None

try:
    from AppOpener import open as app_open
except Exception as e:
    print(f"⚠️ AppOpener failed to load in system.py: {e}")
    app_open = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    import pytesseract
    from PIL import ImageGrab
except ImportError:
    pytesseract = None
    ImageGrab = None

# --- Hardware Tools ---

@tool
def get_system_info() -> str:
    """Get system information: time, date, CPU, memory, battery."""
    now = datetime.now()
    result = [
        f" Time: {now.strftime('%I:%M %p')}",
        f" Date: {now.strftime('%A, %B %d, %Y')}"
    ]
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.5)
        result.append(f" CPU: {cpu_percent}%")
        mem = psutil.virtual_memory()
        result.append(f" RAM: {mem.percent}% used ({mem.used // (1024**3)}/{mem.total // (1024**3)} GB)")
        if hasattr(psutil, 'sensors_battery'):
            battery = psutil.sensors_battery()
            if battery:
                status = " Charging" if battery.power_plugged else " On Battery"
                result.append(f"{status}: {battery.percent}%")
        disk = psutil.disk_usage('/')
        result.append(f" Disk: {disk.percent}% used")
    except ImportError:
        result.append("⚠️ Install 'psutil' for stats.")
    except Exception as e:
        result.append(f"⚠️ Stats unavailable: {e}")
    return "\n".join(result)

@tool
def read_screen(prompt: str = "Describe what is on the screen in detail.", monitor: int = 0) -> str:
    """
    Take a screenshot and analyze it with AI vision.
    
    monitor=0 -> primary/first/main screen (default)
    monitor=1 -> second/secondary screen
    monitor=2 -> third screen
    """
    try:
        import mss
        from PIL import Image
        
        # 1. Capture screen (Keep existing logic as requested)
        with mss.mss() as sct:
            if monitor >= len(sct.monitors):
                return f" Monitor {monitor} not found."
            sct_img = sct.grab(sct.monitors[monitor])
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
        # 2. Vision analysis (New V18 logic)
        if not _vision_client:
            return " Vision analysis unavailable (module import error)."

        # Try to pull context from execution_context_var
        context_str = None
        if execution_context_var:
            try:
                ctx = execution_context_var.get()
                if ctx:
                    context_str = ctx.user_input
            except Exception:
                pass # contextvar may not be set in this thread/task

        # Prompt for detailed desktop analysis
        vision_prompt = (
            "Describe what is on the screen. List all visible text verbatim, "
            "identify UI elements, buttons, and any error messages."
        )
        
        # We use an event loop to run the async analyze in this sync tool
        # Sakura tools are typically synchronous but can use asyncio if needed.
        # Given system.py already uses threading/mss, we safely run the analyzer.
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # In async context? Unusual for current tool architecture, but safe
                import nest_asyncio
                nest_asyncio.apply()
                description = loop.run_until_complete(_vision_client.analyze(img, prompt=vision_prompt, context=context_str))
            else:
                description = loop.run_until_complete(_vision_client.analyze(img, prompt=vision_prompt, context=context_str))
        except RuntimeError:
            description = asyncio.run(_vision_client.analyze(img, prompt=vision_prompt, context=context_str))

        if not description or len(description.strip()) < 5:
             return "⚠️ Vision model returned an empty or invalid response."

        return description

    except Exception as e:
        return f" Screen capture / analysis failed: {e}"

# --- OS Tools ---

@tool
def open_app(app_name: str) -> str:
    """Open a desktop application."""
    if not app_open:
        return os.system(f"start {app_name}") and f"Launched {app_name}"
    try:
        app_open(app_name, match_closest=True, output=False)
        return f" Opened '{app_name}'."
    except Exception as e:
        return f" Error: {e}"

@tool
def clipboard_read() -> str:
    """Read clipboard content."""
    if not pyperclip: return " pyperclip not installed."
    return pyperclip.paste()

@tool
def clipboard_write(text: str) -> str:
    """Write to clipboard."""
    if not pyperclip: return " pyperclip not installed."
    pyperclip.copy(text)
    return " Copied."

# --- File Tools ---

@tool
def file_read(path: str, max_chars: int = 5000) -> str:
    """Read a local file."""
    # V17.2 SECURITY FIX: Validate path before reading
    try:
        from sakura_assistant.core.execution.executor import validate_path
    except ImportError:
        return f"⛔ Security: Path validation module not found. File access denied."
    
    try:
        if not validate_path(path):
             return f"⛔ Access denied: Path validation failed for '{path}'"
    except Exception as e:
        return f"⛔ Security check error: {e}"

    try:
        safe_path = _validate_path(path)
        if not os.path.exists(safe_path): return " File not found."
        
        with open(safe_path, 'r', encoding='utf-8') as f:
            content = f.read(max_chars)
        return content
    except Exception as e:
        return f" Read error: {e}"

@tool
def file_write(path: str, content: str) -> str:
    """Write to a local file."""
    # V17.2 SECURITY FIX: Validate path before writing
    try:
        from sakura_assistant.core.execution.executor import validate_path
    except ImportError:
        return f"⛔ Security: Path validation module not found. File access denied."

    try:
        if not validate_path(path):
             return f"⛔ Access denied: Path validation failed for '{path}'"
    except Exception as e:
        return f"⛔ Security check error: {e}"

    try:
        safe_path = _validate_path(path)
        if "config.py" in os.path.basename(safe_path): return " Protected file."
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f" Written to {safe_path}"
    except Exception as e:
        return f" Write error: {e}"

@tool
def file_open(file_path: str) -> str:
    """
    Open a file or directory.
    
    Open a file or directory.
    
    V17.2 SECURITY FIX: Added path validation to prevent directory traversal.
    """
    # Import validator
    try:
        from sakura_assistant.core.execution.executor import validate_path
    except ImportError:
        # Fallback if import fails - fail safe
        # Fallback if import fails - fail safe
        return f"⛔ Security: Path validation module not found. File access denied."
    
    # Validate path before opening
    try:
        if not validate_path(file_path):
            return f"⛔ Access denied: Path validation failed for '{file_path}'"
    except Exception as e:
        return f"⛔ Access denied: {str(e)}"
    
    try:
        if "~" in file_path: file_path = os.path.expanduser(file_path)
        if not os.path.exists(file_path): return " Not found."
        os.startfile(file_path)
        return f" Opened: {file_path}"
    except Exception as e:
        return f" Failed: {e}"

# --- Utility Tools ---

@tool
def set_timer(minutes: float, label: str = "Timer") -> str:
    """Sets a background timer."""
    import platform
    seconds = int(minutes * 60)
    
    def _timer_thread():
        time.sleep(seconds)
        if platform.system() == "Windows":
            try:
                import winsound
                winsound.Beep(1000, 500)
            except Exception as e:
                import logging
                logging.getLogger("System").warning(f"[System] Windows Beep failed: {e}")
        else:
            print("\a") # Bell sound on Linux

        
    threading.Thread(target=_timer_thread, daemon=True).start()
    return f"Timer set for {minutes} minutes."

@tool
def volume_control(action: str, level: int = 50) -> str:
    """Control system volume (Windows)."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        
        if action == "mute": volume.SetMute(1, None)
        elif action == "unmute": volume.SetMute(0, None)
        elif action == "set": volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Volume {action}ed."
    except Exception as e:
        return f" Volume error (pycaw needed): {e}"

@tool
def get_location() -> str:
    """Get location via IP."""
    import requests
    try:
        data = requests.get("http://ip-api.com/json/", timeout=3).json()
        return f" {data.get('city')}, {data.get('country')}"
    except:
        return " Location unavailable."

# --- Scheduler Tools ---

@tool
def set_reminder(message: str, delay_minutes: float) -> str:
    """Set a reminder."""
    try:
        from ..infrastructure.scheduler import remind_me, start_scheduler
        start_scheduler()
        
        delay_sec = delay_minutes * 60
        def cb(msg): print(f"\n⏰ REMINDER: {msg}\n")
        
        remind_me(message, delay_sec, cb)
        return f" Reminder set for {delay_minutes} mins."
    except Exception as e:
        return f" Error: {e}"
