"""
V7 Background Scheduler - Proactive Assistant Capabilities

Features:
- One-shot Reminders ("remind me in 10 min")
- Recurring Events (Morning Briefing at 8 AM)
- Thread-safe daemon execution
- Graceful shutdown

Design:
- Single daemon thread with 1s tick
- Priority queue for events
- Callback-based execution
"""

import time
import threading
import heapq
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum, auto

from ..utils.stability_logger import log_flow, log_warning


class EventType(Enum):
    """Types of scheduled events."""
    REMINDER = auto()      # One-shot user reminder
    DAILY = auto()         # Recurring daily task
    INTERVAL = auto()      # Recurring every N seconds


@dataclass(order=True)
class ScheduledEvent:
    """Event in the scheduler queue."""
    trigger_time: float  # Unix timestamp (for ordering)
    event_id: str = field(compare=False)
    event_type: EventType = field(compare=False)
    callback: Callable = field(compare=False)
    callback_args: tuple = field(default_factory=tuple, compare=False)
    callback_kwargs: Dict[str, Any] = field(default_factory=dict, compare=False)
    recurring_interval: Optional[float] = field(default=None, compare=False)  # For INTERVAL type
    daily_time: Optional[str] = field(default=None, compare=False)  # For DAILY type ("HH:MM")


class Scheduler:
    """
    V7 Background Scheduler.
    
    Thread-safe, supports one-shot and recurring events.
    """
    
    def __init__(self):
        self._queue: list = []  # heapq of ScheduledEvent
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._event_counter = 0
        self._cancelled: set = set()  # Set of cancelled event IDs
        
        log_flow("Scheduler", "V7 Scheduler initialized")
    
    def start(self) -> bool:
        """Start the scheduler daemon thread."""
        if self._running:
            return True
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="Scheduler")
        self._thread.start()
        
        log_flow("Scheduler", "Daemon started")
        return True
    
    def stop(self):
        """Stop the scheduler gracefully."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        log_flow("Scheduler", "Stopped")
    
    def schedule_reminder(self, 
                          message: str, 
                          delay_seconds: float,
                          callback: Callable[[str], None]) -> str:
        """
        Schedule a one-shot reminder.
        
        Args:
            message: Reminder message
            delay_seconds: Seconds from now
            callback: Function to call with message when triggered
            
        Returns:
            Event ID for cancellation
        """
        trigger_time = time.time() + delay_seconds
        
        with self._lock:
            self._event_counter += 1
            event_id = f"reminder_{self._event_counter}"
            
            event = ScheduledEvent(
                trigger_time=trigger_time,
                event_id=event_id,
                event_type=EventType.REMINDER,
                callback=callback,
                callback_args=(message,)
            )
            
            heapq.heappush(self._queue, event)
            
        log_flow("Scheduler", f"Reminder scheduled: '{message[:30]}...' in {delay_seconds:.0f}s (ID: {event_id})")
        return event_id
    
    def schedule_daily(self,
                       time_str: str,
                       callback: Callable,
                       name: str = "daily_task") -> str:
        """
        Schedule a daily recurring event.
        
        Args:
            time_str: Time in "HH:MM" format (24h)
            callback: Function to call
            name: Human-readable name
            
        Returns:
            Event ID
        """
        trigger_time = self._get_next_daily_trigger(time_str)
        
        with self._lock:
            self._event_counter += 1
            event_id = f"daily_{name}_{self._event_counter}"
            
            event = ScheduledEvent(
                trigger_time=trigger_time,
                event_id=event_id,
                event_type=EventType.DAILY,
                callback=callback,
                daily_time=time_str
            )
            
            heapq.heappush(self._queue, event)
            
        log_flow("Scheduler", f"Daily event scheduled: {name} at {time_str} (ID: {event_id})")
        return event_id
    
    def schedule_interval(self,
                          interval_seconds: float,
                          callback: Callable,
                          name: str = "interval_task") -> str:
        """
        Schedule a recurring interval event.
        
        Args:
            interval_seconds: Repeat interval
            callback: Function to call
            name: Human-readable name
            
        Returns:
            Event ID
        """
        trigger_time = time.time() + interval_seconds
        
        with self._lock:
            self._event_counter += 1
            event_id = f"interval_{name}_{self._event_counter}"
            
            event = ScheduledEvent(
                trigger_time=trigger_time,
                event_id=event_id,
                event_type=EventType.INTERVAL,
                callback=callback,
                recurring_interval=interval_seconds
            )
            
            heapq.heappush(self._queue, event)
            
        log_flow("Scheduler", f"Interval event scheduled: {name} every {interval_seconds}s (ID: {event_id})")
        return event_id
    
    def cancel(self, event_id: str) -> bool:
        """Cancel a scheduled event."""
        with self._lock:
            if event_id in self._cancelled:
                return False
            self._cancelled.add(event_id)
            log_flow("Scheduler", f"Cancelled: {event_id}")
            return True
    
    def _get_next_daily_trigger(self, time_str: str) -> float:
        """Calculate next trigger time for a daily event."""
        hour, minute = map(int, time_str.split(":"))
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If target time has passed today, schedule for tomorrow
        if target <= now:
            target += timedelta(days=1)
        
        return target.timestamp()
    
    def _run_loop(self):
        """Main scheduler loop (runs in daemon thread)."""
        while self._running:
            try:
                self._tick()
                time.sleep(1.0)  # 1 second tick resolution
            except Exception as e:
                log_warning(f"Scheduler tick error: {e}")
    
    def _tick(self):
        """Process due events."""
        now = time.time()
        events_to_reschedule = []
        
        with self._lock:
            while self._queue and self._queue[0].trigger_time <= now:
                event = heapq.heappop(self._queue)
                
                # Skip cancelled events
                if event.event_id in self._cancelled:
                    self._cancelled.discard(event.event_id)
                    continue
                
                # Execute callback
                try:
                    event.callback(*event.callback_args, **event.callback_kwargs)
                except Exception as e:
                    log_warning(f"Scheduler callback error ({event.event_id}): {e}")
                
                # Reschedule recurring events
                if event.event_type == EventType.DAILY:
                    new_trigger = self._get_next_daily_trigger(event.daily_time)
                    event.trigger_time = new_trigger
                    events_to_reschedule.append(event)
                elif event.event_type == EventType.INTERVAL:
                    event.trigger_time = now + event.recurring_interval
                    events_to_reschedule.append(event)
            
            # Re-add recurring events
            for evt in events_to_reschedule:
                heapq.heappush(self._queue, evt)
    
    def get_pending_count(self) -> int:
        """Get number of pending events."""
        with self._lock:
            return len([e for e in self._queue if e.event_id not in self._cancelled])


# --- Singleton Instance ---
_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Scheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


def start_scheduler() -> bool:
    """Start the global scheduler."""
    return get_scheduler().start()


def stop_scheduler():
    """Stop the global scheduler."""
    if _scheduler:
        _scheduler.stop()


# --- Convenience Functions ---

def remind_me(message: str, delay_seconds: float, callback: Callable[[str], None]) -> str:
    """
    Quick reminder scheduling.
    
    Example:
        remind_me("Check the oven", 600, lambda msg: print(f"⏰ {msg}"))
    """
    return get_scheduler().schedule_reminder(message, delay_seconds, callback)


def schedule_morning_briefing(time_str: str, callback: Callable) -> str:
    """
    Schedule daily morning briefing.
    
    Example:
        schedule_morning_briefing("08:00", lambda: send_briefing())
    """
    return get_scheduler().schedule_daily(time_str, callback, name="morning_briefing")


def memory_maintenance() -> int:
    """
    V13: Daily memory maintenance - demote stale entities.
    
    Returns:
        Number of entities demoted.
    """
    from .world_graph import get_world_graph
    
    graph = get_world_graph()
    demoted = 0
    
    for entity in list(graph.entities.values()):
        if entity.check_lifecycle_demotion():
            demoted += 1
    
    if demoted > 0:
        graph.save()
        print(f"🧹 [Memory Maintenance] Demoted {demoted} stale entities")
    else:
        print("🧹 [Memory Maintenance] No entities to demote")
    
    return demoted


def schedule_memory_maintenance(time_str: str = "03:00") -> str:
    """
    V13: Schedule daily memory maintenance.
    
    Default: 3:00 AM daily
    
    Example:
        schedule_memory_maintenance("03:00")
    """
    return get_scheduler().schedule_daily(
        time_str, 
        memory_maintenance, 
        name="memory_maintenance"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# V14: SLEEP CYCLE - FACT CRYSTALLIZATION & DREAM JOURNAL
# ═══════════════════════════════════════════════════════════════════════════════

import json
import os
import re
from datetime import date

# Configuration
DREAM_JOURNAL_PATH = "data/dream_journal.jsonl"
CRYSTALLIZATION_COOLDOWN_PATH = "data/.last_crystallization"
COOLDOWN_HOURS = 24


def _log_dream(data: dict):
    """Append entry to Dream Journal for UI visibility."""
    try:
        from ..config import get_project_root
        
        path = os.path.join(get_project_root(), DREAM_JOURNAL_PATH)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat(),
            **data
        }
        
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            
    except Exception as e:
        print(f"⚠️ [Dream Journal] Log failed: {e}")


def _should_crystallize() -> bool:
    """Check if cooldown period has passed since last crystallization."""
    try:
        from ..config import get_project_root
        
        cooldown_file = os.path.join(get_project_root(), CRYSTALLIZATION_COOLDOWN_PATH)
        
        if not os.path.exists(cooldown_file):
            return True
        
        with open(cooldown_file, "r") as f:
            last_run = float(f.read().strip())
        
        hours_elapsed = (time.time() - last_run) / 3600
        return hours_elapsed >= COOLDOWN_HOURS
        
    except Exception:
        return True  # Default to allowing crystallization


def _mark_crystallization_done():
    """Record that crystallization was just performed."""
    try:
        from ..config import get_project_root
        
        cooldown_file = os.path.join(get_project_root(), CRYSTALLIZATION_COOLDOWN_PATH)
        os.makedirs(os.path.dirname(cooldown_file), exist_ok=True)
        
        with open(cooldown_file, "w") as f:
            f.write(str(time.time()))
            
    except Exception as e:
        print(f"⚠️ [Sleep Cycle] Cooldown mark failed: {e}")


async def crystallize_facts() -> int:
    """
    V14: Extract hard facts from summary and write to World Graph.
    
    Features:
    - Runs on startup (not 3 AM - laptop may be offline)
    - 24-hour cooldown to prevent spam
    - Logs to Dream Journal for /api/dreams endpoint
    - Robust JSON parsing per Red Team audit
    
    Returns:
        Number of facts/constraints crystallized
    """
    # Check cooldown
    if not _should_crystallize():
        print("💤 [Sleep Cycle] Cooldown active, skipping crystallization")
        return 0
    
    from .world_graph import get_world_graph, EntityType, EntitySource, EntityLifecycle
    from ..memory.summary_memory import get_summary_memory
    
    wg = get_world_graph()
    sm = get_summary_memory()
    
    # Check if there's anything to crystallize
    if not sm.summary or len(sm.summary) < 50:
        _log_dream({
            "status": "skipped",
            "reason": "No summary to process"
        })
        return 0
    
    print(f"🌙 [Sleep Cycle] Crystallizing facts from {len(sm.summary)} char summary...")
    
    # Get LLM for crystallization
    try:
        from .container import get_container
        llm = get_container().get_router_llm()  # Use fast 8B model
    except Exception as e:
        _log_dream({"status": "error", "error": f"LLM init failed: {e}"})
        return 0
    
    CRYSTALLIZE_PROMPT = f"""Extract ONLY hard FACTS from this conversation summary.
Discard opinions, small talk, and transient requests.

Summary:
{sm.summary[:2000]}

Output JSON:
{{
  "facts": [
    {{"category": "preference|health|schedule|relationship|interest", "fact": "...", "confidence": 0.9}}
  ],
  "constraints": [
    {{"type": "physical|temporal|resource", "constraint": "...", "implications": [], "criticality": 0.8}}
  ]
}}

RULES:
- Return VALID JSON only
- If nothing significant, return: {{"facts": [], "constraints": []}}
- Focus on things the user would want remembered long-term
"""
    
    try:
        from langchain_core.messages import HumanMessage
        response = await llm.ainvoke([HumanMessage(content=CRYSTALLIZE_PROMPT)])
        content = response.content.strip()
        
        # Robust JSON parsing
        data = _safe_parse_crystallize_json(content)
        if not data:
            _log_dream({"status": "error", "error": "JSON parse failed"})
            return 0
        
        facts_added = 0
        constraints_added = 0
        
        # Process facts
        for fact in data.get("facts", []):
            fact_text = fact.get("fact", "")
            if not fact_text or len(fact_text) < 5:
                continue
            
            node = wg.get_or_create_entity(
                type=EntityType.TOPIC,
                name=fact_text[:100],
                source=EntitySource.MEMORY_RECALLED,
                attributes={
                    "category": fact.get("category", "general"),
                    "crystallized": True,
                    "confidence": fact.get("confidence", 0.7)
                }
            )
            # Promote crystallized facts
            node.lifecycle = EntityLifecycle.PROMOTED
            facts_added += 1
        
        # Process constraints
        for constraint in data.get("constraints", []):
            constraint_text = constraint.get("constraint", "")
            if not constraint_text or len(constraint_text) < 5:
                continue
            
            # Generate constraint ID
            slug = re.sub(r'[^a-z0-9]+', '_', constraint_text.lower())[:30]
            constraint_id = f"constraint:crystallized_{slug}"
            
            node = wg.get_or_create_entity(
                type=EntityType.TOPIC,
                name=constraint_text[:100],
                source=EntitySource.USER_STATED,
                attributes={
                    "constraint_type": constraint.get("type", "physical"),
                    "implications": constraint.get("implications", []),
                    "criticality": constraint.get("criticality", 0.8),
                    "crystallized": True
                }
            )
            
            # Force constraint ID and promote
            if node.id in wg.entities:
                wg.entities[constraint_id] = wg.entities.pop(node.id)
                wg.entities[constraint_id].id = constraint_id
                wg.entities[constraint_id].lifecycle = EntityLifecycle.PROMOTED
            
            constraints_added += 1
        
        # Save World Graph
        wg.save()
        
        # Mark cooldown
        _mark_crystallization_done()
        
        # Log to Dream Journal
        _log_dream({
            "status": "success",
            "facts_crystallized": facts_added,
            "constraints_learned": constraints_added,
            "summary_chars_processed": len(sm.summary),
            "facts_detail": [f.get("fact", "")[:50] for f in data.get("facts", [])[:3]],
            "constraints_detail": [c.get("constraint", "")[:50] for c in data.get("constraints", [])[:3]]
        })
        
        print(f"✨ [Sleep Cycle] Crystallized: {facts_added} facts, {constraints_added} constraints")
        
        # Clear processed summary
        sm.clear()
        
        return facts_added + constraints_added
        
    except Exception as e:
        _log_dream({"status": "error", "error": str(e)})
        print(f"❌ [Sleep Cycle] Crystallization failed: {e}")
        return 0


def _safe_parse_crystallize_json(content: str) -> Optional[dict]:
    """Robust JSON parsing with fallbacks (Red Team requirement)."""
    # Strategy 1: Clean markdown
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
        fixed = re.sub(r',\s*([}\]])', r'\1', content)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    
    # Strategy 4: Extract JSON object
    try:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group())
    except json.JSONDecodeError:
        pass
    
    return None


def run_sleep_cycle_on_startup():
    """
    V14: Run crystallization on app startup if cooldown passed.
    Call this from server.py startup.
    """
    import asyncio
    
    print("🌙 [Sleep Cycle] Checking for pending crystallization...")
    
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(crystallize_facts())
        else:
            loop.run_until_complete(crystallize_facts())
    except RuntimeError:
        # No event loop, create one
        asyncio.run(crystallize_facts())
    except Exception as e:
        print(f"⚠️ [Sleep Cycle] Startup run failed: {e}")


def get_dream_journal(limit: int = 10) -> list:
    """
    V14: Read recent Dream Journal entries for /api/dreams.
    """
    try:
        from ..config import get_project_root
        
        path = os.path.join(get_project_root(), DREAM_JOURNAL_PATH)
        
        if not os.path.exists(path):
            return []
        
        dreams = []
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines[-limit:]:
                try:
                    dreams.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
        
        return list(reversed(dreams))
        
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# V15: COGNITIVE ARCHITECTURE - PROACTIVE FEATURES
# ═══════════════════════════════════════════════════════════════════════════════

PLANNED_INITIATIONS_PATH = "data/planned_initiations.json"


async def precompute_initiations() -> int:
    """
    V15: Generate tomorrow's proactive messages at 3 AM.
    Uses idle night capacity so daytime initiation is zero-cost.
    
    Returns:
        Number of messages generated
    """
    print("🌙 [Sleep Cycle] Pre-computing tomorrow's icebreakers...")
    
    from .world_graph import get_world_graph
    from .cognitive.proactive import get_proactive_scheduler
    from ..config import get_project_root
    
    wg = get_world_graph()
    
    # Gather context for icebreakers
    context_parts = []
    
    # 1. Active constraints
    constraints = [
        e.summary for e in wg.entities.values()
        if e.id.startswith("constraint:") and e.confidence > 0.5
    ]
    if constraints:
        context_parts.append(f"Active constraints: {', '.join(constraints[:3])}")
    
    # 2. Recent topics
    recent_topics = [
        e.name for e in wg.entities.values()
        if e.type.value == "topic" and e.reference_count >= 2
    ][:5]
    if recent_topics:
        context_parts.append(f"Recent topics: {', '.join(recent_topics)}")
    
    # 3. User identity
    user = wg.get_user_identity()
    if user.summary:
        context_parts.append(f"User: {user.summary}")
    
    context = "\n".join(context_parts) if context_parts else "No special context."
    
    PROMPT = f"""Generate 3 short, friendly check-in messages for tomorrow.
    
Context about user:
{context}

Rules:
- Each message < 60 characters
- Reference specific things user cares about
- Vary tone: caring, curious, playful
- Be natural, not robotic

Output JSON only:
{{"messages": ["msg1", "msg2", "msg3"]}}
"""
    
    try:
        from .container import get_container
        llm = get_container().get_router_llm()  # Fast 8B
        
        from langchain_core.messages import HumanMessage
        response = await llm.ainvoke([HumanMessage(content=PROMPT)])
        content = response.content.strip()
        
        # Parse JSON
        data = _safe_parse_crystallize_json(content)
        if not data or "messages" not in data:
            print("⚠️ [Sleep Cycle] Failed to parse icebreakers")
            return 0
        
        messages = data["messages"]
        
        # Save via ProactiveScheduler
        scheduler = get_proactive_scheduler()
        scheduler.initiations_path = os.path.join(get_project_root(), PLANNED_INITIATIONS_PATH)
        scheduler.save_planned_initiations(messages)
        
        # Log to dream journal
        _log_dream({
            "type": "initiations",
            "status": "success",
            "messages_generated": len(messages),
            "context_used": context[:200]
        })
        
        print(f"✨ [Sleep Cycle] Generated {len(messages)} icebreakers for tomorrow")
        return len(messages)
        
    except Exception as e:
        print(f"❌ [Sleep Cycle] Pre-computation failed: {e}")
        _log_dream({"type": "initiations", "status": "error", "error": str(e)})
        return 0


def run_hourly_desire_tick():
    """
    V15: Hourly tick for DesireSystem.
    Updates loneliness, social battery decay.
    """
    try:
        from .cognitive.desire import get_desire_system
        desire = get_desire_system()
        desire.on_hourly_tick()
    except Exception as e:
        print(f"⚠️ [DesireSystem] Hourly tick failed: {e}")


async def run_hourly_proactive_check():
    """
    V15: Hourly check for proactive initiation.
    """
    try:
        from .cognitive.proactive import get_proactive_scheduler
        scheduler = get_proactive_scheduler()
        await scheduler.check_and_initiate()
    except Exception as e:
        print(f"⚠️ [ProactiveScheduler] Hourly check failed: {e}")


def schedule_cognitive_tasks():
    """
    V15: Schedule all cognitive background tasks.
    Call this from server.py startup.
    """
    scheduler = get_scheduler()
    
    # Hourly tick for desire decay
    scheduler.schedule_interval(
        interval_seconds=3600,  # 1 hour
        callback=run_hourly_desire_tick,
        name="desire_tick"
    )
    
    print("🧠 [Cognitive] Scheduled hourly desire tick")


async def run_full_sleep_cycle():
    """
    V15: Complete sleep cycle (crystallization + pre-computation).
    Run on startup with cooldown.
    """
    # 1. Crystallize facts (V14)
    await crystallize_facts()
    
    # 2. Pre-compute initiations (V15)
    await precompute_initiations()
