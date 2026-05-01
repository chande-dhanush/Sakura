import os
from typing import Dict, Any

class ModelContainer:
    """
    V19.0: Central registry for LLM providers.
    Supports lazy loading of providers and model routing.
    """
    def __init__(self, api_keys: Dict[str, str]):
        self.api_keys = api_keys

    def get_provider(self, provider_name: str, model_name: str):
        """Register and return provider instances."""
        if provider_name == "deepseek":
            from .deepseek import DeepSeekProvider  # V19.0
            return DeepSeekProvider(
                model=model_name, 
                api_key=self.api_keys.get("deepseek") or os.getenv("DEEPSEEK_API_KEY")
            )
        
        # Fallback to OpenAI if not deepseek (existing logic)
        elif provider_name == "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model_name, api_key=self.api_keys.get("openai"))
            
        return None
