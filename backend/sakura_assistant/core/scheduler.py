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

