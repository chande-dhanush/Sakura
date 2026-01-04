"""
Sakura V5.1: AgentState - Pipeline State Tracking & Rate Limit Enforcement

V5.1 Budget Model:
- SOFT_LIMIT = 6: Triggers warning, prevents non-essential calls
- HARD_LIMIT = 8: Absolute kill switch, raises exception

Per-Phase Allocation (Core Pipeline):
- routing:    1 call
- planning:   1 call  
- verifying:  1 call
- retrying:   1 call (optional, retry planner)
- responding: 1 call
- Total core: 5 calls (leaves headroom for edge cases)

Non-Core Calls (must be explicitly logged):
- summarizing: Optional, disabled in V5.1
- memory_judger: Out-of-budget, runs async post-pipeline
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict


class RateLimitExceeded(Exception):
    """Raised when LLM call HARD limit is exceeded."""
    pass


class SoftLimitWarning(Exception):
    """Raised when LLM call SOFT limit is exceeded but operation continues."""
    pass


# V5.1: Budget Constants
SOFT_LIMIT = 6   # Warning threshold - non-essential calls blocked
HARD_LIMIT = 8   # Absolute kill switch

# V5.1: Valid phases for core pipeline (tracked in budget)
CORE_PHASES = {"routing", "planning", "verifying", "retrying", "responding"}

# V5.1: Non-core phases (must be explicitly out-of-budget or counted)
NON_CORE_PHASES = {"summarizing", "memory_judging", "reflecting"}


@dataclass
class AgentState:
    """
    V5.1 State tracker for self-correcting pipeline.
    
    Budget Model:
    - soft_limit: 6 (warning, blocks non-essential)
    - hard_limit: 8 (kill switch)
    
    All LLM calls MUST go through record_llm_call().
    Hidden calls are a correctness violation.
    """
    retry_count: int = 0
    llm_call_count: int = 0
    soft_limit: int = SOFT_LIMIT
    hard_limit: int = HARD_LIMIT
    current_intent: str = "unknown"  # SIMPLE / COMPLEX
    intent_mode: str = "action"  # V5.1: reasoning / data_then_reason / action
    tool_execution_status: str = "none"  # none / success / partial / failed
    phase: str = "idle"
    verifier_verdicts: List[str] = field(default_factory=list)
    hindsight: Optional[str] = None
    
    # V5.1: Per-call tracking for audit
    call_log: List[Dict[str, str]] = field(default_factory=list)
    
    def can_call_llm(self, essential: bool = True) -> bool:
        """
        Check if we have remaining LLM call budget.
        
        Args:
            essential: If False, check against soft_limit instead of hard_limit
        """
        if essential:
            return self.llm_call_count < self.hard_limit
        else:
            return self.llm_call_count < self.soft_limit
    
    def remaining_calls(self, use_soft: bool = False) -> int:
        """Get remaining LLM call budget."""
        limit = self.soft_limit if use_soft else self.hard_limit
        return max(0, limit - self.llm_call_count)
    
    def is_over_soft_limit(self) -> bool:
        """Check if we've exceeded soft limit."""
        return self.llm_call_count >= self.soft_limit
    
    def record_llm_call(self, phase: str, essential: bool = True) -> None:
        """
        Record an LLM call. Raises RateLimitExceeded if hard limit hit.
        
        MUST be called BEFORE making the actual LLM call.
        
        Args:
            phase: Pipeline phase (routing/planning/verifying/retrying/responding)
            essential: If True, allowed up to hard_limit. If False, blocked at soft_limit.
        
        Raises:
            RateLimitExceeded: Hard limit exceeded (8 calls)
            SoftLimitWarning: Soft limit exceeded for non-essential call
        """
        # Validate phase is known
        all_phases = CORE_PHASES | NON_CORE_PHASES | {"idle"}
        if phase not in all_phases:
            print(f"⚠️ [AgentState] Unknown phase '{phase}' - treating as core")
        
        # Check hard limit
        if self.llm_call_count >= self.hard_limit:
            raise RateLimitExceeded(
                f"🛑 HARD LIMIT ({self.hard_limit}) exceeded at phase '{phase}'. "
                f"Call log: {[c['phase'] for c in self.call_log]}"
            )
        
        # Check soft limit for non-essential calls
        if not essential and self.llm_call_count >= self.soft_limit:
            raise SoftLimitWarning(
                f"⚠️ SOFT LIMIT ({self.soft_limit}) exceeded - blocking non-essential '{phase}' call"
            )
        
        # Log warning if over soft limit but essential
        if self.llm_call_count >= self.soft_limit:
            print(f"⚠️ [AgentState] Over soft limit ({self.soft_limit}), essential call #{self.llm_call_count + 1} at '{phase}'")
        
        # Record call
        self.llm_call_count += 1
        self.phase = phase
        self.call_log.append({
            "phase": phase,
            "call_number": self.llm_call_count,
            "essential": essential
        })
        
        print(f"📊 [LLM Budget] Call #{self.llm_call_count}/{self.hard_limit} ({phase}) | Soft: {self.soft_limit}")
    
    def log_out_of_budget_call(self, phase: str, model: str) -> None:
        """
        Log a non-core LLM call that runs outside the budget.
        
        Use for: memory_judger, reflection engine, async summarization
        These calls are NOT counted but MUST be logged for transparency.
        """
        print(f"📊 [OUT-OF-BUDGET] {phase} ({model}) - not counted in pipeline budget")
        self.call_log.append({
            "phase": phase,
            "call_number": "OUT_OF_BUDGET",
            "essential": False,
            "model": model
        })
    
    def record_tool_result(self, success: bool, partial: bool = False) -> None:
        """Record tool execution outcome."""
        if success and not partial:
            self.tool_execution_status = "success"
        elif partial:
            self.tool_execution_status = "partial"
        else:
            self.tool_execution_status = "failed"
    
    def set_hindsight(self, reason: str) -> None:
        """Set failure hindsight for retry planner."""
        self.hindsight = reason
        self.retry_count += 1
    
    def reset(self) -> None:
        """Clean reset between user turns."""
        self.retry_count = 0
        self.llm_call_count = 0
        self.current_intent = "unknown"
        self.intent_mode = "action"  # V5.1: Reset to default
        self.tool_execution_status = "none"
        self.phase = "idle"
        self.verifier_verdicts.clear()
        self.hindsight = None
        self.call_log.clear()
    
    def to_metadata(self) -> dict:
        """Export state as response metadata."""
        return {
            "llm_calls": self.llm_call_count,
            "soft_limit": self.soft_limit,
            "hard_limit": self.hard_limit,
            "intent_mode": self.intent_mode,  # V5.1
            "retries": self.retry_count,
            "phase": self.phase,
            "tool_status": self.tool_execution_status,
            "call_log": [c["phase"] for c in self.call_log]
        }
