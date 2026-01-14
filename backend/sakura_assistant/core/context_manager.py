from typing import List, Dict, Any
import json
from ..utils.episodic_memory import episodic_memory
from ..core.world_graph import WorldGraph

class ContextManager:
    """
    Intelligent Context Injection.
    Decides WHAT to look up based on user input, instead of dumping everything.
    """
    def __init__(self):
        self.keywords_map = {
            "likes": ["like", "love", "enjoy", "prefer", "favorite", "recommend", "suggest", "anime", "movie", "book"],
            "dislikes": ["hate", "dislike", "avoid", "bad", "worst"],
            "facts": ["who am i", "my name", "my age", "where do i", "what do i do", "job", "work"],
            "episodes": ["remember", "happened", "last time", "when i", "told you", "said before", "recall", "memory", "know about me"]
        }
        # V10.7: Persistent WorldGraph instance (Singleton pattern)
        # Avoids reloading JSON on every request
        self.wg = WorldGraph()

    def _detect_intent(self, text: str) -> List[str]:
        text = text.lower()
        intents = []
        for category, keywords in self.keywords_map.items():
            if any(k in text for k in keywords):
                intents.append(category)
        return intents

    def get_dynamic_context(self, user_input: str) -> str:
        """
        Builds a context string containing ONLY relevant info.
        """
        context_parts = []
        wg = self.wg
        
        # 1. Inject World Graph Identity (Deterministic)
        identity_str = "=== USER IDENTITY ===\n"
        
        # Core Identity
        # V10.7: Use proper WorldGraph API
        me_node = wg.get_user_identity()
        if me_node:
            name = me_node.name
            attrs = me_node.attributes or {}
            loc = attrs.get("location", "Unknown")
            age = attrs.get("age", "?")
            identity_str += f"User: {name}, {age}, {loc}.\n"
            
            # Interests (Likes)
            interests = attrs.get("interests", [])
            if interests:
                identity_str += f"Interests: {', '.join(interests)}\n"
        
        # Preferences (All pref:* entities)
        identity_str += "Preferences:\n"
        has_prefs = False
        for eid, ent in wg.entities.items():
            if eid.startswith("pref:"):
                has_prefs = True
                # EntityNode uses attributes, not .get()
                summary = ent.summary
                if summary:
                    identity_str += f"- {summary}\n"
                # Also verify attributes specifically for high-value prefs
                if eid == "pref:ui":
                     theme = ent.attributes.get("theme", "dark")
                     identity_str += f"- UI Theme: {theme}\n"
        
        if not has_prefs:
             identity_str += "- No specific output preferences.\n"

        context_parts.append(identity_str)

        # 2. Detect what else is needed
        intents = self._detect_intent(user_input)
        
        # 3. Fetch specific data
        # Note: Likes/Dislikes now come from World Graph 'interests' or specific nodes
        # If specific 'likes' intent is strong, we might search map/nodes more deeply later
        pass # World Graph handles core identity now.
        if "episodes" in intents:
            # Search episodic memory using the user input as query
            hits = episodic_memory.search_episodes(user_input)
            if hits:
                episode_strs = [f"- [{ep['date']}] {ep['summary']}" for ep in hits]
                context_parts.append(f"=== RELEVANT MEMORIES ===\n" + "\n".join(episode_strs))
            else:
                # If they asked "what do you remember", but search failed, maybe show recent?
                recent = episodic_memory.get_recent_episodes(2)
                if recent:
                     episode_strs = [f"- [{ep['date']}] {ep['summary']}" for ep in recent]
                     context_parts.append(f"=== RECENT MEMORIES ===\n" + "\n".join(episode_strs))

        return "\n\n".join(context_parts)

# Global Instance
context_manager = ContextManager()

def get_smart_context(user_input: str, history: List[Dict]) -> Dict[str, str]:
    """
    Returns a dictionary of context metadata for the LLM.
    Combines User Dynamic Context + System State.
    """
    # 1. User Context (Likes, Memories, etc.)
    user_ctx = context_manager.get_dynamic_context(user_input)

    # 2. System Metadata (Last Tool, Routines)
    import re
    last_tool = "None"
    for msg in reversed(history[-5:]): 
        content = msg.get('content', '')
        # Check for our strict debug pattern
        match = re.search(r"\[DEBUG\] Calling (\w+)", content)
        if match:
            last_tool = match.group(1)
            break
            
    return {
        "dynamic_user_context": user_ctx,
        "last_tool_used": last_tool,
        "short_memory_summary": "Active" # Placeholder for future summary
    }
