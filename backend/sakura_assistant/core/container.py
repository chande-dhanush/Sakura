"""
Sakura V10 Dependency Container
================================
Dependency injection container for LLM configuration.

Extracted from llm.py as part of SOLID refactoring.
- Manages model configuration
- Lazy-loads LLM instances
"""
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class LLMConfig:
    """Configuration for LLM models."""
    
    # Model names
    router_model: str = "llama-3.1-8b-instant"
    planner_model: str = "llama-3.3-70b-versatile"
    responder_model: str = "openai/gpt-oss-20b"
    backup_model: str = "google/gemini-2.0-flash-exp:free"
    
    # Temperature settings
    router_temp: float = 0.0
    planner_temp: float = 0.1
    responder_temp: float = 0.6
    
    # Timeout and retry settings
    timeout: int = 60
    max_retries: int = 2
    
    # Cache settings
    enable_cache: bool = True
    cache_ttl_seconds: int = 3600


@dataclass
class Container:
    """
    Dependency injection container for Sakura components.
    
    Provides lazy-loading of LLM instances and centralized configuration.
    """
    
    config: LLMConfig = field(default_factory=LLMConfig)
    _llms: Dict[str, Any] = field(default_factory=dict, repr=False)
    
    def __post_init__(self):
        """Load API keys from environment."""
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
    
    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key)
    
    @property
    def has_openrouter(self) -> bool:
        return bool(self.openrouter_api_key)
    
    @property
    def has_backup(self) -> bool:
        return self.has_openrouter or bool(self.openai_api_key)
    
    def get_router_llm(self):
        """Get or create router LLM (lazy-loaded)."""
        if "router" not in self._llms:
            self._llms["router"] = self._create_reliable_llm(
                self.config.router_model,
                self.config.router_temp,
                "Router"
            )
        return self._llms["router"]
    
    def get_planner_llm(self):
        """Get or create planner LLM (lazy-loaded)."""
        if "planner" not in self._llms:
            self._llms["planner"] = self._create_reliable_llm(
                self.config.planner_model,
                self.config.planner_temp,
                "Planner"
            )
        return self._llms["planner"]
    
    def get_responder_llm(self):
        """Get or create responder LLM (lazy-loaded)."""
        if "responder" not in self._llms:
            self._llms["responder"] = self._create_reliable_llm(
                self.config.responder_model,
                self.config.responder_temp,
                "Responder"
            )
        return self._llms["responder"]
    
    def get_backup_llm(self):
        """Get backup LLM for vision/failover."""
        if "backup" not in self._llms:
            self._llms["backup"] = self._create_backup_llm()
        return self._llms["backup"]
    
    def _create_reliable_llm(self, model: str, temperature: float, name: str):
        """Create a ReliableLLM with primary + backup."""
        from langchain_groq import ChatGroq
        
        if not self.groq_api_key:
            return self.get_backup_llm()
        
        # Import here to avoid circular dependency
        from .llm import ReliableLLM
        
        primary = ChatGroq(
            model=model,
            temperature=temperature,
            groq_api_key=self.groq_api_key,
            max_retries=1
        )
        
        backup = self.get_backup_llm() if self.has_backup else None
        
        return ReliableLLM(primary, backup, name)
    
    def _create_backup_llm(self):
        """Create backup LLM (OpenRouter or OpenAI)."""
        from langchain_openai import ChatOpenAI
        
        if self.openrouter_api_key:
            return ChatOpenAI(
                model=self.config.backup_model,
                temperature=0.3,
                api_key=self.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
                max_retries=self.config.max_retries,
                request_timeout=30
            )
        elif self.openai_api_key:
            return ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.3,
                api_key=self.openai_api_key,
                max_retries=self.config.max_retries,
                request_timeout=20
            )
        
        return None


# Global container instance
_container: Optional[Container] = None


def get_container() -> Container:
    """Get the global container instance."""
    global _container
    if _container is None:
        _container = Container()
    return _container


def reset_container():
    """Reset the global container (for testing)."""
    global _container
    _container = None
