"""
Sakura V14: Unified Reflection Engine
======================================
Background memory processor that extracts:
- Entities (preferences, topics)
- Constraints (physical, temporal, resource limitations)
- Retirements (resolved constraints)

Runs asynchronously after each turn to avoid blocking response.
"""
import asyncio
import json
import re
from typing import List, Dict, Any, Optional
from ..world_graph import get_world_graph, WorldGraph, EntityType, EntitySource, EntityLifecycle


class ReflectionEngine:
    """
    V14 Unified Reflection Engine.
    
    Features:
    - Entity extraction (V11 original)
    - Constraint detection (V14 new)
    - Retirement handling (V14 new)
    - Robust JSON parsing with fallback (Gemini Red Team requirement)
    """
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
            self._llm = get_container().get_router_llm()  # Use fast 8B model
        return self._llm

    async def observe_background(self, history: List[Dict[str, Any]]):
        """
        Fire-and-forget background task to analyze conversation delta.
        """
        asyncio.create_task(self._analyze_delta(history))

    async def _analyze_delta(self, history: List[Dict[str, Any]]):
        """
        V14: Unified analysis for entities, constraints, and retirements.
        """
        current_len = len(history)
        
        # 1. Check for delta
        if current_len <= self.last_reflected_index:
            return
            
        # 2. Slice delta
        delta = history[self.last_reflected_index:]
        
        # V14.1 DEBOUNCE: Skip reflection for trivial messages to save RPM
        # Get latest user message
        user_messages = [m for m in delta if m.get('role') == 'user']
        if user_messages:
            latest_user = str(user_messages[-1].get('content', ''))
            # Skip if user message is too short (saves Groq RPM)
            if len(latest_user) < 15:
                self.last_reflected_index = current_len
                print(f"💨 [Reflection] Skipping short message ({len(latest_user)} chars)")
                return
        
        # Filter for meaningful content
        meaningful_delta = [
            m for m in delta 
            if m.get('role') in ['user', 'assistant'] and len(str(m.get('content', ''))) > 15
        ]
        
        if not meaningful_delta:
            self.last_reflected_index = current_len
            return

        # 3. Update pointer immediately (prevent double processing)
        self.last_reflected_index = current_len
        
        print(f"🤔 [Reflection] Analyzing {len(delta)} new messages...")

        # 4. Prepare Prompt
        from ...config import REFLECTION_SYSTEM_PROMPT
        from langchain_core.messages import SystemMessage, HumanMessage
        
        conversation_str = ""
        for msg in delta:
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', '')
            conversation_str += f"{role}: {content}\n"

        messages = [
            SystemMessage(content=REFLECTION_SYSTEM_PROMPT),
            HumanMessage(content=f"Analyze this conversation segment:\n\n{conversation_str}")
        ]

        try:
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            content = response.content.strip()
            
            # V14: Robust JSON parsing (Red Team requirement)
            data = self._safe_parse_json(content)
            if not data:
                print("⚠️ [Reflection] JSON parse failed, skipping")
                return
            
            # Process entities
            self._process_entities(data.get("entities", []))
            
            # V14: Process constraints
            self._process_constraints(data.get("constraints", []))
            
            # V14: Process retirements
            self._process_retirements(data.get("retirements", []))
            
            # Save World Graph
            self.wg.save()

        except Exception as e:
            # Red Team requirement: Never crash on reflection failure
            print(f"❌ [Reflection] Error (non-fatal): {e}")

    def _safe_parse_json(self, content: str) -> Optional[Dict]:
        """
        Robust JSON parsing with multiple fallback strategies.
        Handles: markdown blocks, trailing commas, single quotes.
        """
        # Strategy 1: Clean markdown blocks
        if "```json" in content:
            content = content.replace("```json", "").replace("```", "")
        elif "```" in content:
            content = re.sub(r'```\w*\n?', '', content)
        
        content = content.strip()
        
        # Strategy 2: Direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Strategy 3: Fix trailing commas
        try:
            # Remove trailing commas before ] or }
            fixed = re.sub(r',\s*([}\]])', r'\1', content)
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        
        # Strategy 4: Extract JSON object with regex
        try:
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                return json.loads(match.group())
        except json.JSONDecodeError:
            pass
        
        # Strategy 5: Return empty structure (graceful degradation)
        print(f"⚠️ [Reflection] All JSON parse strategies failed for: {content[:100]}...")
        return None

    def _process_entities(self, entities: List[Dict]):
        """Process extracted entities (V11 logic preserved)."""
        for ent in entities:
            eid = ent.get("id") or ent.get("summary", "unknown")[:30]
            if not eid:
                continue
            
            # Determine entity type
            etype = EntityType.PREFERENCE
            if eid.startswith("user:"):
                etype = EntityType.USER
            elif ent.get("type") == "preference":
                etype = EntityType.PREFERENCE
            elif ent.get("type") == "topic":
                etype = EntityType.TOPIC
            
            # Get or create entity
            node = self.wg.get_or_create_entity(
                type=etype,
                name=ent.get("summary", "Unknown"),
                source=EntitySource.LLM_INFERRED,
                attributes=ent.get("attributes", {})
            )
            
            # Update attributes if provided
            if ent.get("attributes"):
                self.wg.update_entity(node.id, ent.get("attributes"), source=EntitySource.LLM_INFERRED)
                if ent.get("summary"):
                    node.summary = ent["summary"]
            
            print(f"✨ [Reflection] Entity: {eid} -> {ent.get('summary')}")

    def _process_constraints(self, constraints: List[Dict]):
        """
        V14: Process constraint extractions.
        Writes to World Graph with constraint: prefix.
        """
        for constraint in constraints:
            summary = constraint.get("summary", "")
            if not summary:
                continue
            
            # Generate constraint ID
            constraint_id = constraint.get("id")
            if not constraint_id:
                # Auto-generate from summary
                slug = re.sub(r'[^a-z0-9]+', '_', summary.lower())[:30]
                constraint_id = f"constraint:{slug}"
            elif not constraint_id.startswith("constraint:"):
                constraint_id = f"constraint:{constraint_id}"
            
            # Build attributes
            attrs = constraint.get("attributes", {})
            if not attrs:
                attrs = {
                    "constraint_type": constraint.get("constraint_type", "physical"),
                    "implications": constraint.get("implications", []),
                    "criticality": constraint.get("criticality", 0.8)
                }
            
            # Create entity in World Graph
            node = self.wg.get_or_create_entity(
                type=EntityType.TOPIC,  # Constraints are stored as topics
                name=summary,
                source=EntitySource.USER_STATED,  # Trust constraint detection
                attributes=attrs
            )
            
            # Force constraint ID format
            if node.id != constraint_id:
                # Rename to constraint ID
                if node.id in self.wg.entities:
                    self.wg.entities[constraint_id] = self.wg.entities.pop(node.id)
                    self.wg.entities[constraint_id].id = constraint_id
                    node = self.wg.entities[constraint_id]
            
            # V14.1 FIX: Immediate promotion with criticality-based confidence
            # High criticality constraints get instant max confidence
            criticality = attrs.get("criticality", 0.8)
            node.lifecycle_state = EntityLifecycle.PROMOTED  # Always promote immediately
            
            if criticality > 0.8:
                # Critical constraints bypass normal rules entirely
                node.confidence = 1.0
                print(f"🚨 [Reflection] CRITICAL Constraint: {constraint_id} (criticality={criticality})")
            else:
                node.confidence = max(node.confidence, 0.8)
                print(f"⚠️ [Reflection] Constraint: {constraint_id} -> {summary}")

    def _process_retirements(self, retirements: List[str]):
        """
        V14: Archive resolved constraints.
        """
        for retire_id in retirements:
            if not retire_id:
                continue
            
            # Normalize ID
            if not retire_id.startswith("constraint:"):
                retire_id = f"constraint:{retire_id}"
            
            # Find and archive
            if retire_id in self.wg.entities:
                entity = self.wg.entities[retire_id]
                entity.lifecycle_state = EntityLifecycle.EPHEMERAL
                entity.confidence = 0.1
                print(f"✅ [Reflection] Retired: {retire_id}")
            else:
                # Try fuzzy match on constraint: entities
                for eid, entity in self.wg.entities.items():
                    if eid.startswith("constraint:") and retire_id.lower() in eid.lower():
                        entity.lifecycle_state = EntityLifecycle.EPHEMERAL
                        entity.confidence = 0.1
                        print(f"✅ [Reflection] Retired (fuzzy): {eid}")
                        break


# Singleton accessor
def get_reflection_engine() -> ReflectionEngine:
    """Get the global ReflectionEngine instance."""
    return ReflectionEngine()
