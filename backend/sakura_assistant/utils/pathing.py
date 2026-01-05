import os
import sys

def normalize_path(path: str) -> str:
    """
    Normalizes a file path to be absolute and OS-compliant.
    - Expands ~ to user home directory.
    - Converts backslashes/forward slashes to OS default.
    - Resolves relative paths against the current working directory.
    """
    if not path:
        return ""
        
    # Expand user home (e.g. ~/Documents -> C:/Users/Name/Documents)
    path = os.path.expanduser(path)
    
    # Expand environment variables (e.g. %APPDATA%)
    path = os.path.expandvars(path)
    
    # Make absolute
    path = os.path.abspath(path)
    
    # Normalize slashes
    path = os.path.normpath(path)
    
    return path

def get_project_root() -> str:
    """
    Returns the root directory of the project.
    If running as a PyInstaller frozen app, returns AppData/SakuraV10 (persistence).
    If running from source, returns the project root.
    """
    if getattr(sys, 'frozen', False):
        # FROZEN (Compiled .exe) -> Use %APPDATA%/SakuraV10
        if sys.platform == "win32":
            appdata = os.getenv("APPDATA")
            data_root = os.path.join(appdata, "SakuraV10")
        else:
            # Fallback for Linux/Mac (not main target)
            data_root = os.path.expanduser("~/.sakura_v10")
            
        # Ensure it exists
        if not os.path.exists(data_root):
            try:
                os.makedirs(data_root)
            except OSError:
                pass # Fallback to temp if write failed
        
        return data_root
        
    # SOURCE (Dev mode) -> Use actual project root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(current_dir))

def get_bundled_path(rel_path: str) -> str:
    """
    Get path to a bundled resource (works in Dev and Frozen).
    
    Args:
        rel_path: Relative path from project root (e.g. "data/bookmarks.json")
    """
    if getattr(sys, 'frozen', False):
        # FROZEN: Use _MEIPASS
        base_path = sys._MEIPASS
    else:
        # DEV: Use source root
        base_path = get_project_root()
        
    return os.path.join(base_path, rel_path)
