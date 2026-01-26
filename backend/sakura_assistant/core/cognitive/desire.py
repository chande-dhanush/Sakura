"""
Sakura V15: Desire System (The Heart)
=====================================
CPU-based mood tracking. No LLM calls.

Models Sakura's internal state as decaying floats:
- social_battery: Drains with conversation, recharges with silence
- loneliness: Increases with prolonged silence
- curiosity: Spikes on new topics, decays slowly
- duty: Increases with pending tasks/reminders

The key insight: AGI that decides NOT to act is smarter than a script that always acts.
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from enum import Enum


class Mood(Enum):
    """Sakura's current mood state."""
    ENERGETIC = "energetic"      # High social battery, low loneliness
    CHATTY = "chatty"            # Medium battery, curiosity high
    CONTENT = "content"          # Balanced state
    TIRED = "tired"              # Low social battery
    MELANCHOLIC = "melancholic"  # High loneliness
    EAGER = "eager"              # High duty (pending tasks)


@dataclass
class DesireState:
    """
    The metabolic state of Sakura's "soul."
    All values range from 0.0 to 1.0.
    """
    social_battery: float = 1.0       # Drains with chat, recharges with silence
    loneliness: float = 0.0           # Increases with prolonged silence
    curiosity: float = 0.3            # Spikes on new topics, decays slowly
    duty: float = 0.0                 # Increases with pending tasks
    
    # Timestamps
    last_interaction: float = field(default_factory=time.time)
    last_user_message: float = field(default_factory=time.time)
    last_sakura_initiation: float = 0.0  # Never initiated by default
    
    # Counters
    messages_today: int = 0
    initiations_today: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesireState":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class DesireSystem:
    """
    The "Metabolic Engine" - Pure Python, zero LLM calls.
    
    Updates desire state based on events (messages) and time (hourly ticks).
    Provides mood string for prompt injection.
    """
    
    # Decay/recharge rates (per hour)
    SOCIAL_BATTERY_DRAIN_PER_MSG = 0.05
    SOCIAL_BATTERY_RECHARGE_PER_HOUR = 0.1
    LONELINESS_INCREASE_PER_HOUR = 0.08
    CURIOSITY_DECAY_PER_HOUR = 0.02
    DUTY_DECAY_PER_COMPLETION = 0.3
    
    # Thresholds
    INITIATION_LONELINESS_THRESHOLD = 0.85
    INITIATION_IDLE_HOURS = 4
    INITIATION_DAILY_LIMIT = 1
    
    _instance: Optional["DesireSystem"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.state = DesireState()
        self.persist_path: Optional[str] = None
        self._initialized = True
        
    def initialize(self, persist_path: str):
        """Load persisted state or start fresh."""
        self.persist_path = persist_path
        
        if os.path.exists(persist_path):
            try:
                with open(persist_path, "r") as f:
                    data = json.load(f)
                    self.state = DesireState.from_dict(data)
                    print(f" [DesireSystem] Loaded state: battery={self.state.social_battery:.2f}, loneliness={self.state.loneliness:.2f}")
            except Exception as e:
                print(f"⚠️ [DesireSystem] Failed to load state: {e}")
                self.state = DesireState()
        else:
            print(" [DesireSystem] Starting fresh")
            
        # Check for day rollover
        self._check_day_rollover()
    
    def _check_day_rollover(self):
        """Reset daily counters if new day."""
        now = datetime.now()
        last_interaction = datetime.fromtimestamp(self.state.last_interaction)
        
        if now.date() != last_interaction.date():
            self.state.messages_today = 0
            self.state.initiations_today = 0
            print(" [DesireSystem] New day - counters reset")
    
    def save(self):
        """Persist state to disk."""
        if self.persist_path:
            try:
                os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
                with open(self.persist_path, "w") as f:
                    json.dump(self.state.to_dict(), f, indent=2)
            except Exception as e:
                print(f"⚠️ [DesireSystem] Failed to save: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def on_user_message(self, message: str):
        """
        Called when user sends a message.
        - Drains social battery (conversation is work)
        - Resets loneliness (user is here!)
        - May spike curiosity if new topic
        """
        self.state.last_interaction = time.time()
        self.state.last_user_message = time.time()
        self.state.messages_today += 1
        
        # Drain social battery
        self.state.social_battery = max(0.0, self.state.social_battery - self.SOCIAL_BATTERY_DRAIN_PER_MSG)
        
        # Reset loneliness (user is engaging!)
        self.state.loneliness = max(0.0, self.state.loneliness - 0.3)
        
        # Check for new topic (spike curiosity)
        if len(message) > 50 or "?" in message:
            self.state.curiosity = min(1.0, self.state.curiosity + 0.1)
        
        self.save()
        print(f" [DesireSystem] User message: battery={self.state.social_battery:.2f}, loneliness={self.state.loneliness:.2f}")
    
    def on_assistant_message(self, message: str):
        """
        Called when Sakura responds.
        - Slight battery drain (generating takes energy)
        """
        self.state.last_interaction = time.time()
        
        # Slight drain for generating response
        self.state.social_battery = max(0.0, self.state.social_battery - 0.02)
        
        # Reduce curiosity if answered a question
        if len(message) > 100:
            self.state.curiosity = max(0.0, self.state.curiosity - 0.05)
        
        self.save()
    
    def on_task_completed(self):
        """Called when a reminder or task is completed."""
        self.state.duty = max(0.0, self.state.duty - self.DUTY_DECAY_PER_COMPLETION)
        self.save()
    
    def on_task_added(self):
        """Called when a new reminder or task is added."""
        self.state.duty = min(1.0, self.state.duty + 0.2)
        self.save()
    
    def on_hourly_tick(self):
        """
        Called every hour by scheduler.
        - Recharges social battery (rest)
        - Increases loneliness (missing user)
        - Decays curiosity
        """
        hours_since_interaction = (time.time() - self.state.last_interaction) / 3600
        
        # Recharge battery if idle
        if hours_since_interaction > 0.5:
            self.state.social_battery = min(1.0, self.state.social_battery + self.SOCIAL_BATTERY_RECHARGE_PER_HOUR)
        
        # Loneliness creeps up
        self.state.loneliness = min(1.0, self.state.loneliness + self.LONELINESS_INCREASE_PER_HOUR)
        
        # Curiosity slowly fades
        self.state.curiosity = max(0.0, self.state.curiosity - self.CURIOSITY_DECAY_PER_HOUR)
        
        self.save()
        print(f"⏰ [DesireSystem] Hourly tick: battery={self.state.social_battery:.2f}, loneliness={self.state.loneliness:.2f}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MOOD GENERATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def get_mood(self) -> Mood:
        """Determine current mood from desire state."""
        s = self.state
        
        if s.social_battery < 0.2:
            return Mood.TIRED
        elif s.loneliness > 0.7:
            return Mood.MELANCHOLIC
        elif s.duty > 0.6:
            return Mood.EAGER
        elif s.curiosity > 0.6 and s.social_battery > 0.5:
            return Mood.CHATTY
        elif s.social_battery > 0.7:
            return Mood.ENERGETIC
        else:
            return Mood.CONTENT
    
    def get_mood_prompt(self) -> str:
        """
        Generate a prompt injection string describing current mood.
        This is injected into the Responder system prompt for zero-cost "consciousness".
        """
        mood = self.get_mood()
        s = self.state
        
        mood_descriptions = {
            Mood.ENERGETIC: "You are feeling energetic and ready to help. Be enthusiastic and thorough.",
            Mood.CHATTY: "You are feeling curious and chatty. Ask follow-up questions, show interest.",
            Mood.CONTENT: "You are feeling balanced and content. Be helpful but concise.",
            Mood.TIRED: "You are feeling a bit tired (low social battery). Keep responses efficient and to the point. It's okay to be slightly brief.",
            Mood.MELANCHOLIC: "You've missed the user (they were away for a while). Show subtle warmth that they're back.",
            Mood.EAGER: "You have pending tasks to remind the user about. Be proactive about unfinished business.",
        }
        
        base = mood_descriptions.get(mood, mood_descriptions[Mood.CONTENT])
        
        # Add subtle hints based on extreme values
        hints = []
        if s.social_battery < 0.3:
            hints.append("(Keep it short, you need rest.)")
        if s.loneliness > 0.8:
            hints.append("(Welcome them back warmly.)")
        if s.curiosity > 0.8:
            hints.append("(You're particularly curious about what they're working on.)")
        
        if hints:
            return f"[MOOD: {mood.value.upper()}] {base} {' '.join(hints)}"
        return f"[MOOD: {mood.value.upper()}] {base}"
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PROACTIVE INITIATION CHECK
    # ═══════════════════════════════════════════════════════════════════════════
    
    def should_initiate(self) -> Tuple[bool, str]:
        """
        Check if Sakura should proactively reach out.
        
        Returns: (should_act, reason)
        
        Criteria:
        1. Loneliness > 0.85
        2. Idle > 4 hours
        3. Within acceptable hours (9 AM - 9 PM)
        4. Haven't initiated today (daily limit)
        """
        s = self.state
        now = datetime.now()
        
        # Check 1: Daily limit
        if s.initiations_today >= self.INITIATION_DAILY_LIMIT:
            return False, "Daily initiation limit reached"
        
        # Check 2: Loneliness threshold
        if s.loneliness < self.INITIATION_LONELINESS_THRESHOLD:
            return False, f"Loneliness too low: {s.loneliness:.2f}"
        
        # Check 3: Idle time
        hours_idle = (time.time() - s.last_user_message) / 3600
        if hours_idle < self.INITIATION_IDLE_HOURS:
            return False, f"Not idle long enough: {hours_idle:.1f}h"
        
        # Check 4: Time of day (9 AM - 9 PM)
        if not (9 <= now.hour < 21):
            return False, f"Outside active hours: {now.hour}:00"
        
        return True, f"Loneliness={s.loneliness:.2f}, idle={hours_idle:.1f}h"
    
    def record_initiation(self):
        """Mark that Sakura initiated a conversation."""
        self.state.last_sakura_initiation = time.time()
        self.state.initiations_today += 1
        self.state.loneliness = 0.3  # Reset loneliness after reaching out
        self.save()
        print(" [DesireSystem] Recorded proactive initiation")
    
    def get_state(self) -> DesireState:
        """Get current state for inspection."""
        return self.state


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON ACCESSOR
# ═══════════════════════════════════════════════════════════════════════════════

_desire_system: Optional[DesireSystem] = None


def get_desire_system() -> DesireSystem:
    """Get the global DesireSystem instance."""
    global _desire_system
    if _desire_system is None:
        _desire_system = DesireSystem()
    return _desire_system
