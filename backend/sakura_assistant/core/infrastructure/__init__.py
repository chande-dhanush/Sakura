"""
Infrastructure and system services.

Exports:
- get_container
- broadcast
- get_rate_limiter, ModelRateLimiter
- TaskScheduler
- VoiceEngine, _run_loop
"""

from .container import get_container
from .broadcaster import broadcast
from .rate_limiter import get_rate_limiter, ModelRateLimiter
from .scheduler import Scheduler
try:
    from .voice import VoiceEngine
except Exception:  # Optional dependency path (audio stack)
    VoiceEngine = None

def get_voice_engine():
    """Factory to get VoiceEngine from container."""
    from .container import get_container
    return get_container().infrastructure.get("voice")

__all__ = [
    "get_container",
    "broadcast",
    "get_rate_limiter",
    "ModelRateLimiter",
    "Scheduler",
    "VoiceEngine",
    "get_voice_engine",
]
