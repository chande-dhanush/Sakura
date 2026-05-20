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

# Post-Refactor Refinement Engines
from .adaptive_engine import AdaptiveInteractionEngine, FrictionDetector
from .relevance_engine import ContextRelevanceEngine, ContextBudgeter
from .workflow_engine import WorkflowContextEngine, SessionStateClassifier, ToolBiasingRegistry, ImplicitReferenceResolver
from .confidence_engine import ConfidenceEngine
from .attention_manager import AttentionManager
from .failure_handler import TrustAwareFailureHandler
from .telemetry import ReliabilityTelemetry
from .preference_adaptation import PreferenceAdaptationEngine


def _trace_memory_non_action(impact: str, details: Dict[str, Any]) -> None:
    """Record memory restraint without making context assembly depend on tracing."""
    try:
        from ..infrastructure.behavioral_trace import get_behavioral_trace, InfluenceType
        get_behavioral_trace().record(
            InfluenceType.MEMORY,
            "ContextManager",
            impact,
            details,
        )
    except Exception:
        pass


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
        
        # Initialize Sub-Engines
        self.adaptive_engine = AdaptiveInteractionEngine()
        self.friction_detector = FrictionDetector(self.adaptive_engine)
        self.relevance_engine = ContextRelevanceEngine()
        self.workflow_engine = WorkflowContextEngine()
        self.confidence_engine = ConfidenceEngine()
        self.attention_manager = AttentionManager()
        self.failure_handler = TrustAwareFailureHandler()
        self.telemetry = ReliabilityTelemetry()
        self.pref_engine = PreferenceAdaptationEngine()
    
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
            _trace_memory_non_action(
                "Skipped memory recall to keep this turn lightweight",
                {
                    "mode": mode,
                    "explicit_recall": is_explicit,
                    "has_reference": has_reference,
                    "study_mode": study_mode,
                },
            )
            return ""
            
        # V17/V19: Unified memory search with capped bounds
        result = coordinator.recall(user_input)
        
        memories = []
        if result.semantic:
            for line in result.semantic.splitlines():
                if line.strip().startswith("- "):
                    memories.append({"text": line.strip()[2:], "confidence": 0.6})
        for ep in result.episodic:
            memories.append({"text": ep.get("summary", ""), "confidence": 0.8, "timestamp": ep.get("date")})
            
        win_info = self.workflow_engine.get_active_window_info()
        active_app = win_info.get("process", "None")
        active_project = getattr(state, "project_path", "") if state else ""
        
        ranked = self.relevance_engine.rank_memories(memories, active_app, active_project)
        filtered = self.relevance_engine.suppress_memories(ranked, threshold=2.0)
        
        if filtered:
            parts = []
            for item in filtered[:5]:
                parts.append(f"- {item['text']}")
            return "=== RECENT RELEVANT MEMORIES ===\n" + "\n".join(parts)

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
        """
        if state:
            mode = state.classification
            
        # 1. Run Metrics and Friction Tracking
        self.adaptive_engine.record_turn(user_input)
        self.friction_detector.analyze_input(user_input)
        
        # 2. Query Workflow Context
        win_info = self.workflow_engine.get_active_window_info()
        active_app = win_info.get("process", "None")
        session_state = SessionStateClassifier.classify_session(win_info, user_input)
        
        # Learn habits (focus hours and app transitions)
        now_hour = datetime.now().hour
        self.pref_engine.learn_focus_hours(now_hour)
        last_app = getattr(self, "_last_app", None)
        if last_app:
            self.pref_engine.record_app_transition(last_app, active_app)
        self._last_app = active_app
        
        # 3. Resolve Implicit References
        implicit = ImplicitReferenceResolver.resolve_implicit_references(user_input)
        
        # 4. Determine Posture and Focus mode
        posture = self.adaptive_engine.determine_posture(user_input, active_app)
        is_focus = self.attention_manager.is_focus_mode_active(win_info)
        if is_focus and posture in ["NORMAL", "DETAILED", "REFLECTIVE"]:
            posture = "SHORT_ACK"
            
        # 5. Fetch Token Budgets
        budgets = ContextBudgeter.get_budget(mode)
        
        signals = self._detect_signals(user_input)
        
        # Assemble Planner Context
        if mode == "DIRECT" and not signals.facts:
            planner_dynamic = self._build_identity_block(is_compact=True)
        else:
            parts = [self._build_identity_block(is_compact=False)]
            mem = self._build_episodic_block(user_input, signals, state)
            if mem: 
                parts.append(mem[:budgets["memory"]])
            act = self._build_action_block()
            if act: 
                parts.append(act[:budgets["active_context"]])
            planner_dynamic = "\n\n".join(parts)

        # Assemble Responder Context
        responder_graph = self.wg.get_context_for_responder()
        
        # Assemble Memory Summary
        summary = ""
        if self.summary_memory:
            summary = self.summary_memory.get_context_injection()
            
        # Resolve confidence of memory retrieval
        memories_list = []
        if "=== RECENT RELEVANT MEMORIES ===" in planner_dynamic:
            for line in planner_dynamic.splitlines():
                if line.strip().startswith("- "):
                    memories_list.append({"score": 8.0, "text": line})
        conf_data = self.confidence_engine.score_memory_retrieval(user_input, memories_list)
        action_posture = self.confidence_engine.determine_action_posture(conf_data)
        
        # Inject implicit reference results into planner/responder context if found
        if implicit:
            ref_str = "\n=== RESOLVED IMPLICIT CONTEXT ===\n"
            if "file_path" in implicit:
                ref_str += f"Implicit 'file': {implicit['file_path']}\n"
            if "error_context" in implicit:
                ref_str += f"Implicit 'error': {implicit['error_context']}\n"
            planner_dynamic += ref_str
            
        return {
            "planner_context": planner_dynamic,
            "responder_context": responder_graph,
            "summary_context": summary,
            "intent_adjustment": self.wg.get_intent_adjustment(),
            "current_mood": self.wg.get_current_mood(),
            "posture": posture,
            "session_state": session_state,
            "active_app": active_app,
            "is_focus": "true" if is_focus else "false",
            "action_posture": action_posture
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


