"""
Sakura V17: Execution Context
=============================
Immutable context passed through entire execution pipeline.

v2.1: Mode must be explicit everywhere - no implicit inference.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..graph.world_graph import WorldGraph


class ExecutionMode(Enum):
    """Explicit execution modes."""
    CHAT = "chat"           # No tools, direct to responder
    ONE_SHOT = "one_shot"   # Single tool, regex extraction, no planner
    ITERATIVE = "iterative" # ReAct loop with planner


class ExecutionStatus(Enum):
    """
    Explicit execution outcome.
    
    v2.1: Partial ≠ Success. These are distinct states.
    """
    SUCCESS = "success"     # All steps completed successfully
    PARTIAL = "partial"     # Some steps completed, timeout/budget exceeded
    FAILED = "failed"       # Critical error, no useful work done
    SKIPPED = "skipped"     # CHAT mode, no execution needed


@dataclass(frozen=True)
class GraphSnapshot:
    """
    Immutable snapshot of graph state for a single request.
    
    v2.1: ReferenceResolver must resolve against this snapshot,
    not the live graph, to prevent race conditions during async execution.
    """
    entities: Dict[str, Any]
    recent_actions: List[Dict[str, Any]]
    focus_entity: Optional[str]
    timestamp: float
    user_identity: Dict[str, Any]
    
    @staticmethod
    def from_graph(graph: "WorldGraph") -> "GraphSnapshot":
        """
        Thread-safe snapshot of graph state.
        
        Takes RLock to ensure consistent read.
        """
        with graph._lock:
            # Copy entities (shallow copy is fine - EntityNode is immutable-ish)
            entities = dict(graph.entities)
            
            # Copy recent actions
            recent_actions = [
                {
                    "tool": a.tool,
                    "args": a.args,
                    "result": a.result,
                    "success": a.success,
                    "timestamp": a.timestamp,
                    "summary": a.summary,
                    "focus_entity": a.focus_entity
                }
                for a in graph.actions[-10:]
            ]
            
            # Get focus entity
            focus_entity = graph._current_focus if hasattr(graph, '_current_focus') else None
            
            # Get user identity
            user_entity = graph.entities.get("user:self")
            user_identity = {
                "name": user_entity.attributes.get("name", "User") if user_entity else "User",
                "location": user_entity.attributes.get("location") if user_entity else None,
                "bio": user_entity.attributes.get("bio") if user_entity else None,
            }
            
            return GraphSnapshot(
                entities=entities,
                recent_actions=recent_actions,
                focus_entity=focus_entity,
                timestamp=time.time(),
                user_identity=user_identity
            )
    
    def get_entity(self, entity_id: str) -> Optional[Any]:
        """Get entity from snapshot."""
        return self.entities.get(entity_id)
    
    def get_last_action(self) -> Optional[Dict[str, Any]]:
        """Get most recent action."""
        return self.recent_actions[-1] if self.recent_actions else None


@dataclass
class ExecutionContext:
    """
    Immutable context passed through entire execution.
    
    v2.1: This is the SINGLE SOURCE OF TRUTH for:
    - Current execution mode
    - Time budget
    - Request identity
    - Graph snapshot for reference resolution
    
    Every method that cares about mode receives this, not individual params.
    """
    mode: ExecutionMode
    budget_ms: int
    start_time: float
    request_id: str
    snapshot: Optional[GraphSnapshot] = None
    user_input: str = ""
    
    # Budgets by mode (class constants)
    BUDGET_CHAT_MS: int = 1000
    BUDGET_ONE_SHOT_MS: int = 2000
    BUDGET_ITERATIVE_MS: int = 8000
    BUDGET_RESEARCH_MS: int = 20000
    
    @staticmethod
    def create(
        mode: ExecutionMode,
        request_id: str,
        user_input: str = "",
        snapshot: Optional[GraphSnapshot] = None,
        is_research: bool = False
    ) -> "ExecutionContext":
        """
        Factory method to create context with appropriate budget.
        """
        if mode == ExecutionMode.CHAT:
            budget = ExecutionContext.BUDGET_CHAT_MS
        elif mode == ExecutionMode.ONE_SHOT:
            budget = ExecutionContext.BUDGET_ONE_SHOT_MS
        elif mode == ExecutionMode.ITERATIVE:
            budget = ExecutionContext.BUDGET_RESEARCH_MS if is_research else ExecutionContext.BUDGET_ITERATIVE_MS
        else:
            budget = ExecutionContext.BUDGET_ITERATIVE_MS
        
        return ExecutionContext(
            mode=mode,
            budget_ms=budget,
            start_time=time.time(),
            request_id=request_id,
            snapshot=snapshot,
            user_input=user_input
        )
    
    def remaining_budget_ms(self) -> int:
        """Get remaining time budget in milliseconds."""
        elapsed = (time.time() - self.start_time) * 1000
        return max(0, self.budget_ms - int(elapsed))
    
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        return (time.time() - self.start_time) * 1000
    
    def is_expired(self) -> bool:
        """Check if time budget is exhausted."""
        return self.remaining_budget_ms() <= 0
    
    def is_one_shot(self) -> bool:
        """Check if this is ONE_SHOT mode (always terminal)."""
        return self.mode == ExecutionMode.ONE_SHOT
    
    def is_iterative(self) -> bool:
        """Check if this is ITERATIVE mode."""
        return self.mode == ExecutionMode.ITERATIVE


@dataclass
class ExecutionResult:
    """
    Result from execution pipeline.
    
    v2.1: Uses ExecutionStatus enum instead of bool.
    """
    outputs: str
    tool_messages: List[Any]  # List[ToolMessage]
    tool_used: str
    last_result: Optional[Dict[str, Any]]
    status: ExecutionStatus
    
    @property
    def succeeded(self) -> bool:
        """Check if execution succeeded (SUCCESS or PARTIAL)."""
        return self.status in (ExecutionStatus.SUCCESS, ExecutionStatus.PARTIAL)
    
    @property
    def is_partial(self) -> bool:
        """Check if execution was partial (timeout/budget)."""
        return self.status == ExecutionStatus.PARTIAL
    
    @property
    def is_failed(self) -> bool:
        """Check if execution failed."""
        return self.status == ExecutionStatus.FAILED
    
    @staticmethod
    def empty() -> "ExecutionResult":
        """Create empty result for CHAT mode (no execution)."""
        return ExecutionResult(
            outputs="",
            tool_messages=[],
            tool_used="None",
            last_result=None,
            status=ExecutionStatus.SKIPPED
        )
    
    @staticmethod
    def timeout(outputs: str, tool_messages: List[Any]) -> "ExecutionResult":
        """Create partial result for timeout."""
        return ExecutionResult(
            outputs=outputs + "\n[Execution time limit reached - partial results]",
            tool_messages=tool_messages,
            tool_used=tool_messages[-1].name if tool_messages else "None",
            last_result=None,
            status=ExecutionStatus.PARTIAL
        )
    
    @staticmethod
    def error(message: str) -> "ExecutionResult":
        """Create failed result for errors."""
        return ExecutionResult(
            outputs=message,
            tool_messages=[],
            tool_used="None",
            last_result=None,
            status=ExecutionStatus.FAILED
        )
