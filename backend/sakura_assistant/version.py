# sakura_assistant/version.py
__version__ = "19.5.0"

def get_version_string() -> str:
    return f"Sakura V{__version__.rsplit('.', 1)[0]}"  # Returns "Sakura V19.0"
