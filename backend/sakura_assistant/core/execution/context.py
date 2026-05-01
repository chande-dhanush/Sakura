"""
Sakura V18.0: Execution Context
=============================
Immutable context passed through entire execution pipeline.

v2.1: Mode must be explicit everywhere - no implicit inference.
"""

import time
import threading
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List, TYPE_CHECKING
import contextvars

class LLMBudgetExceededError(Exception):
    """Raised when the LLM call limit is exceeded for a request."""
    pass

execution_context_var = contextvars.ContextVar("execution_context", default=None)


def _get_int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    if value < min_value or value > max_value:
        return default
    return value

# V19: Shared cancellation signal   set by server /stop, checked by ReActLoop
_cancellation_event = threading.Event()

def request_cancellation():
    """Signal all running execution loops to stop."""
    _cancellation_event.set()

def clear_cancellation():
    """Reset the cancellation signal (called at start of new request)."""
    _cancellation_event.clear()

def is_cancelled() -> bool:
    """Check if cancellation has been requested."""
    return _cancellation_event.is_set()

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
    
    v2.1: Partial   Success. These are distinct states.
    """
    SUCCESS = "success"     # All steps completed successfully
    PARTIAL = "partial"     # Some steps completed, timeout/budget exceeded
    FAILED = "failed"       # Critical error, no useful work done
    SKIPPED = "skipped"     # CHAT mode, no execution needed
    RATE_LIMITED = "rate_limited" # API quota exceeded


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
                "name": user_entity.name if user_entity else "User",
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
    history: Optional[List[Dict]] = None  # V17.1: Conversation history for Planner
    reference_context: str = ""           # V19-FIX: Resolved reference for Planner
    llm_call_count: int = 0
    max_llm_calls: int = 6  # V18 FIX-08
    
    # Budgets by mode (class constants)
    BUDGET_CHAT_MS: int = _get_int_env("EXEC_BUDGET_CHAT_MS", 1000, 500, 10000)
    BUDGET_ONE_SHOT_MS: int = _get_int_env("EXEC_BUDGET_ONE_SHOT_MS", 2000, 500, 15000)
    BUDGET_ITERATIVE_MS: int = _get_int_env("EXEC_BUDGET_ITERATIVE_MS", 8000, 1000, 60000)
    BUDGET_RESEARCH_MS: int = _get_int_env("EXEC_BUDGET_RESEARCH_MS", 20000, 2000, 120000)
    
    @staticmethod
    def create(
        mode: ExecutionMode,
        request_id: str,
        user_input: str = "",
        snapshot: Optional[GraphSnapshot] = None,
        is_research: bool = False,
        history: Optional[List[Dict]] = None,  # V17.1
        reference_context: str = ""            # V19-FIX
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
        
        ctx = ExecutionContext(
            mode=mode,
            budget_ms=budget,
            start_time=time.time(),
            request_id=request_id,
            snapshot=snapshot,
            user_input=user_input,
            history=history,
            reference_context=reference_context
        )
        ctx.max_llm_calls = _get_int_env("MAX_LLM_CALLS", ctx.max_llm_calls, 3, 20)
        execution_context_var.set(ctx)
        return ctx
    
    def remaining_budget_ms(self) -> int:
        """Get remaining time budget in milliseconds."""
        elapsed = (time.time() - self.start_time) * 1000
        return max(0, self.budget_ms - int(elapsed))
    
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        return (time.time() - self.start_time) * 1000
    
    def is_expired(self) -> bool:
        """Returns True if budget has expired."""
        return self.remaining_budget_ms() == 0

    def record_and_check_llm_call(self) -> bool:
        """Returns True if budget is OK, False if limit exceeded."""
        self.llm_call_count += 1
        if self.llm_call_count > self.max_llm_calls:
            print(f"  [Budget] LLM call limit ({self.max_llm_calls}) exceeded")
            return False
        return True
    
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
    def empty(mode: str = "CHAT") -> "ExecutionResult":
        """Create empty result for CHAT mode (no execution)."""
        return ExecutionResult(
            outputs="",
            tool_messages=[],
            tool_used="None",
            last_result={"mode": mode},
            status=ExecutionStatus.SKIPPED
        )
    
    @staticmethod
    def timeout(outputs: str, tool_messages: List[Any], mode: str = "PLAN") -> "ExecutionResult":
        """Create partial result for timeout."""
        return ExecutionResult(
            outputs=outputs + "\n[Execution time limit reached - partial results]",
            tool_messages=tool_messages,
            tool_used=tool_messages[-1].name if tool_messages else "None",
            last_result={"mode": mode},
            status=ExecutionStatus.PARTIAL
        )
    
    @staticmethod
    def error(message: str, mode: str = "unknown") -> "ExecutionResult":
        """Create failed result for errors."""
        return ExecutionResult(
            outputs=message,
            tool_messages=[],
            tool_used="None",
            last_result={"mode": mode},
            status=ExecutionStatus.FAILED
        )

    @staticmethod
    def cancelled(outputs: str = "", tool_messages: list = None) -> "ExecutionResult":
        """Create result for user-cancelled execution."""
        return ExecutionResult(
            outputs=outputs + "\n[Generation cancelled by user]" if outputs else "[Generation cancelled by user]",
            tool_messages=tool_messages or [],
            tool_used="None",
            last_result=None,
            status=ExecutionStatus.PARTIAL
        )

    @staticmethod
    def rate_limited(outputs: str = "", tool_messages: list = None) -> "ExecutionResult":
        """Create result for rate-limited execution."""
        return ExecutionResult(
            outputs=outputs + "\n[API Rate Limit Reached]" if outputs else "[API Rate Limit Reached]",
            tool_messages=tool_messages or [],
            tool_used="None",
            last_result=None,
            status=ExecutionStatus.RATE_LIMITED
        )
