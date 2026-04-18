"""
Sakura Request State
====================
Hot-path state container for a single execution pipeline.
Prevents parameter drift and ensures reference context reaches planning.
"""
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class RequestState:
    __slots__ = ["query", "history", "image_data", "study_mode", "reference_context", "classification", "tool_hint", "request_id"]
    
    # Essential Input
    query: str
    history: List[Dict] = field(default_factory=list)
    image_data: Optional[str] = None
    study_mode: bool = False
    
    # State accumulated during pipeline
    reference_context: str = ""    # Found by Graph
    classification: str = "UNKNOWN"
    tool_hint: Optional[str] = None
    
    # System identifiers
    request_id: str = field(default_factory=lambda: f"req_{int(time.time()*1000)}")

    def __post_init__(self):
        # Validation
        if not isinstance(self.query, str):
            raise ValueError(f"RequestState.query must be str, got {type(self.query)}")
        if not isinstance(self.history, list):
            raise ValueError(f"RequestState.history must be list, got {type(self.history)}")
        
        # Valid classifications
        valid_modes = {"DIRECT", "PLAN", "CHAT", "RESEARCH", "UNKNOWN"}
        if self.classification not in valid_modes:
            raise ValueError(f"Invalid classification: {self.classification}")
    
    def copy(self) -> "RequestState":
        """Safe shallow copy for threading if needed."""
        return RequestState(
            query=self.query,
            history=self.history.copy(),
            image_data=self.image_data,
            study_mode=self.study_mode,
            reference_context=self.reference_context,
            classification=self.classification,
            tool_hint=self.tool_hint,
            request_id=self.request_id
        )
