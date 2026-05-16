import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from .desire import get_desire_system, Mood
from ..infrastructure.behavioral_trace import get_behavioral_trace, InfluenceType

@dataclass
class Trigger:
    id: str
    reason: str
    priority: int
    data: Dict[str, Any] = None

class TriggerSystem:
    """
    Evaluates system state to find 'Earned' proactive opportunities.
    """
    
    def __init__(self, world_graph):
        self.world_graph = world_graph
        self.desire_system = get_desire_system()
        self.trace = get_behavioral_trace()

    def evaluate(self) -> List[Trigger]:
        """Check for proactive triggers."""
        triggers = []
        
        # 1. Recurring Failure Detection
        # (This would normally check a history of failed actions)
        # For now, let's look for entities with low confidence or high 'uncertainty'
        
        # 2. Project Continuity
        # Look for the last 'active' project entity referenced in the last session
        active_project = self._find_active_project()
        if active_project:
            triggers.append(Trigger(
                id="project_continuity",
                reason=f"Continuing work on {active_project.name}",
                priority=2,
                data={"project_name": active_project.name}
            ))

        # 3. Emotional Delta
        # If loneliness is high, increase priority of any existing triggers
        mood = self.desire_system.get_mood()
        if mood == Mood.MELANCHOLIC:
            for t in triggers:
                t.priority += 1
                
        return sorted(triggers, key=lambda x: x.priority, reverse=True)

    def _find_active_project(self) -> Optional[Any]:
        """Find an entity of type 'project' that was recently touched."""
        from ..graph.world_graph import EntityType
        projects = [e for e in self.world_graph.entities.values() if e.type == EntityType.PROJECT]
        if not projects:
            return None
        
        # Return most recently referenced project
        return sorted(projects, key=lambda x: x.last_referenced, reverse=True)[0]

def get_trigger_system(world_graph) -> TriggerSystem:
    return TriggerSystem(world_graph)
