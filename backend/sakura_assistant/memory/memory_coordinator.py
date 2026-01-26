"""
Sakura V17: Memory Coordinator
==============================
Single unified interface for memory retrieval across all stores.

Design Principle:
- Don't scatter FAISS/episodic/WorldGraph calls everywhere
- Single entry point for context_manager.py to use
- Respects V15.4 architecture (all memory via ContextManager)
"""
import re
import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class RecallResult:
    """Unified result from memory search."""
    semantic: str = ""          # FAISS vector search results
    episodic: List[Dict] = field(default_factory=list)  # Keyword matches
    entities: List[Dict] = field(default_factory=list)  # WorldGraph entities
    actions: List[Dict] = field(default_factory=list)   # Recent actions
    latency_ms: float = 0.0
    
    def has_results(self) -> bool:
        return bool(self.semantic or self.episodic or self.entities)
    
    def to_context_string(self, max_chars: int = 1500) -> str:
        """Format as context block for responder."""
        parts = []
        chars_used = 0
        
        # Priority 1: Semantic (most relevant)
        if self.semantic:
            semantic_block = f"[PAST CONVERSATIONS]\n{self.semantic}"
            if chars_used + len(semantic_block) <= max_chars:
                parts.append(semantic_block)
                chars_used += len(semantic_block)
        
        # Priority 2: Episodic (explicit memories)
        if self.episodic:
            ep_strs = [f"- [{ep.get('date', '?')}] {ep.get('summary', '')}" 
                       for ep in self.episodic[:3]]
            episodic_block = f"[STORED MEMORIES]\n" + "\n".join(ep_strs)
            if chars_used + len(episodic_block) <= max_chars:
                parts.append(episodic_block)
                chars_used += len(episodic_block)
        
        # Priority 3: Actions (what was done)
        if self.actions:
            action_strs = [f"- T{a.get('turn', '?')}: {a.get('summary', '')}"
                           for a in self.actions[:3]]
            action_block = f"[RECENT ACTIONS]\n" + "\n".join(action_strs)
            if chars_used + len(action_block) <= max_chars:
                parts.append(action_block)
        
        return "\n\n".join(parts) if parts else ""


class MemoryCoordinator:
    """
    Unified memory search across all stores.
    
    Coordinates:
    - FAISS (semantic vector search)
    - EpisodicMemory (keyword-based significant events)
    - WorldGraph (entities, actions, identity)
    
    Usage:
        from sakura_assistant.memory.memory_coordinator import get_memory_coordinator
        result = get_memory_coordinator().recall("which FastAPI package")
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # Lazy-load dependencies to avoid circular imports
        self._faiss_store = None
        self._episodic_memory = None
        self._world_graph = None
        
        print(" [MemoryCoordinator] Initialized")
    
    @property
    def faiss_store(self):
        if self._faiss_store is None:
            try:
                from .faiss_store import get_memory_store
                self._faiss_store = get_memory_store()
            except ImportError:
                logger.warning("FAISS store not available")
        return self._faiss_store
    
    @property
    def episodic_memory(self):
        if self._episodic_memory is None:
            try:
                from ..utils.episodic_memory import episodic_memory
                self._episodic_memory = episodic_memory
            except ImportError:
                logger.warning("Episodic memory not available")
        return self._episodic_memory
    
    @property
    def world_graph(self):
        if self._world_graph is None:
            try:
                from ..core.world_graph import get_world_graph
                self._world_graph = get_world_graph()
            except (ImportError, Exception):
                # WorldGraph might not be initialized yet
                pass
        return self._world_graph
    
    def recall(self, query: str, mode: str = "hybrid", max_chars: int = 1500) -> RecallResult:
        """
        Unified memory search across all stores.
        
        Args:
            query: User query to search for
            mode: "semantic" (FAISS only), "episodic" (keyword only), or "hybrid" (both)
            max_chars: Max characters for semantic results
            
        Returns:
            RecallResult with results from all stores
        """
        start = time.perf_counter()
        result = RecallResult()
        
        try:
            # 1. Semantic search (FAISS)
            if mode in ["semantic", "hybrid"] and self.faiss_store:
                try:
                    result.semantic = self.faiss_store.get_context_for_query(
                        query, max_chars=max_chars
                    )
                except Exception as e:
                    logger.warning(f"FAISS search failed: {e}")
            
            # 2. Episodic search (keyword-based)
            if mode in ["episodic", "hybrid"] and self.episodic_memory:
                try:
                    result.episodic = self.episodic_memory.search_episodes(query)
                except Exception as e:
                    logger.warning(f"Episodic search failed: {e}")
            
            # 3. WorldGraph entities and actions
            if self.world_graph:
                try:
                    # Get recent actions
                    actions = self.world_graph.get_recent_actions(10)
                    result.actions = [
                        {"turn": a.turn, "summary": a.summary, "tool": a.tool}
                        for a in actions if a.summary
                    ]
                except Exception as e:
                    logger.warning(f"WorldGraph search failed: {e}")
            
            result.latency_ms = (time.perf_counter() - start) * 1000
            
            # Log for observability
            logger.info(
                f"[MemoryCoordinator] recall('{query[:30]}...') "
                f"semantic={bool(result.semantic)} "
                f"episodic={len(result.episodic)} "
                f"actions={len(result.actions)} "
                f"latency={result.latency_ms:.1f}ms"
            )
            
        except Exception as e:
            logger.error(f"MemoryCoordinator.recall failed: {e}")
        
        return result
    
    def is_recall_query(self, text: str) -> bool:
        """
        Detect if query requires memory search.
        
        Uses pattern matching to avoid false positives.
        """
        text_lower = text.lower()
        
        # Direct keyword matches (high confidence)
        recall_keywords = [
            "do you remember", "remember when", "remember what",
            "talked about", "talking about", "asked about",
            "mentioned", "discussed", "said before",
            "yesterday", "earlier", "last time", "previously", 
            "what did i", "what was i", "what were we",
            "recall", "recollect"
        ]
        
        if any(kw in text_lower for kw in recall_keywords):
            return True
        
        # Regex patterns (for complex detection)
        patterns = [
            r"what (did|was|were) (i|we)",
            r"which .+ (did|was|were) (i|we)",
            r"which .+ (package|api|library|tool|module)",
            r"(told|said|asked|mentioned)\s+(you|me)\b",
        ]
        
        return any(re.search(p, text_lower) for p in patterns)
    
    def get_memory_health(self) -> Dict[str, Any]:
        """
        V17.1: Return memory system health stats for debugging.
        
        Helps identify:
        - Empty memory stores
        - Large index sizes
        - Potential issues
        """
        stats = {}
        
        try:
            if self.faiss_store:
                stats["faiss"] = {
                    "total_messages": len(self.faiss_store.memory_texts),
                    "in_memory_history": len(self.faiss_store.conversation_history),
                    "system_health": self.faiss_store.memory_stats.get("system_health", "unknown")
                }
            
            if self.episodic_memory:
                stats["episodic"] = {
                    "total_episodes": len(self.episodic_memory.episodes)
                }
            
            if self.world_graph:
                stats["world_graph"] = {
                    "total_entities": len(self.world_graph.entities),
                    "total_actions": len(self.world_graph.actions),
                    "current_turn": self.world_graph.current_turn
                }
        except Exception as e:
            stats["error"] = str(e)
        
        return stats


# Singleton accessor
_coordinator_instance = None

def get_memory_coordinator() -> MemoryCoordinator:
    """Get singleton MemoryCoordinator instance."""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = MemoryCoordinator()
    return _coordinator_instance
