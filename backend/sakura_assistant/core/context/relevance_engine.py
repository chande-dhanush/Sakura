import re
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

class ContextRelevanceEngine:
    """
    Context Relevance Engine (Phase B / Step 2)
    ===========================================
    Ranks context blocks and memories hierarchically, suppressing stale or irrelevant
    memories to prevent creepy/annoying memory resurfacing.
    """
    
    def __init__(self):
        pass

    def rank_memories(self, memories: List[Dict[str, Any]], active_app: str, active_project: str) -> List[Dict[str, Any]]:
        """
        Scores and ranks memory items.
        Each memory dict should have keys:
            - 'text': str (the memory content)
            - 'timestamp': str or float (when it was stored)
            - 'confidence': float (original retrieval confidence)
        """
        scored_memories = []
        now = time.time()
        
        for mem in memories:
            text = mem.get("text", "")
            if not text:
                continue
                
            # Base score from retrieval confidence
            score = mem.get("confidence", 0.5) * 10.0
            
            # 1. Recency Boost/Decay
            ts_val = mem.get("timestamp", now)
            try:
                if isinstance(ts_val, str):
                    dt = datetime.fromisoformat(ts_val)
                    ts = dt.timestamp()
                else:
                    ts = float(ts_val)
            except Exception:
                ts = now
                
            age_hours = (now - ts) / 3600.0
            # Exponential decay: halflife of 48 hours
            decay_factor = 0.5 ** (age_hours / 48.0)
            score *= decay_factor
            
            # 2. Active App Match Boost
            if active_app:
                app_base = active_app.split(".")[0].lower()
                if app_base in text.lower():
                    score += 4.0  # significant boost
                    
            # 3. Current Project/Folder Boost
            if active_project:
                project_base = active_project.replace("\\", "/").split("/")[-1].lower()
                if project_base in text.lower():
                    score += 3.0
                    
            # 4. Keyword matches for file types or extensions (e.g. .py, .js)
            if active_app in ["code.exe", "devenv.exe"]:
                if any(ext in text.lower() for ext in [".py", ".ts", ".js", ".json", ".html", ".css", ".md"]):
                    score += 2.0
            
            scored_memories.append({
                "text": text,
                "score": score,
                "original": mem,
                "recency": decay_factor
            })
            
        # Sort descending by score
        scored_memories.sort(key=lambda x: x["score"], reverse=True)
        return scored_memories

    def suppress_memories(self, scored_memories: List[Dict[str, Any]], threshold: float = 2.0) -> List[Dict[str, Any]]:
        """
        Filters out memories that do not meet the minimum relevance threshold
        to prevent creepy or irrelevant details from polluting the context.
        """
        return [m for m in scored_memories if m["score"] >= threshold]


class ContextBudgeter:
    """
    Context Budgeter (Phase B)
    ==========================
    Allocates character/token budgets dynamically based on classification
    to prevent context bloat and minimize token spend.
    """
    
    @staticmethod
    def get_budget(mode: str) -> Dict[str, int]:
        if mode == "CHAT":
            return {
                "history": 2500,
                "memory": 800,
                "active_context": 200,
                "clipboard": 0,
                "screen": 0
            }
        elif mode == "DIRECT":
            return {
                "history": 800,
                "memory": 400,
                "active_context": 600,
                "clipboard": 800,
                "screen": 1200
            }
        elif mode == "PLAN":
            return {
                "history": 1500,
                "memory": 2000,
                "active_context": 1000,
                "clipboard": 1000,
                "screen": 1000
            }
        else: # DEFAULT
            return {
                "history": 1500,
                "memory": 1000,
                "active_context": 500,
                "clipboard": 500,
                "screen": 500
            }
