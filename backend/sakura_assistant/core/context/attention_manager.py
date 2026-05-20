import time
from typing import Dict, Any

class AttentionManager:
    """
    Attention Manager (Phase C / Step 5)
    ====================================
    Tracks focus states, fullscreen windows, and active apps to prevent distracting interruptions.
    """
    
    def __init__(self):
        self.last_notification_time = 0.0

    @staticmethod
    def is_focus_mode_active(active_window: Dict[str, Any]) -> bool:
        """
        Determines if the user is in focus mode based on fullscreen state and active process.
        """
        proc = active_window.get("process", "").lower()
        title = active_window.get("title", "").lower()
        
        # 1. Fullscreen check on Windows
        try:
            import win32gui
            import win32api
            import win32con
            
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                
                sw = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                sh = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)
                
                # If window is exactly screen size, it's fullscreen (game, movie, presentation)
                if w >= sw and h >= sh:
                    return True
        except Exception:
            pass

        # 2. Suppress for specific focus-heavy applications
        focus_apps = [
            "zoom.exe", "teams.exe", "discord.exe", 
            "obsidian.exe", "powerpnt.exe", "pubg.exe", 
            "vlc.exe", "netflix.exe"
        ]
        if any(app in proc for app in focus_apps):
            return True
            
        # 3. Suppress for meetings or fullscreen markers in window title
        focus_titles = ["zoom meeting", "google meet", "playing", "fullscreen"]
        if any(ft in title for ft in focus_titles):
            return True
            
        return False

    def check_notification_permission(self) -> bool:
        """Enforces a 30-second cooldown between proactive notifications/interruptions."""
        now = time.time()
        if now - self.last_notification_time < 30.0:
            return False
        self.last_notification_time = now
        return True
