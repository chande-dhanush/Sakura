"""
Sakura V7: World Graph

The SINGLE SOURCE OF TRUTH for the assistant.
This replaces the implicit hidden state lost in multi-agent decomposition.

Core Concepts:
- EntityNode: Things that exist (user, songs, topics, people)
- ActionNode: Things that happened (tool calls, chats)
- Lifecycle: Ephemeral → Candidate → Promoted
- Source: Who created this data (USER_STATED, TOOL_RESULT, LLM_INFERRED)
- Focus Entity: The primary thing an action is "about"

Invariants:
1. user:self is immutable to tools
2. LLM_INFERRED entities never auto-promote
3. Source tracking on every mutation
4. Reference resolution: focus_entity > entities_involved > action
5. External search banned for user references
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple, Union
import json
import os
import threading
import time
import tempfile

# Lazy-loaded numpy (only when embeddings used)
_np = None
def _get_numpy():
    global _np
    if _np is None:
        import numpy as np
        _np = np
    return _np


# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════════

class EntityType(Enum):
    """Types of entities in the world."""
    USER = "user"               # The human user (ONLY ONE)
    PREFERENCE = "preference"   # User preferences
    PERSON = "person"           # External people (friends, celebrities)
    SONG = "song"
    ARTIST = "artist"
    APP = "app"
    TOPIC = "topic"
    QUERY = "query"             # Search queries as entities
    FILE = "file"
    EVENT = "event"
    TASK = "task"
    LOCATION = "location"
    EXTERNAL = "external"       # Generic external entity from tools


class ActionType(Enum):
    """Types of actions."""
    TOOL_CALL = "tool"
    CHAT = "chat"
    CLARIFICATION = "clarification"
    ERROR = "error"
    CORRECTION = "correction"   # Self-repair
    EPISODE = "episode"         # Compressed group of actions


class EntityLifecycle(Enum):
    """Lifecycle stage of an entity."""
    EPHEMERAL = "ephemeral"     # Temporary, not trusted, semantic search ignores
    CANDIDATE = "candidate"     # Referenced multiple times, awaiting promotion
    PROMOTED = "promoted"       # Trusted, searchable, persistent


class EntitySource(Enum):
    """Who/what created this entity."""
    USER_STATED = "user_stated"           # User explicitly said this (highest trust)
    USER_CONFIRMED = "user_confirmed"     # User confirmed a suggestion
    TOOL_RESULT = "tool_result"           # Came from tool execution
    LLM_INFERRED = "llm_inferred"         # LLM filled in (NEVER auto-trust)
    MEMORY_RECALLED = "memory_recalled"   # Retrieved from long-term memory
    SYSTEM = "system"                     # Created by system initialization


class RecencyBucket(Enum):
    """Temporal grouping for entities and actions."""
    NOW = "now"                 # This turn or last turn
    EARLIER = "earlier"         # This session (last ~10 turns)
    LONG_AGO = "long_ago"       # Previous sessions
    FORGOTTEN = "forgotten"     # Beyond recall horizon


class UserIntent(Enum):
    """User's emotional/interaction state (descriptive, not causal)."""
    CURIOUS = "curious"
    FRUSTRATED = "frustrated"
    CASUAL = "casual"
    URGENT = "urgent"
    PLAYFUL = "playful"
    TASK_FOCUSED = "task_focused"


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class EntityNode:
    """
    Represents a thing that exists in the world.
    
    Lifecycle: EPHEMERAL (default) → CANDIDATE → PROMOTED
    Only PROMOTED entities are trusted and searchable.
    """
    id: str                                         # e.g., "entity:song:shape_of_you"
    type: EntityType
    name: str                                       # Human-readable name
    attributes: Dict[str, Any] = field(default_factory=dict)
    
    # Lifecycle management
    lifecycle: EntityLifecycle = EntityLifecycle.EPHEMERAL
    source: EntitySource = EntitySource.LLM_INFERRED
    mutable_by: Set[EntitySource] = field(default_factory=lambda: {
        EntitySource.USER_STATED, 
        EntitySource.USER_CONFIRMED
    })
    
    # Temporal tracking
    created_at: datetime = field(default_factory=datetime.now)
    last_referenced: datetime = field(default_factory=datetime.now)
    reference_count: int = 0
    recency_bucket: RecencyBucket = RecencyBucket.NOW
    
    # Uncertainty
    confidence: float = 0.5                         # 0.0 - 1.0
    not_claims: List[str] = field(default_factory=list)  # Negative constraints
    
    # Latent state (lazy-loaded)
    summary: str = ""
    _embedding_cached: bool = False
    
    def touch(self) -> None:
        """Mark entity as recently referenced."""
        self.last_referenced = datetime.now()
        self.reference_count += 1
        self.recency_bucket = RecencyBucket.NOW
    
    def decay(self, current_time: datetime, session_start: datetime) -> None:
        """Update recency bucket based on time elapsed."""
        age_seconds = (current_time - self.last_referenced).total_seconds()
        
        if age_seconds < 120:  # 2 minutes
            self.recency_bucket = RecencyBucket.NOW
        elif self.last_referenced >= session_start:
            self.recency_bucket = RecencyBucket.EARLIER
        elif age_seconds < 86400:  # 24 hours
            self.recency_bucket = RecencyBucket.LONG_AGO
        else:
            self.recency_bucket = RecencyBucket.FORGOTTEN
    
    def can_be_mutated_by(self, source: EntitySource) -> bool:
        """Check if this source is allowed to update this entity."""
        return source in self.mutable_by
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for persistence."""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "attributes": self.attributes,
            "lifecycle": self.lifecycle.value,
            "source": self.source.value,
            "mutable_by": [s.value for s in self.mutable_by],
            "created_at": self.created_at.isoformat(),
            "last_referenced": self.last_referenced.isoformat(),
            "reference_count": self.reference_count,
            "confidence": self.confidence,
            "not_claims": self.not_claims,
            "summary": self.summary,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntityNode":
        """Deserialize from persistence."""
        return cls(
            id=data["id"],
            type=EntityType(data["type"]),
            name=data["name"],
            attributes=data.get("attributes", {}),
            lifecycle=EntityLifecycle(data.get("lifecycle", "ephemeral")),
            source=EntitySource(data.get("source", "llm_inferred")),
            mutable_by={EntitySource(s) for s in data.get("mutable_by", ["user_stated", "user_confirmed"])},
            created_at=datetime.fromisoformat(data["created_at"]),
            last_referenced=datetime.fromisoformat(data["last_referenced"]),
            reference_count=data.get("reference_count", 0),
            confidence=data.get("confidence", 0.5),
            not_claims=data.get("not_claims", []),
            summary=data.get("summary", ""),
        )


@dataclass
class ActionNode:
    """
    Represents something that happened.
    
    Key field: focus_entity — the primary thing this action is "about".
    Reference resolution prioritizes focus_entity over entities_involved.
    """
    id: str                                         # e.g., "action:t-5"
    turn: int                                       # Conversation turn number
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Action details
    action_type: ActionType = ActionType.CHAT
    tool: Optional[str] = None
    args: Dict[str, Any] = field(default_factory=dict)
    result: Optional[str] = None                    # Truncated result
    success: bool = True
    
    # Focus + Entities (key for reference resolution)
    focus_entity: Optional[str] = None              # Entity ID this action is about
    entities_involved: List[str] = field(default_factory=list)
    
    # Causality (restricted to planner dependencies only)
    depends_on: Optional[str] = None                # Action ID this depends on
    
    # Emotion (descriptive, NOT causal)
    user_intent: UserIntent = UserIntent.CASUAL
    user_satisfaction: Optional[float] = None       # 0.0 - 1.0
    
    # Compression guidance
    significance: float = 0.5                       # 0.0 (trivial) to 1.0 (life event)
    key_facts: List[str] = field(default_factory=list)  # NEVER compressed
    
    # Latent + Temporal
    summary: str = ""
    recency_bucket: RecencyBucket = RecencyBucket.NOW
    session_id: str = ""
    
    _embedding_cached: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for persistence."""
        return {
            "id": self.id,
            "turn": self.turn,
            "timestamp": self.timestamp.isoformat(),
            "action_type": self.action_type.value,
            "tool": self.tool,
            "args": self.args,
            "result": self.result,
            "success": self.success,
            "focus_entity": self.focus_entity,
            "entities_involved": self.entities_involved,
            "depends_on": self.depends_on,
            "user_intent": self.user_intent.value,
            "user_satisfaction": self.user_satisfaction,
            "significance": self.significance,
            "key_facts": self.key_facts,
            "summary": self.summary,
            "session_id": self.session_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionNode":
        """Deserialize from persistence."""
        return cls(
            id=data["id"],
            turn=data["turn"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            action_type=ActionType(data.get("action_type", "chat")),
            tool=data.get("tool"),
            args=data.get("args", {}),
            result=data.get("result"),
            success=data.get("success", True),
            focus_entity=data.get("focus_entity"),
            entities_involved=data.get("entities_involved", []),
            depends_on=data.get("depends_on"),
            user_intent=UserIntent(data.get("user_intent", "casual")),
            user_satisfaction=data.get("user_satisfaction"),
            significance=data.get("significance", 0.5),
            key_facts=data.get("key_facts", []),
            summary=data.get("summary", ""),
            session_id=data.get("session_id", ""),
        )


@dataclass
class ResolutionResult:
    """Result of reference resolution."""
    resolved: Optional[Union[EntityNode, ActionNode]] = None
    confidence: float = 0.0
    alternatives: List[Any] = field(default_factory=list)
    needs_clarification: bool = False
    action: Optional[str] = None                    # "repeat", "modify", etc.
    fallback_response: Optional[str] = None         # Graceful failure message
    ban_external_search: bool = False               # Hard constraint for identity


# ═══════════════════════════════════════════════════════════════════════════════
# WORLD GRAPH
# ═══════════════════════════════════════════════════════════════════════════════

class WorldGraph:
    """
    Persistent world model for the assistant.
    
    This is the SINGLE SOURCE OF TRUTH.
    The LLM is the voice. The graph is the brain.
    
    Authority Order:
    1. Graph identity (user:self) — immutable to tools
    2. Graph entities (promoted) — mutable by approved sources
    3. User memory (FAISS) — supplements graph
    4. Tools — add external entities only
    5. External search — banned for user references
    """
    
    # User identity configuration (loaded from config or set at init)
    USER_NAME = "Dhanush"
    USER_ATTRIBUTES = {
        "age": 22,
        "birthday": "29 October",
        "location": "Bangalore, India",
        "interests": ["AI", "Anime", "Travelling"],
    }
    
    def __init__(self, persist_path: str = None):
        # Core storage
        self.entities: Dict[str, EntityNode] = {}
        self.actions: List[ActionNode] = []
        
        # State
        self.current_turn: int = 0
        self.current_session: str = self._generate_session_id()
        self.session_start: datetime = datetime.now()
        
        # Compression state
        self.last_compression_turn: int = 0
        self.compression_interval: int = 15  # Compress every N turns
        
        # Persistence
        self.persist_path = persist_path
        
        # V7.1: Thread safety lock (protects all mutations)
        self._lock = threading.RLock()
        
        # Initialize identity
        self._initialize_identity()
        
        # Load persisted state if available
        if persist_path and os.path.exists(persist_path):
            self._load_from_disk()
        
        print(f"📊 [WorldGraph] Initialized (session={self.current_session[:8]})")
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        import uuid
        return str(uuid.uuid4())
    
    def _initialize_identity(self) -> None:
        """
        Create the immutable user identity node.
        
        INVARIANT: This node can ONLY be mutated by USER_STATED or USER_CONFIRMED.
        """
        user_entity = EntityNode(
            id="user:self",
            type=EntityType.USER,
            name=self.USER_NAME,
            attributes=self.USER_ATTRIBUTES.copy(),
            lifecycle=EntityLifecycle.PROMOTED,
            source=EntitySource.SYSTEM,
            mutable_by={EntitySource.USER_STATED, EntitySource.USER_CONFIRMED},
            confidence=1.0,
            not_claims=["NOT the actor Dhanush", "NOT a public figure"],
            summary=self._generate_user_summary(),
        )
        self.entities["user:self"] = user_entity
        
        # Preference node
        pref_entity = EntityNode(
            id="pref:communication",
            type=EntityType.PREFERENCE,
            name="Communication Preferences",
            attributes={
                "style": "practical, direct",
                "enjoys": "being roasted",
                "prefers": "minimal responses",
            },
            lifecycle=EntityLifecycle.PROMOTED,
            source=EntitySource.SYSTEM,
            mutable_by={EntitySource.USER_STATED, EntitySource.USER_CONFIRMED},
            confidence=1.0,
            summary="Prefers practical, direct replies. Enjoys being teased.",
        )
        self.entities["pref:communication"] = pref_entity
    
    def _generate_user_summary(self) -> str:
        """Generate natural language summary of user."""
        attrs = self.USER_ATTRIBUTES
        interests = ", ".join(attrs.get("interests", []))
        return f"{self.USER_NAME}, {attrs.get('age')}, from {attrs.get('location')}. Interests: {interests}."
    
    # ═══════════════════════════════════════════════════════════════════════════
    # QUERY METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_user_identity(self) -> EntityNode:
        """
        Return the user identity node.
        
        INVARIANT: This ALWAYS returns a valid node. Never None.
        """
        return self.entities["user:self"]
    
    def is_user_reference(self, text: str) -> Tuple[bool, float]:
        """
        Check if text refers to the user.
        
        Returns (is_user, confidence).
        
        INVARIANT: "me", "myself", "I" → True with confidence=1.0
        """
        text_lower = text.lower().strip()
        
        # Absolute signals (confidence = 1.0)
        if any(phrase in text_lower for phrase in [
            "who am i", "about me", "about myself", "tell me about me",
            "my name", "my age", "my birthday", "my location",
            "what do you know about me", "describe me",
            # V7: Added more patterns
            "what have you stored about me", "what do you remember about me",
            "what's stored about me", "what info do you have on me",
            "what have you learned about me", "my profile", "my interests"
        ]):
            return True, 1.0
        
        # Check user's name
        user = self.get_user_identity()
        if user.name.lower() in text_lower:
            # Could be user or external — check context
            if any(ctx in text_lower for ctx in ["about", "tell me", "who is", "what about"]):
                return True, 0.75  # Likely user
            return False, 0.3  # More likely external
        
        return False, 0.0
    
    def resolve_reference(self, ref: str) -> ResolutionResult:
        """
        Resolve pronouns and references with multi-hypothesis support.
        
        Priority:
        1. "me/myself/I" → user:self (confidence=1.0)
        2. "this/that/it" → focus_entity > entities_involved > action
        3. "again" → repeat last action
        4. Name lookup (fuzzy)
        5. Graceful fallback
        
        INVARIANT: Never returns empty without a fallback_response.
        """
        ref_lower = ref.lower().strip()
        
        # Priority 1: User self-reference (ABSOLUTE)
        if ref_lower in ["me", "myself", "i", "my"]:
            return ResolutionResult(
                resolved=self.get_user_identity(),
                confidence=1.0,
                ban_external_search=True
            )
        
        # Check if this is a user-reference query
        is_user_ref, user_conf = self.is_user_reference(ref)
        if is_user_ref and user_conf > 0.7:
            return ResolutionResult(
                resolved=self.get_user_identity(),
                confidence=user_conf,
                ban_external_search=True
            )
        
        # Priority 2: Demonstrative pronouns → last action's focus
        # Check if "it", "that", "this" appears ANYWHERE in the input (not just exact match)
        words = ref_lower.split()
        has_demonstrative = any(word in ["this", "that", "it"] for word in words)
        
        if has_demonstrative:
            last_action = self.get_last_action()
            if last_action:
                # 2a: Focus entity (highest priority)
                if last_action.focus_entity:
                    entity = self.entities.get(last_action.focus_entity)
                    if entity:
                        return ResolutionResult(
                            resolved=entity,
                            confidence=0.9,
                        )
                
                # 2b: First entity involved
                if last_action.entities_involved:
                    entity = self.entities.get(last_action.entities_involved[0])
                    if entity:
                        return ResolutionResult(
                            resolved=entity,
                            confidence=0.75,
                        )
                
                # 2c: The action itself
                return ResolutionResult(
                    resolved=last_action,
                    confidence=0.5,
                )
        
        # Priority 3: "again" / "repeat" → repeat last action
        if "again" in ref_lower or "repeat" in ref_lower:
            last_action = self.get_last_action()
            if last_action:
                return ResolutionResult(
                    resolved=last_action,
                    confidence=0.95,
                    action="repeat"
                )
        
        # Priority 4: "instead" → same query, different tool
        if "instead" in ref_lower:
            last_action = self.get_last_action()
            if last_action and last_action.args:
                return ResolutionResult(
                    resolved=last_action,
                    confidence=0.85,
                    action="modify_tool"
                )
        
        # Priority 5: Name lookup in promoted entities
        entity = self._lookup_entity_by_name(ref)
        if entity:
            return ResolutionResult(
                resolved=entity,
                confidence=0.7,
            )
        
        # Fallback: No resolution found
        return ResolutionResult(
            resolved=None,
            confidence=0.0,
            fallback_response="I'm not sure what you're referring to. Could you clarify?"
        )
    
    def _lookup_entity_by_name(self, name: str) -> Optional[EntityNode]:
        """Lookup entity by name (case-insensitive, promoted only)."""
        name_lower = name.lower().strip()
        
        for entity in self.entities.values():
            if entity.lifecycle != EntityLifecycle.PROMOTED:
                continue
            if entity.name.lower() == name_lower:
                return entity
        
        return None
    
    def get_last_action(self, tool: str = None) -> Optional[ActionNode]:
        """Get most recent action, optionally filtered by tool."""
        for action in reversed(self.actions):
            if tool is None or action.tool == tool:
                return action
        return None
    
    def get_recent_actions(self, count: int = 5) -> List[ActionNode]:
        """Get N most recent actions."""
        return self.actions[-count:] if self.actions else []
    
    def get_context_for_planner(self, query: str, budget: int = 500) -> str:
        """
        Generate compact context for planner injection.
        
        Includes:
        - Resolved references
        - Recent actions (last 3)
        - Relevant promoted entities
        
        INVARIANT: Always respects token budget.
        """
        parts = []
        
        # 1. Check for resolved reference
        resolution = self.resolve_reference(query)
        if resolution.resolved and resolution.confidence > 0.5:
            if isinstance(resolution.resolved, EntityNode):
                parts.append(f"[RESOLVED] Entity: {resolution.resolved.name} ({resolution.resolved.summary})")
            elif isinstance(resolution.resolved, ActionNode):
                parts.append(f"[RESOLVED] Last action: {resolution.resolved.tool} - {resolution.resolved.summary}")
        
        # 2. Recent actions (summaries)
        recent = self.get_recent_actions(3)
        if recent:
            summaries = [f"T{a.turn}: {a.summary}" for a in recent if a.summary]
            if summaries:
                parts.append(f"[RECENT] {'; '.join(summaries)}")
        
        # 3. Identity reminder (always include)
        user = self.get_user_identity()
        parts.append(f"[USER] {user.summary}")
        
        # Build and truncate
        context = "\n".join(parts)
        if len(context) > budget:
            context = context[:budget-3] + "..."
        
        return context
    
    def get_context_for_responder(self) -> str:
        """Generate context for responder injection."""
        parts = []
        
        # User identity (always)
        user = self.get_user_identity()
        parts.append(f"[USER IDENTITY]\n{user.summary}")
        
        # Preferences
        prefs = self.entities.get("pref:communication")
        if prefs:
            parts.append(f"[PREFERENCES]\n{prefs.summary}")
        
        # Last action context
        last = self.get_last_action()
        if last and last.summary:
            parts.append(f"[LAST ACTION]\n{last.summary}")
        
        return "\n\n".join(parts)
    
    def summarize_recent_activity(self, count: int = 10) -> str:
        """
        V7: Summarize recent user activity for "what have I been into recently" queries.
        
        Looks at last N actions and high-importance entities to create a natural summary.
        
        Returns:
            A natural language summary like "You recently asked about X, Y, and Z."
        """
        if not self.actions:
            return "I don't have any recent activity recorded yet."
        
        # Get recent actions and their topics
        recent = self.actions[-count:]
        topics = []
        
        for action in recent:
            # Extract topic from action summary or args
            if action.focus_entity:
                entity = self.entities.get(action.focus_entity)
                if entity and entity.name not in topics:
                    topics.append(entity.name)
            elif action.summary:
                # Extract key topic from summary
                summary = action.summary.lower()
                if "searched" in summary or "query" in summary:
                    # Try to extract the query topic
                    import re
                    match = re.search(r"(?:searched|query)[:\s]+([^,\.]+)", summary)
                    if match:
                        topic = match.group(1).strip()
                        if topic and topic not in topics:
                            topics.append(topic)
        
        # Also check high-engagement entities
        high_engagement = [
            e for e in self.entities.values() 
            if e.reference_count >= 2 
            and e.lifecycle != EntityLifecycle.EPHEMERAL
            and e.type not in [EntityType.USER, EntityType.PREFERENCE]
            and e.name not in topics
        ]
        for entity in high_engagement[:3]:
            topics.append(entity.name)
        
        if not topics:
            return "You've been asking general questions, nothing I've tracked specifically."
        
        # Format nicely
        if len(topics) == 1:
            return f"You recently asked about {topics[0]}."
        elif len(topics) == 2:
            return f"You recently asked about {topics[0]} and {topics[1]}."
        else:
            return f"You recently asked about {', '.join(topics[:-1])}, and {topics[-1]}."
    
    # ═══════════════════════════════════════════════════════════════════════════
    # UPDATE METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_or_create_entity(
        self,
        type: EntityType,
        name: str,
        source: EntitySource = EntitySource.LLM_INFERRED,
        attributes: Dict[str, Any] = None
    ) -> EntityNode:
        """
        Get existing entity or create new one.
        
        INVARIANT: LLM_INFERRED entities start as EPHEMERAL.
        INVARIANT: USER_STATED entities start as PROMOTED.
        """
        # Generate ID
        entity_id = f"entity:{type.value}:{name.lower().replace(' ', '_')}"
        
        # Check if exists
        if entity_id in self.entities:
            entity = self.entities[entity_id]
            entity.touch()
            return entity
        
        # Determine lifecycle based on source
        if source in [EntitySource.USER_STATED, EntitySource.USER_CONFIRMED, EntitySource.SYSTEM]:
            lifecycle = EntityLifecycle.PROMOTED
            confidence = 0.9
        elif source == EntitySource.TOOL_RESULT:
            lifecycle = EntityLifecycle.EPHEMERAL
            confidence = 0.6
        else:  # LLM_INFERRED
            lifecycle = EntityLifecycle.EPHEMERAL
            confidence = 0.3
        
        # Create entity
        entity = EntityNode(
            id=entity_id,
            type=type,
            name=name,
            attributes=attributes or {},
            lifecycle=lifecycle,
            source=source,
            confidence=confidence,
            summary=f"{name} ({type.value})",
        )
        
        self.entities[entity_id] = entity
        print(f"📊 [WorldGraph] Created entity: {entity_id} (lifecycle={lifecycle.value})")
        
        return entity
    
    def update_entity(
        self,
        entity_id: str,
        updates: Dict[str, Any],
        source: EntitySource
    ) -> bool:
        """
        Update entity attributes.
        
        INVARIANT: Mutation blocked if source not in entity.mutable_by.
        """
        # V9: Explicit identity guard (for auditors)
        if entity_id == "user:self" and source not in {EntitySource.USER_STATED, EntitySource.USER_CONFIRMED}:
            print(f"🛡️ BLOCKED mutation of user:self from source {source.value}")
            return False
        
        entity = self.entities.get(entity_id)
        if not entity:
            print(f"⚠️ [WorldGraph] Entity not found: {entity_id}")
            return False
        
        # Check permission (generic entities)
        if not entity.can_be_mutated_by(source):
            print(f"⛔ [WorldGraph] Blocked mutation of {entity_id} by {source.value}")
            return False
        
        # Apply updates
        for key, value in updates.items():
            entity.attributes[key] = value
        
        entity.last_referenced = datetime.now()
        entity.summary = self._regenerate_entity_summary(entity)
        
        print(f"✅ [WorldGraph] Updated {entity_id} by {source.value}")
        return True
    
    def _regenerate_entity_summary(self, entity: EntityNode) -> str:
        """Regenerate natural language summary for entity."""
        if entity.id == "user:self":
            return self._generate_user_summary()
        
        # Simple summary for other entities
        attrs_str = ", ".join(f"{k}: {v}" for k, v in list(entity.attributes.items())[:3])
        return f"{entity.name} ({entity.type.value}). {attrs_str}" if attrs_str else f"{entity.name} ({entity.type.value})"
    
    def record_action(
        self,
        tool: Optional[str],
        args: Dict[str, Any],
        result: Optional[str],
        success: bool,
        action_type: ActionType = ActionType.TOOL_CALL
    ) -> ActionNode:
        """
        Record a completed action.
        
        Automatically infers focus_entity based on tool + args.
        V7.1: Thread-safe via RLock.
        """
        with self._lock:
            action_id = f"action:t-{self.current_turn}"
            
            action = ActionNode(
                id=action_id,
                turn=self.current_turn,
                action_type=action_type,
                tool=tool,
                args=args,
                result=result[:500] if result else None,  # Truncate
                success=success,
                session_id=self.current_session,
            )
            
            # Infer focus entity
            action.focus_entity = self._infer_focus_entity(tool, args)
            
            # Populate entities_involved
            action.entities_involved = self._extract_entities_from_args(tool, args)
            
            # Generate summary
            action.summary = self._generate_action_summary(action)
            
            # Extract key facts
            action.key_facts = self._extract_key_facts(action)
            
            self.actions.append(action)
            print(f"📊 [WorldGraph] Recorded action: {action_id} (focus={action.focus_entity})")
            
            return action
    
    def _infer_focus_entity(self, tool: Optional[str], args: Dict[str, Any]) -> Optional[str]:
        """
        Infer the primary entity this action is about.
        
        This is critical for reference resolution:
        "Play Shape of You" → "Who sings this?" should resolve to the SONG, not the action.
        """
        if not tool:
            return None
        
        # Spotify → song is focus
        if tool in ["spotify_control", "play_music", "spotify"]:
            song_name = args.get("song_name") or args.get("song") or args.get("track")
            if song_name:
                entity = self.get_or_create_entity(
                    type=EntityType.SONG,
                    name=song_name,
                    source=EntitySource.TOOL_RESULT
                )
                return entity.id
        
        # Search → query is focus
        if tool in ["web_search", "arxiv_search", "search", "wikipedia"]:
            query = args.get("query") or args.get("q") or args.get("search_query")
            if query:
                entity = self.get_or_create_entity(
                    type=EntityType.QUERY,
                    name=query,
                    source=EntitySource.TOOL_RESULT
                )
                return entity.id
        
        # App open → app is focus
        if tool in ["open_app", "launch"]:
            app_name = args.get("app_name") or args.get("app")
            if app_name:
                entity = self.get_or_create_entity(
                    type=EntityType.APP,
                    name=app_name,
                    source=EntitySource.TOOL_RESULT
                )
                return entity.id
        
        return None
    
    def _extract_entities_from_args(self, tool: Optional[str], args: Dict[str, Any]) -> List[str]:
        """Extract all entity IDs mentioned in action args."""
        entities = []
        
        # Common patterns
        for key in ["song_name", "song", "track", "artist"]:
            if key in args and args[key]:
                entity = self.get_or_create_entity(
                    type=EntityType.SONG if "song" in key or "track" in key else EntityType.ARTIST,
                    name=str(args[key]),
                    source=EntitySource.TOOL_RESULT
                )
                entities.append(entity.id)
        
        for key in ["query", "q", "search_query", "topic"]:
            if key in args and args[key]:
                entity = self.get_or_create_entity(
                    type=EntityType.QUERY if "query" in key else EntityType.TOPIC,
                    name=str(args[key]),
                    source=EntitySource.TOOL_RESULT
                )
                entities.append(entity.id)
        
        return entities
    
    def _generate_action_summary(self, action: ActionNode) -> str:
        """Generate natural language summary of action."""
        if action.tool:
            args_str = ", ".join(f"{k}={v}" for k, v in list(action.args.items())[:2])
            status = "✓" if action.success else "✗"
            return f"{action.tool}({args_str}) {status}"
        else:
            return f"Chat turn {action.turn}"
    
    def _extract_key_facts(self, action: ActionNode) -> List[str]:
        """
        Extract key facts that should NEVER be compressed.
        """
        facts = []
        
        if action.tool == "spotify_control":
            song = action.args.get("song_name")
            if song:
                facts.append(f"Played: {song}")
        
        if action.tool in ["reminder_create", "create_reminder"]:
            text = action.args.get("text") or action.args.get("reminder")
            if text:
                facts.append(f"Reminder: {text}")
        
        if action.tool in ["send_message", "send_whatsapp"]:
            to = action.args.get("to") or action.args.get("recipient")
            if to:
                facts.append(f"Sent message to: {to}")
        
        return facts
    
    def advance_turn(self) -> None:
        """
        Advance turn counter and run maintenance.
        
        - Decay recency buckets
        - Promote candidates if criteria met
        - Check if compression needed
        - Garbage collect ephemeral entities
        
        V7.1: Thread-safe via RLock.
        """
        with self._lock:
            self.current_turn += 1
            now = datetime.now()
            
            # Decay all entities
            for entity in list(self.entities.values()):
                entity.decay(now, self.session_start)
            
            # Update action recency
            for action in list(self.actions):
                age = (now - action.timestamp).total_seconds()
                if age < 120:
                    action.recency_bucket = RecencyBucket.NOW
                elif action.session_id == self.current_session:
                    action.recency_bucket = RecencyBucket.EARLIER
                else:
                    action.recency_bucket = RecencyBucket.LONG_AGO
            
            # Check for promotions
            self._check_promotions()
            
            # Compression check
            if self.current_turn - self.last_compression_turn >= self.compression_interval:
                self._run_compression()
            
            # Garbage collection
            self._garbage_collect()
            
            print(f"📊 [WorldGraph] Turn {self.current_turn} (entities={len(self.entities)}, actions={len(self.actions)})")
    
    def _check_promotions(self) -> None:
        """Promote candidate entities that meet criteria."""
        for entity in list(self.entities.values()):
            if entity.lifecycle == EntityLifecycle.EPHEMERAL:
                # Promote if referenced 3+ times
                if entity.reference_count >= 3:
                    entity.lifecycle = EntityLifecycle.CANDIDATE
                    print(f"📊 [WorldGraph] Promoted to CANDIDATE: {entity.id}")
            
            elif entity.lifecycle == EntityLifecycle.CANDIDATE:
                # Promote to PROMOTED if high confidence or user-sourced
                if entity.source in [EntitySource.USER_STATED, EntitySource.USER_CONFIRMED]:
                    entity.lifecycle = EntityLifecycle.PROMOTED
                    print(f"📊 [WorldGraph] Promoted to PROMOTED: {entity.id}")
                elif entity.reference_count >= 5 and entity.confidence >= 0.7:
                    entity.lifecycle = EntityLifecycle.PROMOTED
                    entity.confidence = min(entity.confidence + 0.1, 0.9)
                    print(f"📊 [WorldGraph] Promoted to PROMOTED: {entity.id}")
    
    def _run_compression(self) -> None:
        """
        Compress old actions.
        
        INVARIANT: key_facts are NEVER compressed.
        INVARIANT: High-significance actions retain full detail.
        """
        print(f"💤 [WorldGraph] Running compression (turn {self.current_turn})")
        
        # Find old actions to compress
        old_actions = [
            a for a in self.actions 
            if a.recency_bucket == RecencyBucket.LONG_AGO
            and a.action_type != ActionType.EPISODE
        ]
        
        if len(old_actions) < 5:
            self.last_compression_turn = self.current_turn
            return
        
        # Group by session or significance
        to_compress = [a for a in old_actions if a.significance < 0.7]
        
        if not to_compress:
            self.last_compression_turn = self.current_turn
            return
        
        # Create episode from low-significance actions
        summaries = [a.summary for a in to_compress if a.summary][:5]
        key_facts = []
        for a in to_compress:
            key_facts.extend(a.key_facts)
        
        episode = ActionNode(
            id=f"episode:{to_compress[0].turn}-{to_compress[-1].turn}",
            turn=to_compress[-1].turn,
            timestamp=to_compress[-1].timestamp,
            action_type=ActionType.EPISODE,
            summary=f"[EPISODE] {'; '.join(summaries)}",
            key_facts=key_facts[:10],  # Cap at 10 facts
            significance=0.5,
            recency_bucket=RecencyBucket.LONG_AGO,
            session_id=to_compress[0].session_id,
        )
        
        # Remove compressed actions, add episode
        for a in to_compress:
            self.actions.remove(a)
        self.actions.insert(0, episode)
        
        # Collapse edges for relationship inference
        self._collapse_edges()
        
        self.last_compression_turn = self.current_turn
        print(f"💤 [WorldGraph] Compressed {len(to_compress)} actions into 1 episode")
    
    def _garbage_collect(self) -> None:
        """
        V9.1: Enhanced garbage collection with retention policy.
        
        INVARIANT: user:self and pref:* are NEVER removed.
        
        Steps:
        1. Remove EPHEMERAL entities older than 1 hour with ref_count < 2
        2. Demote stale CANDIDATES (not referenced in 7 days) → delete
        3. Enforce hard caps per EntityType (oldest promoted first)
        """
        now = datetime.now()
        to_remove = []
        
        # V9.1: Hard caps per entity type (prevents bloat)
        ENTITY_CAPS = {
            EntityType.QUERY: 200,
            EntityType.SONG: 150,
            EntityType.APP: 100,
            EntityType.TOPIC: 150,
            EntityType.EXTERNAL: 100,
        }
        STALE_CANDIDATE_DAYS = 7
        
        # --- Step 1: Remove old EPHEMERAL ---
        for entity_id, entity in self.entities.items():
            # Never GC identity or preferences
            if entity_id.startswith("user:") or entity_id.startswith("pref:"):
                continue
            
            # Remove old ephemeral
            if entity.lifecycle == EntityLifecycle.EPHEMERAL:
                age = (now - entity.last_referenced).total_seconds()
                if age > 3600 and entity.reference_count < 2:  # 1 hour
                    to_remove.append(entity_id)
        
        # --- Step 2: Demote stale CANDIDATES ---
        stale_demoted = 0
        for entity_id, entity in list(self.entities.items()):
            if entity_id.startswith("user:") or entity_id.startswith("pref:"):
                continue
            
            if entity.lifecycle == EntityLifecycle.CANDIDATE:
                age_days = (now - entity.last_referenced).total_seconds() / 86400
                if age_days > STALE_CANDIDATE_DAYS:
                    to_remove.append(entity_id)
                    stale_demoted += 1
        
        # --- Step 3: Enforce hard caps per type ---
        caps_deleted = 0
        for etype, cap in ENTITY_CAPS.items():
            # Get all entities of this type (non-protected)
            entities = [
                (eid, e) for eid, e in self.entities.items()
                if e.type == etype and
                   not eid.startswith("user:") and
                   not eid.startswith("pref:") and
                   eid not in to_remove
            ]
            
            if len(entities) > cap:
                # Sort by last_referenced (oldest first)
                entities.sort(key=lambda x: x[1].last_referenced)
                excess = len(entities) - cap
                for eid, _ in entities[:excess]:
                    to_remove.append(eid)
                    caps_deleted += 1
        
        # --- Execute deletions ---
        for entity_id in to_remove:
            if entity_id in self.entities:
                del self.entities[entity_id]
        
        # --- Logging ---
        if to_remove:
            ephemeral_count = len(to_remove) - stale_demoted - caps_deleted
            print(f"🗑️ [WorldGraph] GC: {ephemeral_count} ephemeral, {stale_demoted} stale candidates, {caps_deleted} caps exceeded")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # VALIDATION (Graph Veto)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def validate_plan(self, plan: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate plan before execution.
        
        INVARIANT: Block external search for user-reference queries.
        """
        for step in plan.get("plan", []):
            tool = step.get("tool", "")
            args = step.get("args", {})
            
            # Check for identity violations in search queries
            if tool in ["web_search", "wikipedia", "search"]:
                query = args.get("query", "").lower()
                is_user, conf = self.is_user_reference(query)
                if is_user and conf > 0.5:
                    return False, f"Query '{query}' appears to be about the user. Use graph identity instead of external search."
            
            # Check for negative constraints
            user = self.get_user_identity()
            for not_claim in user.not_claims:
                if not_claim.lower() in str(args).lower():
                    return False, f"Plan violates negative constraint: {not_claim}"
        
        return True, None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PERSISTENCE
    # ═══════════════════════════════════════════════════════════════════════════
    
    def save(self) -> None:
        """
        Save graph to disk using atomic write pattern.
        
        V7.1: Writes to temp file first, then atomically replaces target.
        This prevents data corruption on crash/power loss.
        """
        if not self.persist_path:
            return
        
        with self._lock:
            # V9.1: Filter out EPHEMERAL entities before save (retention policy)
            # Only persist: CANDIDATE, PROMOTED, and always user:*/pref:*
            entities_to_persist = {
                eid: e.to_dict() for eid, e in self.entities.items()
                if e.lifecycle != EntityLifecycle.EPHEMERAL or
                   eid.startswith("user:") or eid.startswith("pref:")
            }
            
            data = {
                "version": "v7",
                "current_turn": self.current_turn,
                "current_session": self.current_session,
                "entities": entities_to_persist,
                "actions": [a.to_dict() for a in self.actions[-100:]],  # Keep last 100
            }
            
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
            
            # Atomic write: write to temp file in same directory, then replace
            dir_path = os.path.dirname(self.persist_path)
            try:
                with tempfile.NamedTemporaryFile(
                    mode='w', 
                    dir=dir_path, 
                    suffix='.tmp',
                    delete=False
                ) as tmp_file:
                    json.dump(data, tmp_file, indent=2)
                    tmp_path = tmp_file.name
                
                # Atomic replace (works on Windows and POSIX)
                os.replace(tmp_path, self.persist_path)
                print(f"💾 [WorldGraph] Saved to {self.persist_path}")
                
            except Exception as e:
                print(f"❌ [WorldGraph] Save failed: {e}")
                # Clean up temp file if it exists
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except:
                        pass
    
    def reset(self) -> bool:
        """
        V7.1: Complete reset of World Graph state.
        Deletes persisted file and re-initializes with fresh identity.
        
        Returns:
            True if reset succeeded, False otherwise
        """
        with self._lock:
            try:
                # 1. Delete persisted file
                if os.path.exists(self.persist_path):
                    os.remove(self.persist_path)
                    print(f"🗑️ [WorldGraph] Deleted {self.persist_path}")
                
                # 2. Clear all in-memory state
                self.entities.clear()
                self.actions.clear()
                self.current_turn = 0
                self.current_session = self._generate_session_id()
                self.session_start = datetime.now()
                self.last_compression_turn = 0
                
                # 3. Re-initialize identity (fresh user:self)
                self._init_identity()
                
                print(f"🔄 [WorldGraph] Reset complete - fresh identity initialized")
                return True
                
            except Exception as e:
                print(f"❌ [WorldGraph] Reset failed: {e}")
                return False
    
    def _load_from_disk(self) -> None:
        """Load graph from disk."""
        try:
            with open(self.persist_path, "r") as f:
                data = json.load(f)
            
            if data.get("version") != "v7":
                print(f"⚠️ [WorldGraph] Version mismatch, starting fresh")
                return
            
            self.current_turn = data.get("current_turn", 0)
            
            # Load entities (but always re-init identity)
            for eid, edata in data.get("entities", {}).items():
                if not eid.startswith("user:") and not eid.startswith("pref:"):
                    self.entities[eid] = EntityNode.from_dict(edata)
            
            # Load actions
            for adata in data.get("actions", []):
                self.actions.append(ActionNode.from_dict(adata))
            
            print(f"📂 [WorldGraph] Loaded {len(self.entities)} entities, {len(self.actions)} actions")
            
        except Exception as e:
            print(f"⚠️ [WorldGraph] Load failed: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════════════════════
    
    def reset_session(self) -> None:
        """Start a new session (preserves entities and actions)."""
        self.current_session = self._generate_session_id()
        self.session_start = datetime.now()
        print(f"📊 [WorldGraph] New session: {self.current_session[:8]}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics for debugging."""
        lifecycle_counts = {}
        for entity in self.entities.values():
            lc = entity.lifecycle.value
            lifecycle_counts[lc] = lifecycle_counts.get(lc, 0) + 1
        
        return {
            "turn": self.current_turn,
            "session": self.current_session[:8],
            "entities": len(self.entities),
            "actions": len(self.actions),
            "lifecycle_breakdown": lifecycle_counts,
            "current_intent": self._current_intent.value if hasattr(self, '_current_intent') else "casual",
        }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 6: EQ LAYER (Emotional Intelligence)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def infer_user_intent(self, user_input: str, history: List[Dict] = None) -> UserIntent:
        """
        Infer user's emotional state from input.
        
        This is DESCRIPTIVE, not causal - we're labeling state, not building edges.
        
        Returns:
            UserIntent enum value
        """
        text = user_input.lower().strip()
        
        # Frustration signals
        frustration_signals = [
            "no ", "not that", "wrong", "i said", "i meant", "that's not",
            "ugh", "again?", "still", "why can't", "doesn't work", "broken",
            "stop", "cancel", "forget it", "never mind"
        ]
        if any(sig in text for sig in frustration_signals):
            self._current_intent = UserIntent.FRUSTRATED
            return UserIntent.FRUSTRATED
        
        # Urgency signals
        urgency_signals = [
            "now", "quick", "hurry", "urgent", "asap", "immediately",
            "right now", "fast", "quickly", "emergency"
        ]
        if any(sig in text for sig in urgency_signals):
            self._current_intent = UserIntent.URGENT
            return UserIntent.URGENT
        
        # Curious signals (questions)
        if text.endswith("?") or text.startswith(("what", "how", "why", "who", "when", "where")):
            self._current_intent = UserIntent.CURIOUS
            return UserIntent.CURIOUS
        
        # Playful signals
        playful_signals = [
            "lol", "haha", ":)", ":p", "xd", "lmao", "jk", "joke",
            "just kidding", "hehe"
        ]
        if any(sig in text for sig in playful_signals):
            self._current_intent = UserIntent.PLAYFUL
            return UserIntent.PLAYFUL
        
        # Task-focused (imperatives without emotion)
        if text.split()[0] in ["play", "open", "search", "find", "get", "show", "set", "turn"]:
            self._current_intent = UserIntent.TASK_FOCUSED
            return UserIntent.TASK_FOCUSED
        
        # Default: casual
        self._current_intent = UserIntent.CASUAL
        return UserIntent.CASUAL
    
    def self_check(self, response: str, user_intent: str = None) -> Tuple[bool, Optional[str]]:
        """
        Validate response against graph truth.
        
        Checks:
        1. Response doesn't contradict user identity
        2. Response doesn't claim hallucinated user facts
        3. Response respects negative constraints
        
        Returns:
            (is_valid, correction_needed) tuple
        """
        import re  # Import at top to avoid UnboundLocalError
        
        user = self.get_user_identity()
        response_lower = response.lower()
        
        # Check 1: Negative constraints
        for constraint in user.not_claims:
            # e.g., "NOT a public figure" -> check for "celebrity", "famous", etc.
            if "public figure" in constraint.lower():
                if any(word in response_lower for word in ["celebrity", "famous", "actor", "public figure"]):
                    return False, f"Response implies user is a public figure, but graph says: {constraint}"
            
            # Actor Dhanush check
            if "actor" in constraint.lower() and "dhanush" in constraint.lower():
                if "actor" in response_lower and "dhanush" in response_lower:
                    return False, f"Response confuses user with the actor. Graph says: {constraint}"
        
        # Check 2: Identity contradictions
        user_name = user.name.lower()
        user_location = user.attributes.get("location", "").lower()
        
        # Check for location contradictions
        if user_location and f"you live in" in response_lower or f"you're from" in response_lower:
            # Extract claimed location
            import re
            match = re.search(r"you (?:live in|'re from|are from) (\w+)", response_lower)
            if match:
                claimed_location = match.group(1)
                if claimed_location not in user_location:
                    return False, f"Response claims user is from '{claimed_location}', but graph says: {user_location}"
        
        # Check 3: Hallucinated preferences (things we don't know)
        # If response claims "your favorite X" but we don't have that in attributes
        favorites_pattern = re.search(r"your (?:favorite|favourite) (\w+) is (\w+)", response_lower)
        if favorites_pattern:
            category = favorites_pattern.group(1)
            claimed_value = favorites_pattern.group(2)
            
            # Check if we actually have this in our attributes
            favorite_key = f"favorite_{category}"
            actual_value = user.attributes.get(favorite_key)
            
            if actual_value is None:
                # We don't know this - could be hallucination
                # Don't hard block, but flag for potential correction
                pass  # Accept for now, but could log warning
            elif claimed_value.lower() != actual_value.lower():
                return False, f"Response claims favorite {category} is '{claimed_value}', but graph says: {actual_value}"
        
        return True, None
    
    def get_intent_adjustment(self) -> str:
        """
        Get response style adjustment based on current user intent.
        
        Returns instruction string for responder.
        """
        intent = getattr(self, '_current_intent', UserIntent.CASUAL)
        
        adjustments = {
            UserIntent.FRUSTRATED: "User seems frustrated. Be extra helpful, acknowledge the issue, and avoid being overly cheerful.",
            UserIntent.URGENT: "User needs help quickly. Be concise and direct, skip pleasantries.",
            UserIntent.CURIOUS: "User is curious and exploring. Feel free to elaborate and provide context.",
            UserIntent.PLAYFUL: "User is in a playful mood. Match their energy, light teasing is okay.",
            UserIntent.TASK_FOCUSED: "User wants to get things done. Be efficient and action-oriented.",
            UserIntent.CASUAL: "",  # No adjustment needed
        }
        return adjustments.get(intent, "")

    def get_current_mood(self) -> str:
        """
        Get current user mood (string representation of intent).
        Used by Responder context.
        """
        intent = getattr(self, '_current_intent', UserIntent.CASUAL)
        return intent.value
        
        return adjustments.get(intent, "")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # EDGE COLLAPSING (For repeated patterns)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _collapse_edges(self) -> None:
        """
        Merge repeated entity references into weighted relationships.
        
        Example: If user played "Song X" 5 times, create a relationship:
            user -> LOVES -> Song X (weight=5)
        
        Called during compression cycle.
        """
        # Count entity interactions by type
        entity_interactions: Dict[str, Dict[str, int]] = {}  # entity_id -> {action_type: count}
        
        for action in self.actions:
            if action.focus_entity:
                entity_id = action.focus_entity
                action_type = action.tool or "chat"
                
                if entity_id not in entity_interactions:
                    entity_interactions[entity_id] = {}
                
                entity_interactions[entity_id][action_type] = \
                    entity_interactions[entity_id].get(action_type, 0) + 1
        
        # Update entity attributes with interaction weights
        for entity_id, interactions in entity_interactions.items():
            entity = self.entities.get(entity_id)
            if not entity:
                continue
            
            total_interactions = sum(interactions.values())
            
            # Set engagement score (used for promotion)
            entity.attributes["engagement_score"] = total_interactions
            
            # Set interaction breakdown
            entity.attributes["interaction_types"] = interactions
            
            # Infer relationship strength
            if total_interactions >= 5:
                entity.attributes["relationship"] = "loved"
            elif total_interactions >= 3:
                entity.attributes["relationship"] = "liked"
            else:
                entity.attributes["relationship"] = "mentioned"
        
        print(f"📊 [WorldGraph] Collapsed edges for {len(entity_interactions)} entities")


# ═══════════════════════════════════════════════════════════════════════════════
# EMBEDDING MANAGER (Phase 2)
# ═══════════════════════════════════════════════════════════════════════════════

class EmbeddingManager:
    """
    Lazy embedding manager for WorldGraph.
    
    Features:
    - Lazy load: Model only loaded on first use
    - Auto-unload: Model unloaded after idle timeout
    - Caching: Embeddings cached to avoid recomputation
    - Time-window filtering: Semantic search respects recency
    
    INVARIANT: Never block main thread with model loading.
    """
    
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    IDLE_TIMEOUT = 300  # 5 minutes
    EMBEDDING_DIM = 384
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._model = None
        self._lock = threading.RLock()
        self._last_used = 0
        self._unload_timer = None
        self._cache: Dict[str, Any] = {}  # text -> embedding
        self._cache_order: List[str] = []
        self._cache_max = 512
        self._initialized = True
    
    def _ensure_loaded(self):
        """Load model lazily (thread-safe)."""
        with self._lock:
            if self._model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    print("🧠 [EmbeddingManager] Loading model...")
                    self._model = SentenceTransformer(self.EMBEDDING_MODEL)
                    print("✅ [EmbeddingManager] Model loaded")
                except Exception as e:
                    print(f"⚠️ [EmbeddingManager] Failed to load: {e}")
                    return None
            
            self._last_used = time.time()
            self._schedule_unload()
            return self._model
    
    def _schedule_unload(self):
        """Schedule model unload after idle timeout."""
        if self._unload_timer:
            self._unload_timer.cancel()
        
        self._unload_timer = threading.Timer(
            self.IDLE_TIMEOUT,
            self._check_and_unload
        )
        self._unload_timer.daemon = True
        self._unload_timer.start()
    
    def _check_and_unload(self):
        """Unload model if idle."""
        with self._lock:
            if self._model is None:
                return
            
            idle_time = time.time() - self._last_used
            if idle_time >= self.IDLE_TIMEOUT:
                print("💤 [EmbeddingManager] Unloading model (idle)")
                del self._model
                self._model = None
                import gc
                gc.collect()
    
    def embed(self, text: str) -> Optional[Any]:
        """
        Get embedding for text (cached).
        
        Returns numpy array or None if model unavailable.
        """
        # Check cache first
        if text in self._cache:
            return self._cache[text]
        
        model = self._ensure_loaded()
        if model is None:
            return None
        
        np = _get_numpy()
        embedding = model.encode([text])[0]
        
        # Cache with LRU eviction
        if len(self._cache_order) >= self._cache_max:
            oldest = self._cache_order.pop(0)
            self._cache.pop(oldest, None)
        
        self._cache[text] = embedding
        self._cache_order.append(text)
        
        return embedding
    
    def similarity(self, emb1: Any, emb2: Any) -> float:
        """Cosine similarity between two embeddings."""
        np = _get_numpy()
        if emb1 is None or emb2 is None:
            return 0.0
        
        dot = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot / (norm1 * norm2))
    
    @property
    def is_loaded(self) -> bool:
        return self._model is not None


# Global embedding manager instance
_embedding_manager: Optional[EmbeddingManager] = None

def get_embedding_manager() -> EmbeddingManager:
    """Get singleton EmbeddingManager instance."""
    global _embedding_manager
    if _embedding_manager is None:
        _embedding_manager = EmbeddingManager()
    return _embedding_manager


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC RECALL EXTENSION
# ═══════════════════════════════════════════════════════════════════════════════

def add_semantic_recall_to_graph():
    """Add semantic_recall method to WorldGraph class."""
    
    def semantic_recall(
        self,
        query: str,
        k: int = 5,
        time_window: Optional[Tuple[RecencyBucket, ...]] = None,
        entity_types: Optional[List[EntityType]] = None,
        min_confidence: float = 0.3
    ) -> List[Tuple[EntityNode, float]]:
        """
        Semantic search over graph entities with time-window filtering.
        
        Args:
            query: Search query
            k: Max results to return
            time_window: Filter to these recency buckets (default: NOW, EARLIER)
            entity_types: Filter to these entity types (default: all)
            min_confidence: Minimum entity confidence
        
        Returns:
            List of (entity, similarity_score) tuples, sorted by score.
        
        INVARIANT: Always respects lifecycle (only CANDIDATE or PROMOTED).
        """
        mgr = get_embedding_manager()
        
        # Default time window: recent entities
        if time_window is None:
            time_window = (RecencyBucket.NOW, RecencyBucket.EARLIER)
        
        # Get query embedding
        query_emb = mgr.embed(query)
        if query_emb is None:
            return []  # Model not available
        
        # Filter and score candidates
        candidates = []
        
        for entity in self.entities.values():
            # Skip ephemeral (untrusted)
            if entity.lifecycle == EntityLifecycle.EPHEMERAL:
                continue
            
            # Skip below confidence threshold
            if entity.confidence < min_confidence:
                continue
            
            # Time window filter
            if entity.recency_bucket not in time_window:
                continue
            
            # Entity type filter
            if entity_types and entity.type not in entity_types:
                continue
            
            # Get embedding for entity (use name + summary)
            entity_text = f"{entity.name} {entity.summary}"
            entity_emb = mgr.embed(entity_text)
            
            if entity_emb is None:
                continue
            
            # Compute similarity
            score = mgr.similarity(query_emb, entity_emb)
            candidates.append((entity, score))
        
        # Sort by similarity (descending) and return top k
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:k]
    
    # Add method to WorldGraph
    WorldGraph.semantic_recall = semantic_recall


# Initialize extension
try:
    add_semantic_recall_to_graph()
except Exception as e:
    print(f"⚠️ [WorldGraph] Failed to add semantic_recall: {e}")
