"""
Sakura V9.1: Context Governor
Circuit-breaker for LLM context budget enforcement.

Enforces hard per-stage token limits BEFORE context construction.
Applies ordered degradation if over budget.
Aborts with explicit error (never silent failure).
"""
import os
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Any
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

# ============================================================================
# BUDGET CONFIGURATION
# ============================================================================

@dataclass
class StageBudget:
    """
    Per-stage token limits (conservative for free tier).
    Char limit = tokens * 4 (approximate).
    """
    ROUTER: int = 1500      # Simple COMPLEX/SIMPLE classification
    PLANNER: int = 4000     # Tool schemas (~2k) + context (~2k)
    VERIFIER: int = 1500    # Binary PASS/FAIL check
    RESPONDER: int = 6000   # Needs most context for response
    REFLECTION: int = 2000  # Post-turn memory extraction
    
    @classmethod
    def get_char_limit(cls, stage: str) -> int:
        """Get character limit for stage (~4 chars per token)."""
        stage_upper = stage.upper()
        token_limit = getattr(cls, stage_upper, 4000)
        return token_limit * 4


# ============================================================================
# EXCEPTIONS
# ============================================================================

class ContextBudgetExceeded(Exception):
    """
    Raised when context cannot be reduced to fit budget.
    Agent should tell user explicitly, not fail silently.
    """
    def __init__(self, stage: str, current_chars: int, limit_chars: int, message: str = None):
        self.stage = stage
        self.current_chars = current_chars
        self.limit_chars = limit_chars
        self.message = message or f"{stage} context ({current_chars:,} chars) exceeds limit ({limit_chars:,}) after degradation"
        super().__init__(self.message)


# ============================================================================
# CONTEXT GOVERNOR
# ============================================================================

class ContextGovernor:
    """
    Proactive context budget enforcement.
    
    Intercepts all LLM calls and applies ordered degradation:
    1. Replace raw file refs with RAG pointers
    2. Summarize large tool outputs
    3. Trim tool history (oldest first)
    4. ABORT if still over budget
    
    Never silently truncates - explicit error for user visibility.
    """
    
    # Dev override: set to True to log-only (no enforcement)
    DEV_LOG_ONLY = os.environ.get("SAKURA_GOVERNOR_LOG_ONLY", "").lower() == "true"
    
    def __init__(self, ingestion_registry=None):
        """
        Args:
            ingestion_registry: FileRegistry instance for RAG-owned file lookup
        """
        self.registry = ingestion_registry
        self._load_registry()
    
    def _load_registry(self):
        """Lazy load registry if not provided."""
        if self.registry is None:
            try:
                from ...utils.file_registry import get_file_registry
                self.registry = get_file_registry()
            except ImportError:
                logger.warning("FileRegistry not available - Governor running without RAG awareness")
    
    # ========================================================================
    # MAIN ENFORCEMENT
    # ========================================================================
    
    def enforce(
        self, 
        messages: List[BaseMessage], 
        stage: str,
        tool_outputs: str = "",
        tool_history: list = None
    ) -> Tuple[List[BaseMessage], str, list]:
        """
        Enforce budget for given stage.
        
        Args:
            messages: LLM messages to send
            stage: One of ROUTER, PLANNER, VERIFIER, RESPONDER
            tool_outputs: Tool execution results string
            tool_history: ReAct loop history list
            
        Returns:
            (reduced_messages, reduced_tool_outputs, reduced_history)
            
        Raises:
            ContextBudgetExceeded if cannot reduce to fit budget
        """
        budget_chars = StageBudget.get_char_limit(stage)
        current_chars = self._estimate_chars(messages, tool_outputs)
        
        # Under budget - pass through
        if current_chars <= budget_chars:
            return messages, tool_outputs, tool_history or []
        
        print(f"⚠️ [Governor] {stage}: {current_chars:,} chars > {budget_chars:,} limit")
        
        # Dev mode: log only, don't enforce
        if self.DEV_LOG_ONLY:
            print(f" [Governor] DEV_LOG_ONLY mode - skipping enforcement")
            return messages, tool_outputs, tool_history or []
        
        # Apply ordered degradation
        tool_outputs = self._degrade_tool_outputs(tool_outputs, budget_chars // 2)
        tool_history = self._degrade_history(tool_history, max_items=3)
        messages = self._rebuild_messages_with_degraded_outputs(messages, tool_outputs)
        
        # Recheck after degradation
        final_chars = self._estimate_chars(messages, tool_outputs)
        
        if final_chars > budget_chars:
            raise ContextBudgetExceeded(
                stage=stage,
                current_chars=final_chars,
                limit_chars=budget_chars
            )
        
        print(f" [Governor] Reduced {stage} to {final_chars:,} chars")
        return messages, tool_outputs, tool_history or []
    
    def enforce_simple(self, text: str, stage: str) -> str:
        """
        Simplified enforcement for single-string contexts (e.g., router).
        
        Returns:
            Degraded text if over budget
            
        Raises:
            ContextBudgetExceeded if cannot reduce
        """
        budget_chars = StageBudget.get_char_limit(stage)
        
        if len(text) <= budget_chars:
            return text
        
        print(f"⚠️ [Governor] {stage}: {len(text):,} chars > {budget_chars:,} limit")
        
        if self.DEV_LOG_ONLY:
            return text
        
        # Simple truncation with notice
        degraded = text[:budget_chars - 100] + f"\n\n[DEGRADED by Governor: {len(text):,} → {budget_chars:,} chars]"
        
        return degraded
    
    # ========================================================================
    # DEGRADATION METHODS (Ordered)
    # ========================================================================
    
    def _degrade_tool_outputs(self, outputs: str, max_chars: int) -> str:
        """
        Step 1: Replace file contents with RAG pointers, then truncate.
        """
        if not outputs:
            return ""
        
        if len(outputs) <= max_chars:
            return outputs
        
        # Check for file paths in output - replace with RAG pointers
        degraded = self._replace_file_refs_with_pointers(outputs)
        
        # If still too large, truncate with explicit notice
        if len(degraded) > max_chars:
            degraded = degraded[:max_chars - 100]
            degraded += f"\n\n[GOVERNOR: Truncated from {len(outputs):,} to {max_chars:,} chars]"
        
        return degraded
    
    def _replace_file_refs_with_pointers(self, text: str) -> str:
        """
        Scan for file paths and replace content with RAG pointers.
        """
        if not self.registry:
            return text
        
        # Look for common file path patterns and check registry
        # This is a heuristic - real implementation would parse tool outputs
        import re
        
        # Match file paths like /path/to/file.md or D:\path\to\file.txt
        path_pattern = r'(?:[A-Za-z]:\\[^\s]+\.[a-zA-Z]+|/[^\s]+\.[a-zA-Z]+)'
        
        def replace_with_pointer(match):
            path = match.group(0)
            entry = self.registry.get_by_source_path(path)
            if entry:
                file_id = entry.get("file_id", "unknown")
                return f"[RAG:{file_id}]"
            return path
        
        return re.sub(path_pattern, replace_with_pointer, text)
    
    def _degrade_history(self, history: list, max_items: int = 3) -> list:
        """
        Step 2: Keep only last N history items.
        """
        if not history:
            return []
        
        if len(history) <= max_items:
            return history
        
        print(f" [Governor] Trimmed history: {len(history)} → {max_items}")
        return history[-max_items:]
    
    def _rebuild_messages_with_degraded_outputs(
        self, 
        messages: List[BaseMessage], 
        degraded_outputs: str
    ) -> List[BaseMessage]:
        """
        Step 3: Rebuild messages with degraded tool outputs.
        Preserves system and user messages.
        """
        # Find the system message with tool outputs and replace
        result = []
        for msg in messages:
            if isinstance(msg, SystemMessage) and "TOOL EXECUTION" in msg.content:
                # This is the tool outputs message - replace content
                new_content = msg.content
                # Find and replace the tool outputs section
                if "=== TOOL EXECUTION LOG ===" in new_content:
                    parts = new_content.split("=== TOOL EXECUTION LOG ===")
                    if len(parts) > 1:
                        new_content = parts[0] + "=== TOOL EXECUTION LOG ===\n" + degraded_outputs
                result.append(SystemMessage(content=new_content))
            else:
                result.append(msg)
        
        return result
    
    # ========================================================================
    # HELPERS
    # ========================================================================
    
    def _estimate_chars(self, messages: List[BaseMessage], tool_outputs: str = "") -> int:
        """Estimate total character count."""
        msg_chars = sum(len(m.content) for m in messages) if messages else 0
        return msg_chars + len(tool_outputs or "")
    
    def get_budget_status(self, stage: str, current_chars: int) -> dict:
        """Get budget status for logging/debugging."""
        limit = StageBudget.get_char_limit(stage)
        return {
            "stage": stage,
            "current_chars": current_chars,
            "limit_chars": limit,
            "usage_pct": round((current_chars / limit) * 100, 1),
            "over_budget": current_chars > limit
        }


# ============================================================================
# SINGLETON
# ============================================================================

_governor = None

def get_context_governor() -> ContextGovernor:
    """Get singleton Context Governor instance."""
    global _governor
    if _governor is None:
        _governor = ContextGovernor()
    return _governor
