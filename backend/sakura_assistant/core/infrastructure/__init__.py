"""
Infrastructure and system services.

Exports:
- get_container
- broadcast
- get_rate_limiter, GlobalRateLimiter
- TaskScheduler
- VoiceEngine, _run_loop
"""

from .container import get_container
from .broadcaster import broadcast
from .rate_limiter import get_rate_limiter, GlobalRateLimiter
from .scheduler import Scheduler
from .voice import VoiceEngine

def get_voice_engine() -> VoiceEngine:
    """Factory to get VoiceEngine from container."""
    from .container import get_container
    return get_container().infrastructure.get("voice")

__all__ = [
    "get_container",
    "broadcast",
    "get_rate_limiter",
    "GlobalRateLimiter",
    "Scheduler",
    "VoiceEngine",
    "get_voice_engine",
]
