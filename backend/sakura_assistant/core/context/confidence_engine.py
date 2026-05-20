import os
from typing import Dict, Any, List, Optional

class ConfidenceEngine:
    """
    Confidence Engine (Phase C / Step 4)
    ====================================
    Calculates confidence, relevance, and ambiguity scores for inputs,
    memories, and tool routing, guiding system behavior dynamically.
    """
    
    @staticmethod
    def score_implicit_reference(query: str, resolved: Dict[str, Any]) -> Dict[str, float]:
        """Scores the resolution of implicit references (e.g. 'that file', 'the error')."""
        if not resolved:
            return {"confidence": 0.0, "relevance": 0.0, "ambiguity": 1.0}
            
        # If we have a file path resolved
        if "file_path" in resolved:
            path = resolved["file_path"]
            if os.path.exists(path):
                return {"confidence": 0.9, "relevance": 0.95, "ambiguity": 0.1}
            else:
                return {"confidence": 0.5, "relevance": 0.6, "ambiguity": 0.5}
                
        # If we resolved an error context
        if "error_context" in resolved:
            return {"confidence": 0.8, "relevance": 0.85, "ambiguity": 0.2}
            
        return {"confidence": 0.5, "relevance": 0.5, "ambiguity": 0.5}

    @staticmethod
    def score_memory_retrieval(query: str, memories: List[Dict[str, Any]]) -> Dict[str, float]:
        """Scores the confidence of a retrieved memory set against the user query."""
        if not memories:
            return {"confidence": 0.0, "relevance": 0.0, "ambiguity": 1.0}
            
        # Take the top memory score
        top_score = memories[0].get("score", 0.0)
        
        # Normalize top score to a 0.0 - 1.0 confidence value
        # A score of 8+ is very high confidence
        confidence = min(1.0, top_score / 10.0)
        relevance = min(1.0, top_score / 8.0)
        ambiguity = max(0.0, 1.0 - relevance)
        
        return {"confidence": confidence, "relevance": relevance, "ambiguity": ambiguity}

    @staticmethod
    def determine_action_posture(confidence_data: Dict[str, float]) -> str:
        """
        Determines action posture based on confidence score:
        - confidence < 0.4 -> 'CLARIFY' (Ask user for clarification)
        - 0.4 <= confidence < 0.75 -> 'HEDGE' (Proceed but note assumption / hedge response)
        - confidence >= 0.75 -> 'PROCEED' (Proceed directly)
        """
        conf = confidence_data.get("confidence", 1.0)
        if conf < 0.4:
            return "CLARIFY"
        elif conf < 0.75:
            return "HEDGE"
        return "PROCEED"
