import json
import asyncio
import logging
import re
from typing import Dict, Any, Optional, Tuple
from langchain_core.messages import SystemMessage, HumanMessage
from ...config import MEMORY_JUDGER_SYSTEM_PROMPT, MEMORY_JUDGER_MODEL, MAX_MEMORY_JUDGER_TOKENS
from ...utils.flight_recorder import get_recorder

logger = logging.getLogger(__name__)

class MemoryJudger:
    """
    Evaluates conversation turns for long-term memory storage (FAISS).
    Uses a fast, cheap model (llama-3.1-8b-instant) to judge importance.
    
    V18.2: Integrated into the main pipeline to solve BUG-03.
    """
    
    def __init__(self, llm_wrapper):
        """
        Args:
            llm_wrapper: ReliableLLM instance for classification
        """
        self.llm = llm_wrapper
        self.recorder = get_recorder()

    async def evaluate(self, user_input: str, assistant_response: str, trace_id: Optional[str] = None):
        """
        Entry point for memory judgment. Runs asynchronously (fire-and-forget).
        
        Args:
            user_input: The raw user message
            assistant_response: The generated response
            trace_id: Correlation ID for Flight Recorder
        """
        try:
            # 1. Prepare prompt
            # V18.1: Importance scoring rules are already in the system prompt
            prompt = MEMORY_JUDGER_SYSTEM_PROMPT
            content = f"User: {user_input}"
            
            messages = [
                SystemMessage(content=prompt),
                HumanMessage(content=content)
            ]
            
            # 2. Call LLM (Cheap model)
            # max_tokens=128 is enough for "yes [N] - reason"
            # We use ainvoke for non-blocking execution
            response = await self.llm.ainvoke(messages, trace_id=trace_id)
            
            # 3. Parse result
            should_store, importance, fact = self._parse_judgement(response.content)
            
            # 4. Action
            status = "SKIPPED"
            if should_store and importance >= 7:
                from ...memory.faiss_store import get_memory_store
                store = get_memory_store()
                
                # CRITICAL: Store the factual extraction, not the raw chat format
                # This ensures RAG retrieval is high-quality
                store.add_message(content=fact, role="user")
                status = "STORED"
            
            # 5. Log to Flight Recorder (Visible in traces)
            # This increases span_count from 6 -> 8 on CHAT traces
            self.recorder.span(
                stage="MemoryJudger",
                status="SUCCESS",
                content=f"{status} (Imp: {importance}): {fact[:50]}...",
                trace_id=trace_id,
                details={
                    "should_store": should_store,
                    "importance": importance,
                    "extracted_fact": fact,
                    "raw_judgement": response.content
                }
            )
            
            print(f" [MemoryJudger] {status} (Importance: {importance})")
            
        except Exception as e:
            logger.error(f" [MemoryJudger] Error: {e}")
            self.recorder.span(
                stage="MemoryJudger",
                status="ERROR",
                content=str(e),
                trace_id=trace_id
            )

    def _parse_judgement(self, text: str) -> Tuple[bool, int, str]:
        """
        Parses the LLM output format: "yes [N] - reason" or "no - reason"
        
        Returns:
            (should_store, importance, fact)
        """
        text = text.strip()
        lower_text = text.lower()
        
        if lower_text.startswith("yes"):
            try:
                # 1. Extract importance [N]
                importance = 5
                match = re.search(r'\[(\d+)\]', text)
                if match:
                    importance = int(match.group(1))
                
                # 2. Extract the fact (everything after the dash or the rating)
                if "-" in text:
                    fact = text.split("-", 1)[1].strip()
                else:
                    fact = re.sub(r'yes\s*\[\d+\]\s*:?', '', text, flags=re.IGNORECASE).strip()
                
                # Fallback to original text if extraction is too short
                if len(fact) < 5:
                    fact = text
                    
                return True, importance, fact
            except Exception as e:
                logger.warning(f" [MemoryJudger] Parse error on 'yes': {e}")
                return True, 5, text
                
        return False, 0, ""
