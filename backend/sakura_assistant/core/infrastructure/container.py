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

from ...utils.logging import get_logger

log = get_logger("container")


def _get_int_env(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        log.warning(f"Invalid int for {name}: {raw}. Using default={default}")
        return default
    if value < min_value or value > max_value:
        log.warning(
            f"Out-of-range {name}={value}. Allowed [{min_value}, {max_value}], using default={default}"
        )
        return default
    return value


@dataclass
class LLMConfig:
    """Configuration for LLM models."""
    
    # Model names
    router_provider: str = "auto"
    planner_provider: str = "auto"
    responder_provider: str = "auto"
    verifier_provider: str = "auto"
    backup_provider: str = "auto"

    router_model: str = "llama-3.1-8b-instant"
    planner_model: str = "llama-3.3-70b-versatile"
    responder_model: str = "openai/gpt-oss-20b"
    verifier_model: str = "llama-3.1-8b-instant"
    backup_model: str = "google/gemini-2.0-flash-exp:free"

    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    deepseek_base_url: str = "https://api.deepseek.com"
    
    # Temperature settings
    router_temp: float = 0.0
    planner_temp: float = 0.1
    responder_temp: float = 0.4
    
    # Timeout and retry settings
    timeout: int = 60
    max_retries: int = 2

    # Execution safety rails (configurable with bounds)
    max_llm_calls: int = 6
    max_planner_iterations: int = 3
    planner_step_timeout_ms: int = 10000
    
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
        self.config = self._hydrate_config(self.config)
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self._log_stage_config()
    
    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key)
    
    @property
    def has_openrouter(self) -> bool:
        return bool(self.openrouter_api_key)
    
    @property
    def has_backup(self) -> bool:
        return (
            bool(self.google_api_key)
            or self.has_openrouter
            or bool(self.openai_api_key)
            or bool(self.deepseek_api_key)
        )

    @property
    def has_deepseek(self) -> bool:
        return bool(self.deepseek_api_key)
    
    def get_router_llm(self, overrides: Optional[Dict[str, Any]] = None):
        """Get or create router LLM (lazy-loaded)."""
        key = "router"
        if overrides:
            # V19: Support nested request-time overrides or flat settings overrides
            stage_overrides = overrides.get("router", {}) if isinstance(overrides.get("router"), dict) else {}
            return self._create_reliable_llm(
                stage="router",
                model=stage_overrides.get("model") or overrides.get("router_model", self.config.router_model),
                temperature=0.0,
                name="Router-Override",
                provider_override=stage_overrides.get("provider") or overrides.get("router_provider")
            )
            
        if key not in self._llms:
            self._llms[key] = self._create_reliable_llm(
                stage="router",
                model=self.config.router_model,
                temperature=self.config.router_temp,
                name="Router",
            )
        return self._llms[key]
    
    def get_planner_llm(self, overrides: Optional[Dict[str, Any]] = None):
        """Get or create planner LLM (lazy-loaded)."""
        key = "planner"
        if overrides:
            # V19: Support nested request-time overrides or flat settings overrides
            stage_overrides = overrides.get("planner", {}) if isinstance(overrides.get("planner"), dict) else {}
            return self._create_reliable_llm(
                stage="planner",
                model=stage_overrides.get("model") or overrides.get("planner_model", self.config.planner_model),
                temperature=stage_overrides.get("temperature") or overrides.get("planner_temp", self.config.planner_temp),
                name="Planner-Override",
                provider_override=stage_overrides.get("provider") or overrides.get("planner_provider")
            )
            
        if key not in self._llms:
            self._llms[key] = self._create_reliable_llm(
                stage="planner",
                model=self.config.planner_model,
                temperature=self.config.planner_temp,
                name="Planner",
            )
        return self._llms[key]
    
    def get_responder_llm(self, overrides: Optional[Dict[str, Any]] = None):
        """Get or create responder LLM (lazy-loaded)."""
        key = "responder"
        if overrides:
            # V19: Support nested request-time overrides or flat settings overrides
            stage_overrides = overrides.get("responder", {}) if isinstance(overrides.get("responder"), dict) else {}
            return self._create_reliable_llm(
                stage="responder",
                model=stage_overrides.get("model") or overrides.get("responder_model", self.config.responder_model),
                temperature=stage_overrides.get("temperature") or overrides.get("responder_temp", self.config.responder_temp),
                name="Responder-Override",
                provider_override=stage_overrides.get("provider") or overrides.get("responder_provider")
            )
            
        if key not in self._llms:
            self._llms[key] = self._create_reliable_llm(
                stage="responder",
                model=self.config.responder_model,
                temperature=self.config.responder_temp,
                name="Responder",
            )
        return self._llms[key]

    def get_verifier_llm(self, overrides: Optional[Dict[str, Any]] = None):
        """Get or create verifier LLM (lazy-loaded)."""
        key = "verifier"
        if overrides:
            # V19: Support nested request-time overrides or flat settings overrides
            stage_overrides = overrides.get("verifier", {}) if isinstance(overrides.get("verifier"), dict) else {}
            return self._create_reliable_llm(
                stage="verifier",
                model=stage_overrides.get("model") or overrides.get("verifier_model", self.config.verifier_model),
                temperature=0.0,
                name="Verifier-Override",
                provider_override=stage_overrides.get("provider") or overrides.get("verifier_provider")
            )
            
        if key not in self._llms:
            self._llms[key] = self._create_reliable_llm(
                stage="verifier",
                model=self.config.verifier_model,
                temperature=0.0,
                name="Verifier",
            )
        return self._llms[key]
    
    def get_backup_llm(self):
        """Get backup LLM for vision/failover."""
        if "backup" not in self._llms:
            self._llms["backup"] = self._create_backup_llm()
        return self._llms["backup"]
    
    def _create_reliable_llm(self, stage: str, model: str, temperature: float, name: str, provider_override: Optional[str] = None):
        """Create a ReliableLLM with stage-aware provider selection + backup."""
        from ..models.wrapper import ReliableLLM

        provider = provider_override or self._resolve_stage_provider(stage)
        primary = self._build_provider_llm(provider=provider, model=model, temperature=temperature, stage=stage)
        
        if primary is None:
            # If explicit provider was requested but failed (e.g. no key), log clearly and FAIL FAST
            if provider != "auto":
                log.error(f"Critical resolution failure: Stage '{stage}' requested provider '{provider}' but it is unavailable or misconfigured.")
                raise RuntimeError(
                    f"FATAL: Selected provider '{provider}' for stage '{stage}' is unavailable (missing API key or dependency). "
                    f"Please check your settings or use 'auto' for automatic fallback."
                )
                
            log.warning(f"{name}: provider={provider} unavailable, trying backup provider chain")
            primary = self._create_backup_llm()
            if primary is None:
                log.error(f"Fatal: Stage '{stage}' could not resolve any valid LLM provider.")
                return None
            return ReliableLLM(primary, None, name)

        backup = self._create_backup_llm(exclude_provider=provider) if self.has_backup else None
        return ReliableLLM(primary, backup, name)
    
    def _create_backup_llm(self, exclude_provider: Optional[str] = None):
        """Create backup LLM (Google > OpenRouter > OpenAI > DeepSeek)."""
        fallback_order = ["google", "openrouter", "openai", "deepseek"]
        for provider in fallback_order:
            if provider == exclude_provider:
                continue
            llm = self._build_provider_llm(
                provider=provider,
                model=self.config.backup_model if provider != "openai" else "gpt-4o-mini",
                temperature=0.3,
                stage="backup",
            )
            if llm is not None:
                return llm
        return None

    def _hydrate_config(self, base: LLMConfig) -> LLMConfig:
        cfg = LLMConfig(**base.__dict__)
        cfg.router_provider = os.getenv("ROUTER_PROVIDER", cfg.router_provider)
        cfg.planner_provider = os.getenv("PLANNER_PROVIDER", cfg.planner_provider)
        cfg.responder_provider = os.getenv("RESPONDER_PROVIDER", cfg.responder_provider)
        cfg.verifier_provider = os.getenv("VERIFIER_PROVIDER", cfg.verifier_provider)
        cfg.backup_provider = os.getenv("BACKUP_PROVIDER", cfg.backup_provider)
        cfg.router_model = os.getenv("ROUTER_MODEL", cfg.router_model)
        cfg.planner_model = os.getenv("PLANNER_MODEL", cfg.planner_model)
        cfg.responder_model = os.getenv("RESPONDER_MODEL", cfg.responder_model)
        cfg.verifier_model = os.getenv("VERIFIER_MODEL", cfg.verifier_model)
        cfg.backup_model = os.getenv("BACKUP_MODEL", cfg.backup_model)
        cfg.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", cfg.openrouter_base_url)
        cfg.deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", cfg.deepseek_base_url)
        cfg.max_retries = _get_int_env("LLM_MAX_RETRIES", cfg.max_retries, 0, 6)
        cfg.timeout = _get_int_env("LLM_TIMEOUT_SECONDS", cfg.timeout, 5, 180)
        cfg.max_llm_calls = _get_int_env("MAX_LLM_CALLS", cfg.max_llm_calls, 3, 20)
        cfg.max_planner_iterations = _get_int_env("MAX_PLANNER_ITERATIONS", cfg.max_planner_iterations, 1, 8)
        cfg.planner_step_timeout_ms = _get_int_env("PLANNER_STEP_TIMEOUT_MS", cfg.planner_step_timeout_ms, 1000, 60000)
        return cfg

    def _resolve_stage_provider(self, stage: str) -> str:
        explicit = getattr(self.config, f"{stage}_provider", "auto")
        if explicit != "auto":
            return explicit
        # Preserve current behavior: Groq-first where available
        if self.has_groq:
            return "groq"
        if self.google_api_key:
            return "google"
        if self.has_openrouter:
            return "openrouter"
        if self.openai_api_key:
            return "openai"
        if self.has_deepseek:
            return "deepseek"
        return "none"

    def _build_provider_llm(self, provider: str, model: str, temperature: float, stage: str):
        if provider == "groq":
            if not self.groq_api_key:
                return None
            from langchain_groq import ChatGroq
            return ChatGroq(
                model=model,
                temperature=temperature,
                groq_api_key=self.groq_api_key,
                max_retries=min(1, self.config.max_retries),
            )
        if provider == "google":
            if not self.google_api_key:
                return None
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError:
                log.warning("langchain_google_genai not installed, skipping Google provider")
                return None
            return ChatGoogleGenerativeAI(
                model=model if stage != "backup" else "gemini-2.0-flash",
                google_api_key=self.google_api_key,
                temperature=temperature,
                max_retries=self.config.max_retries,
                timeout=min(self.config.timeout, 30),
            )
        if provider == "openrouter":
            if not self.openrouter_api_key:
                return None
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                api_key=self.openrouter_api_key,
                base_url=self.config.openrouter_base_url,
                max_retries=self.config.max_retries,
                request_timeout=self.config.timeout,
            )
        if provider == "openai":
            if not self.openai_api_key:
                return None
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                api_key=self.openai_api_key,
                max_retries=self.config.max_retries,
                request_timeout=self.config.timeout,
            )
        if provider == "deepseek":
            if not self.deepseek_api_key:
                log.error(f"DeepSeek provider requested for stage '{stage}' but DEEPSEEK_API_KEY is missing.")
                return None
            
            # STALKER-G: Require explicit model for DeepSeek (v3 parity)
            if not model or model.strip() == "":
                log.error(f"DeepSeek provider requested for stage '{stage}' but no Model ID was provided.")
                raise RuntimeError(
                    f"Configuration Error: {stage.upper()}_PROVIDER=deepseek requires {stage.upper()}_MODEL to be explicitly configured. "
                    "DeepSeek does not support a default 'guess' model ID in this architecture."
                )
                
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model,
                temperature=temperature,
                api_key=self.deepseek_api_key,
                base_url=self.config.deepseek_base_url,
                max_retries=self.config.max_retries,
                request_timeout=self.config.timeout,
            )
        return None

    def _log_stage_config(self):
        log.info(
            "LLM stage configuration",
            extra={
                "router": {"provider": self._resolve_stage_provider("router"), "model": self.config.router_model},
                "planner": {"provider": self._resolve_stage_provider("planner"), "model": self.config.planner_model},
                "responder": {"provider": self._resolve_stage_provider("responder"), "model": self.config.responder_model},
                "verifier": {"provider": self._resolve_stage_provider("verifier"), "model": self.config.verifier_model},
                "base_urls": {
                    "openrouter": self.config.openrouter_base_url,
                    "deepseek": self.config.deepseek_base_url,
                },
                "keys_present": {
                    "groq": bool(self.groq_api_key),
                    "openrouter": bool(self.openrouter_api_key),
                    "openai": bool(self.openai_api_key),
                    "google": bool(self.google_api_key),
                    "deepseek": bool(self.deepseek_api_key),
                },
            },
        )


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
