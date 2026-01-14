"""
V11.2 Proactive Personalization - Reflection Engine
"""
import asyncio
import json
from typing import List, Dict, Any
from ..world_graph import get_world_graph, WorldGraph, EntityType, EntitySource

class ReflectionEngine:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ReflectionEngine, cls).__new__(cls)
            cls._instance.last_reflected_index = 0
            cls._instance.wg = get_world_graph()
            cls._instance._llm = None
        return cls._instance

    def _get_llm(self):
        if not self._llm:
            from ..container import get_container
            self._llm = get_container().get_llm_service()
        return self._llm

    async def observe_background(self, history: List[Dict[str, Any]]):
        """
        Fire-and-forget background task to analyze conversation delta.
        """
        # Create background task immediately
        asyncio.create_task(self._analyze_delta(history))

    async def _analyze_delta(self, history: List[Dict[str, Any]]):
        """
        Analyze only the new messages since last reflection.
        """
        current_len = len(history)
        
        # 1. Check for delta
        if current_len <= self.last_reflected_index:
            return # Nothing new
            
        # 2. Slice delta (User + Assistant pairs preferred)
        # We need at least one pair to make sense, or significant user message
        delta = history[self.last_reflected_index:]
        
        # Filter for meaningful content (ignore short acknowledgements)
        meaningful_delta = [
            m for m in delta 
            if m.get('role') in ['user', 'assistant'] and len(str(m.get('content', ''))) > 10
        ]
        
        if not meaningful_delta:
            self.last_reflected_index = current_len
            return

        # 3. Update pointer immediately (to prevent double processing if slow)
        self.last_reflected_index = current_len
        
        print(f"🤔 [Reflection] Analyzing {len(delta)} new messages...")

        # 4. Prepare Prompt
        from ...config import REFLECTION_SYSTEM_PROMPT
        from langchain_core.messages import SystemMessage, HumanMessage
        
        conversation_str = ""
        for msg in delta: # Use raw delta for context
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', '')
            conversation_str += f"{role}: {content}\n"

        messages = [
            SystemMessage(content=REFLECTION_SYSTEM_PROMPT),
            HumanMessage(content=f"Analyze this conversation segment:\n\n{conversation_str}")
        ]

        try:
            llm = self._get_llm()
            # Use small/fast model if possible, but standard is fine
            response = await llm.ainvoke(messages)
            content = response.content.strip()
            
            # Clean Markdown json blocks if present
            if "```json" in content:
                content = content.replace("```json", "").replace("```", "")
            
            data = json.loads(content)
            
            entities = data.get("entities", [])
            for ent in entities:
                eid = ent.get("id")
                if not eid: continue
                
                # Check entity type
                # Simple logic: 'pref:' -> PREFERENCE, 'user:' -> USER
                etype = EntityType.PREFERENCE
                if eid.startswith("user:"): etype = EntityType.USER
                elif ent.get("type") == "preference": etype = EntityType.PREFERENCE
                
                # Update World Graph
                # 1. Get or Create
                node = self.wg.get_or_create_entity(
                    type=etype,
                    name=ent.get("summary", "Unknown Preference"),
                    source=EntitySource.LLM_INFERRED, # Reflection is inferred
                    attributes=ent.get("attributes", {})
                )
                
                # 2. Update Attributes (Merge)
                if ent.get("attributes"):
                    self.wg.update_entity(node.id, ent.get("attributes"), source=EntitySource.LLM_INFERRED)
                    # Force summary update if provided
                    if ent.get("summary"):
                         node.summary = ent["summary"]
                
                print(f"✨ [Reflection] Learned: {eid} -> {ent.get('summary')}")

        except Exception as e:
            print(f"❌ Reflection Error: {e}")
