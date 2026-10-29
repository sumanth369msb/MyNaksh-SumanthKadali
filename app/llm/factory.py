from app.core.config import settings
from app.llm.mock import MockLLMProvider
from app.llm.openai import OpenAIProvider


def create_llm_provider():
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key.strip("\"' "),
            base_url=settings.openai_base_url.strip("\"' "),
            model=settings.openai_model.strip("\"' "),
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    if provider in ("nvidia", "nim"):
        api_key = settings.nvidia_api_key.strip("\"' ") if settings.nvidia_api_key else settings.openai_api_key
        model_name = settings.nvidia_model.strip("\"' ") if settings.nvidia_model else "nvidia/llama-3.1-nemotron-ultra-253b-v1"
        return OpenAIProvider(
            api_key=api_key,
            base_url=settings.nvidia_base_url.strip("\"' "),
            model=model_name,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    if provider in ("openrouter", "or"):
        api_key = settings.openrouter_api_key.strip("\"' ") if settings.openrouter_api_key else settings.openai_api_key
        model_name = settings.openrouter_model.strip("\"' ") if settings.openrouter_model else "meta-llama/llama-3.3-70b-instruct"
        return OpenAIProvider(
            api_key=api_key,
            base_url=settings.openrouter_base_url.strip("\"' "),
            model=model_name,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    if provider == "mock":
        return MockLLMProvider()
    raise ValueError(f"Unknown LLM provider: {provider}")
