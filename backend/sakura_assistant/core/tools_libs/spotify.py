import os
import time
from typing import Optional
from langchain_core.tools import tool
from .common import log_api_call

# --- Third-party libs ---
try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    spotipy = None

try:
    from AppOpener import open as app_open
except ImportError:
    app_open = None

class ToolStateManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolStateManager, cls).__new__(cls)
            cls._instance.spotify_client = None
            cls._instance._initialized = False
        return cls._instance

    def get_spotify(self):
        if not self.spotify_client:
            self._init_spotify()
        return self.spotify_client

    def _init_spotify(self):
        if not spotipy: return
        try:
            client_id = os.getenv("SPOTIFY_CLIENT_ID")
            client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
            if client_id and client_secret:
                # ENABLE OPEN_BROWSER (Fix for manual copy-paste issue)
                self.spotify_client = spotipy.Spotify(auth_manager=SpotifyOAuth(
                    client_id=client_id,
                    client_secret=client_secret,
                    redirect_uri="http://127.0.0.1:8888/callback",
                    scope="user-read-playback-state user-modify-playback-state user-read-currently-playing",
                    open_browser=True
                ))
                print("✅ Spotify client initialized (Lazy Load).")
        except Exception as e:
            print(f"❌ Spotify init failed: {e}")

state_manager = ToolStateManager()

@tool
def spotify_control(action: str, song_name: Optional[str] = None) -> str:
    """Control Spotify playback. 
    
    Args:
        action: 'play', 'pause', 'next', 'previous', or 'status'
        song_name: Name of song (only for 'play')
    """
    client = state_manager.get_spotify()
    
    # Auto-launch logic (Initial Check)
    if not client:
        # Try to open app first
        if app_open:
            print("🔄 Launching Spotify (Client Init)...")
            try:
                app_open("spotify", match_closest=True, output=False)
                time.sleep(5) # Wait for app to start
                state_manager._init_spotify() # Retry init
                client = state_manager.get_spotify()
            except:
                pass
            
    if not client:
        return "❌ Spotify not configured or unreachable. Please use 'play_youtube' instead."
    
    try:
        action = action.lower()
        if action == "play":
            # Device Selection Logic
            target_device_name = os.getenv("SPOTIFY_DEVICE_NAME", "").lower()
            target_device = None
            
            # 1. Fetch devices
            try:
                devices = client.devices()
                device_list = devices.get('devices', [])
            except:
                return "❌ Spotify API Error: Could not fetch devices."

            # 2. Find matching device
            for d in device_list:
                d_name = d['name'].lower()
                # Priority 1: Exact match on configured name
                if target_device_name and target_device_name in d_name:
                    target_device = d
                    break
                # Priority 2: Already active device (if no specific target set)
                if not target_device_name and d['is_active']:
                    target_device = d
                    break
            
            # Priority 3: First available device (if no target and no active)
            if not target_device and not target_device_name and device_list:
                target_device = device_list[0]

            # 3. If still no device, try launching App
            if not target_device:
                if app_open:
                    print("🔄 No Spotify device found. Launching local app...")
                    try:
                        app_open("spotify", match_closest=True, output=False)
                        
                        # Poll for device (up to 20 seconds)
                        print("⏳ Waiting for Spotify to connect...")
                        for i in range(10):
                            time.sleep(2) # Faster polling
                            try:
                                devices = client.devices()
                                device_list = devices.get('devices', [])
                                for d in device_list:
                                    # Check again for target or any device
                                    d_name = d['name'].lower()
                                    if target_device_name:
                                        if target_device_name in d_name:
                                            target_device = d
                                            break
                                    else:
                                        # Use any device if no target
                                        target_device = d
                                        break
                                if target_device:
                                    print(f"✅ Found device: {target_device['name']}")
                                    break
                            except:
                                pass
                    except Exception as e:
                        print(f"⚠️ App launch failed: {e}")

            if not target_device:
                available = ", ".join([d['name'] for d in device_list]) if device_list else "None"
                return f"❌ No Spotify device found. Available: {available}. Try opening Spotify manually."

            # 4. Activate Device
            if not target_device['is_active']:
                try:
                    print(f"🔄 Activating '{target_device['name']}' ({target_device['id']})...")
                    client.transfer_playback(target_device['id'], force_play=False)
                    time.sleep(1)
                except Exception as e:
                    return f"❌ Failed to activate '{target_device['name']}': {e}"

            # Now proceed with Play
            if song_name:
                results = client.search(q=song_name, limit=1, type="track")
                tracks = results.get("tracks", {}).get("items", [])
                if tracks:
                    client.start_playback(uris=[tracks[0]["uri"]])
                    return f"🎵 Playing '{tracks[0]['name']}'."
                return f"❌ Song '{song_name}' not found."
            else:
                client.start_playback()
                return "▶️ Resumed playback."
        elif action == "pause":
            client.pause_playback()
            return "⏸️ Paused."
        elif action == "next":
            client.next_track()
            return "⏭️ Skipped."
        elif action == "previous":
            client.previous_track()
            return "⏮️ Previous track."
        elif action == "status":
            current = client.current_playback()
            if current and current.get("is_playing"):
                item = current.get("item", {})
                return f"🎵 Now Playing: {item.get('name')} by {', '.join(a['name'] for a in item.get('artists', []))}"
            return "⏸️ Nothing playing."
        return "❌ Unknown action."
    except Exception as e:
        return f"❌ Spotify error: {e}"
