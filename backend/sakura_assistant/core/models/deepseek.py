from langchain_openai import ChatOpenAI

class DeepSeekProvider(ChatOpenAI):
    """
    V19.0: DeepSeek Provider Bridge.
    Uses OpenAI-compatible API but points to DeepSeek endpoints.
    """
    def __init__(self, model: str, api_key: str):
        super().__init__(
            model=model,  # e.g., deepseek-v4-flash
            api_key=api_key,
            base_url="https://api.deepseek.com/v1"
        )
