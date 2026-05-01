"""
Sakura V15.4: Refined Deterministic Context Router
================================================
Single Source of Truth for Context Hygiene.
Refined for SRP (Single Responsibility Principle) and code hygiene.
"""
from typing import List, Dict, Any, Optional, Set
import json
import re
from dataclasses import dataclass
from ...utils.episodic_memory import episodic_memory


@dataclass
class ContextSignals:
    """Internal representation of detected data needs."""
    facts: bool = False
    episodes: bool = False
    temporal: bool = False
    location: bool = False
    likes_dislikes: bool = False


class ContextManager:
    """
    Intelligent Context Injection with Mode-Based Pruning.
    
    Responsibilities:
    1. Signal Detection (What data is needed?)
    2. Data Assembly (How should it be formatted?)
    3. Mode-Based Pruning (What's essential vs nice-to-have?)
    """
    
    def __init__(self, world_graph=None, summary_memory=None):
        """Initialize with optional dependencies."""
        # Cleaned keyword clusters (avoiding overlap)
        self.keywords_map = {
            "facts": ["who am i", "my name", "my age", "job", "work", "profile", "about me", "myself", "tell me about"],
            "episodes": ["remember", "happened", "told you", "said before", "recall", "memory"],
            "temporal": ["today", "yesterday", "last week", "earlier", "recently", "when did"],
            "location": ["where am i", "current location", "weather in", "my city"],
            "likes_dislikes": ["like", "love", "hate", "dislike", "prefer", "favorite"]
        }
        
        # Dependency injection
        if world_graph is not None:
            self.wg = world_graph
        else:
            from ..graph.world_graph import WorldGraph
            from ..graph.identity import get_identity_manager
            self.wg = WorldGraph(identity_manager=get_identity_manager())
        
        self.summary_memory = summary_memory
    
    def _detect_signals(self, text: str) -> ContextSignals:
        """Parse user input to detect deterministic data requirements."""
        text_lower = text.lower()
        signals = ContextSignals()
        
        for category, keywords in self.keywords_map.items():
            if any(k in text_lower for k in keywords):
                setattr(signals, category, True)
        
        # Cross-category inference
        if signals.temporal or "last time" in text_lower:
            signals.episodes = True
            
        return signals

    def _build_identity_block(self, is_compact: bool = False) -> str:
        """Build the user identity string from WorldGraph."""
        me_node = self.wg.get_user_identity()
        if not me_node:
            return ""
            
        name = me_node.name
        attrs = me_node.attributes or {}
        loc = attrs.get("location", "Unknown")
        
        if is_compact:
            bio_short = f", {attrs.get('bio')[:30]}..." if attrs.get("bio") else ""
            return f"[USER] {name}, {loc}{bio_short}"
            
        # Detail view
        age = attrs.get("age", "?")
        bio = attrs.get("bio", "None")
        identity = [f"=== USER IDENTITY ===\nUser: {name}, {age}, {loc}.\nBio: {bio}"]
        
        interests = attrs.get("interests", [])
        if interests:
            identity.append(f"Interests: {', '.join(interests)}")
            
        # Preferences
        prefs = []
        for eid, ent in self.wg.entities.items():
            if eid.startswith("pref:") and ent.summary:
                prefs.append(f"- {ent.summary}")
                if eid == "pref:ui":
                    theme = ent.attributes.get("theme", "dark")
                    prefs.append(f"  (UI Theme: {theme})")
        
        if prefs:
            identity.append("Preferences:\n" + "\n".join(prefs))
        else:
            identity.append("Preferences: None stored.")
            
        return "\n".join(identity)

    def _build_episodic_block(self, user_input: str, signals: ContextSignals, state: "RequestState", force: bool = False) -> str:
        """
        V19: Tiered Memory Read-Path.
        Gates semantic recall structurally instead of unconditionally.
        """
        from ...memory.memory_coordinator import get_memory_coordinator
        coordinator = get_memory_coordinator()
        
        # Detect Tier 1 (Explicit Recall)
        is_explicit = coordinator.is_recall_query(user_input) or signals.episodes or force
        
        mode = state.classification if state else "UNKNOWN"
        has_reference = bool(state and state.reference_context)
        study_mode = bool(state and state.study_mode)
        
        # Gating Logic
        should_recall = False
        max_chars = 1500
        
        if is_explicit:
            # Tier 1: Full recall path allowed
            should_recall = True
            max_chars = 2000
        elif mode == "PLAN" or study_mode:
            # Tier 2: PLAN / complex reasoning or study - light semantic recall
            should_recall = True
            max_chars = 800
        elif mode == "DIRECT" and has_reference:
            # Tier 3: DIRECT with references (e.g. "play that")
            should_recall = True
            max_chars = 500
        else:
            # Tier 4: CHAT / simple turns - no recall by default
            should_recall = False
            
        if not should_recall:
            return ""
        
        # V17/V19: Unified memory search with capped bounds
        result = coordinator.recall(user_input)
        
        if result.has_results():
            return result.to_context_string(max_chars=max_chars)
        
        # Fallback to recent episodes if explicit memory request but no hits
        if signals.episodes:
            recent = episodic_memory.get_recent_episodes(2)
            if recent:
                episode_strs = [f"- [{ep['date']}] {ep['summary']}" for ep in recent]
                return "=== RECENT MEMORIES ===\n" + "\n".join(episode_strs)
            return "=== MEMORIES ===\nNo stored memories found."
            
        return ""

    def _build_action_block(self) -> str:
        """Retrieve recent world actions for context."""
        recent_actions = self.wg.get_recent_actions(3)
        if not recent_actions:
            return ""
            
        action_strs = [f"T{a.turn}: {a.summary}" for a in recent_actions if a.summary]
        if not action_strs:
            return ""
            
        return "=== RECENT ACTIONS ===\n" + "\n".join(action_strs)

    def get_context_for_llm(self, user_input: str, state: "RequestState" = None, mode: str = "CHAT", history: List[Dict] = None) -> Dict[str, str]:
        """
        Main entry point for llm.py. Returns segmented context strings.
        
        Args:
            user_input: Current user message
            state: V19 RequestState representation
            mode: Fallback if state is missing
            history: Optional conversation list
        """
        if state:
            mode = state.classification
            
        signals = self._detect_signals(user_input)
        
        # 1. Assemble Planner Context (Deterministic Pruning)
        # -----------------------------------------------
        if mode == "DIRECT" and not signals.facts:
            # Minimalist identity for direct tools
            planner_dynamic = self._build_identity_block(is_compact=True)
        else:
            # Full context for planning or identity-focused direct queries
            parts = [self._build_identity_block(is_compact=False)]
            
            # Add episodic if relevant to plan or asked (V19 tiered)
            mem = self._build_episodic_block(user_input, signals, state, force=(mode == "CHAT"))
            if mem: parts.append(mem)
            
            # V17.1: Always include recent actions (removed PLAN-only gating)
            act = self._build_action_block()
            if act: parts.append(act)
                
            planner_dynamic = "\n\n".join(parts)

        # 2. Assemble Responder Context
        # -----------------------------------------------
        # The responder prompt uses the WorldGraph detailed responder context 
        # (which includes active constraints)
        responder_graph = self.wg.get_context_for_responder()
        
        # 3. Assemble Memory Summary
        # -----------------------------------------------
        summary = ""
        if self.summary_memory:
            summary = self.summary_memory.get_context_injection()
            
        return {
            "planner_context": planner_dynamic,
            "responder_context": responder_graph,
            "summary_context": summary,
            "intent_adjustment": self.wg.get_intent_adjustment(),
            "current_mood": self.wg.get_current_mood()
        }


# Global Instance
context_manager = ContextManager()


def get_smart_context(user_input: str, history: List[Dict], mode: str = "CHAT") -> Dict[str, str]:
    """Shim for backward compatibility."""
    # V15.4: dynamic_user_context renamed to planner_context in modern API
    # but kept here if llm.py expects old names (llm.py was updated though)
    ctx = context_manager.get_context_for_llm(user_input, mode=mode, history=history)
    return {
        "dynamic_user_context": ctx["planner_context"],
        "graph_context": ctx["responder_context"],
        "short_memory_summary": ctx["summary_context"]
    }


