from datetime import datetime
from enum import Enum
import threading
from typing import Any, Dict, List


class InfluenceType(Enum):
    MEMORY = "memory"
    MOOD = "mood"
    PLANNING = "planning"
    PROACTIVITY = "proactivity"
    RESTRAINT = "restraint"
    ROUTING = "routing"
    VOICE = "voice"


class BehavioralInfluence:
    def __init__(
        self,
        type: InfluenceType,
        source: str,
        impact: str,
        details: Dict[str, Any] | None = None,
    ):
        self.timestamp = datetime.now().isoformat()
        self.type = type.value
        self.source = source
        self.impact = impact
        self.details = details or {}


class BehavioralTrace:
    """
    Human-readable behavioral inspector.

    This is intentionally about why Sakura behaved a certain way: memory,
    mood, planning, routing, and initiative. It is not token telemetry.
    """

    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._traces = []
                cls._instance._max_traces = 50
            return cls._instance

    def record(
        self,
        type: InfluenceType,
        source: str,
        impact: str,
        details: Dict[str, Any] | None = None,
    ):
        """Record a cognitive influence event."""
        with self._lock:
            trace = BehavioralInfluence(type, source, impact, details)
            self._traces.append(trace)

            if len(self._traces) > self._max_traces:
                self._traces.pop(0)

            print(f" [Behavior] {type.value.upper()}: {impact} (from {source})")

    def get_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent traces."""
        with self._lock:
            return [vars(t) for t in self._traces[-limit:]]

    def clear(self):
        """Clear all traces."""
        with self._lock:
            self._traces = []


def get_behavioral_trace() -> BehavioralTrace:
    """Get the global BehavioralTrace instance."""
    return BehavioralTrace()
