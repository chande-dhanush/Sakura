"""
Sakura V10.3 Summary Memory
===========================
Simple context compression to survive beyond the 5-turn sliding window.

Gemini's insight: "You don't need a complex class. Just a thread that runs 
every 5 turns: summary = llm('Summarize this chat so far')"

Implementation:
- Compresses old messages into a running summary
- Injects summary into system prompt
- Triggered after every 5 messages
"""
import json
import os
from typing import List, Dict, Optional
from datetime import datetime


class SummaryMemory:
    """
    Lightweight memory compressor for long-context conversations.
    
    Usage:
        memory = SummaryMemory(llm)
        memory.add_turn("user", "What's the weather in Tokyo?")
        memory.add_turn("assistant", "It's 15°C and sunny in Tokyo.")
        
        # After 5+ turns, get compressed summary for system prompt
        context = memory.get_context_injection()
    """
    
    # Persist summary to disk to survive restarts
    PERSIST_FILE = "data/summary_memory.json"
    COMPRESS_THRESHOLD = 5  # Compress after this many new messages
    
    def __init__(self, llm=None, persist_path: str = None):
        """
        Args:
            llm: LangChain LLM for summarization (optional - degrades gracefully)
            persist_path: Path to persist summary (defaults to data/summary_memory.json)
        """
        self.llm = llm
        self.summary = ""
        self.recent_messages: List[Dict] = []  # Messages since last compression
        self.message_count_since_compress = 0
        
        # Persistence
        if persist_path:
            self.persist_path = persist_path
        else:
            from sakura_assistant.utils.pathing import get_project_root
            self.persist_path = os.path.join(get_project_root(), self.PERSIST_FILE)
        
        # Load existing summary
        self._load()
    
    def add_turn(self, role: str, content: str) -> None:
        """Add a message to the buffer."""
        self.recent_messages.append({
            "role": role,
            "content": content[:500],  # Cap message length
            "timestamp": datetime.now().isoformat()
        })
        self.message_count_since_compress += 1
        
        # Auto-compress if threshold reached
        if self.message_count_since_compress >= self.COMPRESS_THRESHOLD:
            self.compress()
    
    def compress(self) -> str:
        """Compress recent messages into running summary."""
        if not self.recent_messages:
            return self.summary
        
        # Build content to summarize
        msgs_text = "\n".join([
            f"{m['role']}: {m['content']}" 
            for m in self.recent_messages
        ])
        
        if self.llm:
            try:
                from langchain_core.messages import SystemMessage, HumanMessage
                
                prompt = f"""Summarize this conversation segment in 2-3 sentences.
Focus on: key facts, user preferences, and decisions made.
Do NOT add information not present.

Previous context: {self.summary or 'None'}

New messages:
{msgs_text}"""
                
                response = self.llm.invoke([HumanMessage(content=prompt)])
                new_summary = response.content.strip()
                
                # Append to running summary (keep it bounded)
                if self.summary:
                    self.summary = f"{self.summary}\n{new_summary}"
                else:
                    self.summary = new_summary
                
                # Keep summary bounded (last 1000 chars)
                if len(self.summary) > 1000:
                    self.summary = self.summary[-1000:]
                
                print(f" [SummaryMemory] Compressed {len(self.recent_messages)} messages")
                
            except Exception as e:
                print(f"⚠️ [SummaryMemory] LLM compression failed: {e}")
                # Fallback: just keep last few messages as-is
                self.summary += f"\n[Recent: {msgs_text[:200]}...]"
        else:
            # No LLM: naive concatenation
            self.summary += f"\n[Messages {self.message_count_since_compress}]: {msgs_text[:200]}..."
        
        # Clear buffer
        self.recent_messages = []
        self.message_count_since_compress = 0
        
        # Persist
        self._save()
        
        return self.summary
    
    def get_context_injection(self) -> str:
        """Get summary for injection into system prompt."""
        if not self.summary:
            return ""
        
        return f"""[CONTEXT FROM EARLIER IN CONVERSATION]
{self.summary}
[END EARLIER CONTEXT]
"""
    
    def clear(self) -> None:
        """Clear all summary memory (e.g., on explicit reset)."""
        self.summary = ""
        self.recent_messages = []
        self.message_count_since_compress = 0
        self._save()
        print("️ [SummaryMemory] Cleared")
    
    def _load(self) -> None:
        """Load persisted summary from disk."""
        try:
            if os.path.exists(self.persist_path):
                with open(self.persist_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.summary = data.get("summary", "")
                    print(f" [SummaryMemory] Loaded ({len(self.summary)} chars)")
        except Exception as e:
            print(f"⚠️ [SummaryMemory] Load failed: {e}")
    
    def _save(self) -> None:
        """Persist summary to disk."""
        try:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
            with open(self.persist_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "summary": self.summary,
                    "updated_at": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            print(f"⚠️ [SummaryMemory] Save failed: {e}")


# Singleton for global access
_summary_memory: Optional[SummaryMemory] = None

def get_summary_memory(llm=None) -> SummaryMemory:
    """Get or create the global SummaryMemory instance."""
    global _summary_memory
    if _summary_memory is None:
        _summary_memory = SummaryMemory(llm=llm)
    return _summary_memory

def reset_summary_memory() -> None:
    """Reset the global SummaryMemory instance."""
    global _summary_memory
    if _summary_memory:
        _summary_memory.clear()
    _summary_memory = None
