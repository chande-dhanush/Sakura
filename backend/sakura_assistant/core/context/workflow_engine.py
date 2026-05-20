import os
import re
import json
from typing import Dict, Any, List, Optional

class WorkflowContextEngine:
    """
    Workflow Context Engine (Phase C / Step 3)
    ==========================================
    Tracks active application process name, window titles, clipboard, and recent commands.
    """
    
    @staticmethod
    def get_active_window_info() -> Dict[str, Any]:
        """Query foreground window text, process name, and pid on Windows."""
        try:
            import win32gui
            import win32process
            import psutil
            
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return {"title": "None", "process": "None", "pid": 0}
                
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            try:
                proc = psutil.Process(pid)
                process_name = proc.name()
            except Exception:
                process_name = "Unknown"
                
            return {"title": title, "process": process_name, "pid": pid}
        except ImportError:
            # Fallback for non-Windows or if pywin32 is not installed
            return {"title": "Unsupported Platform", "process": "Unknown", "pid": 0}
        except Exception as e:
            return {"title": "Unknown", "process": "Unknown", "pid": 0, "error": str(e)}


class SessionStateClassifier:
    """Classifies user sessions into CODING, WRITING, RESEARCH, MEDIA, GENERAL."""
    
    @staticmethod
    def classify_session(active_window: Dict[str, Any], query: str) -> str:
        proc = active_window.get("process", "").lower()
        title = active_window.get("title", "").lower()
        q = query.lower()
        
        # Coding session triggers
        if "code" in proc or "devenv" in proc or "pycharm" in proc or "idea" in proc or "sublime" in proc:
            return "CODING"
        if any(kw in q for kw in ["code", "run code", "compile", "bug", "exception", "error in", "syntax"]):
            return "CODING"
            
        # Writing session triggers
        if "word" in proc or "notepad" in proc or "writer" in proc or "obsidian" in proc:
            return "WRITING"
        if any(kw in q for kw in ["write", "draft", "summarize", "rewrite", "paragraph", "essay"]):
            return "WRITING"
            
        # Media session triggers
        if "spotify" in proc or "vlc" in proc or "netflix" in proc or "music" in proc:
            return "MEDIA"
        if any(kw in q for kw in ["play", "song", "playlist", "mute", "volume", "pause"]):
            return "MEDIA"
            
        # Research session triggers
        if "chrome" in proc or "firefox" in proc or "msedge" in proc or "brave" in proc:
            return "RESEARCH"
        if any(kw in q for kw in ["search", "find", "lookup", "who is", "what is"]):
            return "RESEARCH"
            
        return "GENERAL"


class ToolBiasingRegistry:
    """Biases the intent router towards specific tools depending on the session state."""
    
    @staticmethod
    def get_tool_bias(session_state: str) -> Dict[str, float]:
        if session_state == "CODING":
            return {
                "execute_code": 1.5,
                "file_read": 1.3,
                "file_write": 1.3,
                "search_web": 1.1
            }
        elif session_state == "RESEARCH":
            return {
                "search_web": 1.6,
                "read_screen": 1.3,
                "clipboard_read": 1.2
            }
        elif session_state == "WRITING":
            return {
                "clipboard_read": 1.4,
                "clipboard_write": 1.3,
                "file_write": 1.2
            }
        elif session_state == "MEDIA":
            return {
                "volume_control": 1.6,
                "open_app": 1.3
            }
        return {}


class ImplicitReferenceResolver:
    """Resolves implicit terms like 'that file' or 'the error' from recent actions."""
    
    @staticmethod
    def resolve_implicit_references(query: str) -> Dict[str, Any]:
        resolved = {}
        q = query.lower()
        
        # 1. Resolve "the error" / "that error"
        if "error" in q or "failed" in q or "exception" in q:
            try:
                from ..database import get_db_connection
                conn = get_db_connection()
                cursor = conn.execute(
                    "SELECT result, tool, success FROM actions WHERE success = 0 ORDER BY timestamp DESC LIMIT 1"
                )
                row = cursor.fetchone()
                if row:
                    resolved["error_context"] = f"Last failed tool: {row['tool']}. Output: {row['result']}"
                else:
                    cursor = conn.execute(
                        "SELECT result, tool FROM actions ORDER BY timestamp DESC LIMIT 1"
                    )
                    row = cursor.fetchone()
                    if row:
                        resolved["error_context"] = f"Recent action: {row['tool']}. Output: {row['result']}"
            except Exception:
                pass

        # 2. Resolve "that file" / "the file" / "it"
        if "file" in q or "it" in q or "read it" in q or "open it" in q:
            # Search clipboard first
            try:
                from ..tools_libs.system import clipboard_read
                clip = clipboard_read()
                if clip and (os.path.exists(clip) or re.search(r'[a-zA-Z]:\\|[a-zA-Z]:/', clip) or "/" in clip or "\\" in clip):
                    resolved["file_path"] = clip
            except Exception:
                pass
                
            if "file_path" not in resolved:
                try:
                    from ..database import get_db_connection
                    conn = get_db_connection()
                    cursor = conn.execute(
                        "SELECT args, tool FROM actions WHERE tool IN ('file_read', 'file_write', 'file_open') ORDER BY timestamp DESC LIMIT 1"
                    )
                    row = cursor.fetchone()
                    if row:
                        args = json.loads(row['args'])
                        path = args.get("path") or args.get("file_path")
                        if path:
                            resolved["file_path"] = path
                except Exception:
                    pass
        
        return resolved
