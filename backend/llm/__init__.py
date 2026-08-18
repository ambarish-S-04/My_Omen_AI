from typing import Optional
from backend.config import config
from backend.llm.base import BaseLLMProvider
from backend.llm.gemini_provider import GeminiProvider
from backend.llm.ollama_provider import OllamaProvider
from backend.llm.openai_compat import OpenAICompatProvider

def get_llm_provider(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> BaseLLMProvider:
    name = (provider_name or config.LLM_PROVIDER).lower().strip()
    
    if name == "gemini":
        return GeminiProvider(api_key=api_key, model=model)
    elif name == "ollama":
        return OllamaProvider(model=model)
    elif name in ["openai", "groq", "openrouter"]:
        return OpenAICompatProvider(api_key=api_key, model=model)
    else:
        return GeminiProvider(api_key=api_key, model=model)

__all__ = ["BaseLLMProvider", "GeminiProvider", "OllamaProvider", "OpenAICompatProvider", "get_llm_provider"]
