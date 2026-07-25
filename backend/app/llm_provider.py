from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import settings


@lru_cache
def get_chat_model() -> BaseChatModel:
    """Returns a LangChain chat model chosen by settings.llm_provider.

    Every node/module in this app calls this one factory instead of
    instantiating a provider SDK directly, so switching LLM_PROVIDER in
    .env is the only change needed to move between Groq/OpenAI/Anthropic.
    """
    provider = settings.llm_provider.lower()

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=settings.llm_model_groq,
            temperature=settings.llm_temperature,
            api_key=settings.groq_api_key,
            timeout=settings.llm_timeout_seconds,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.llm_model_openai,
            temperature=settings.llm_temperature,
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.llm_model_anthropic,
            temperature=settings.llm_temperature,
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
        )

    if provider == "azure_openai":
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            azure_deployment=settings.azure_openai_chat_deployment,
            api_version=settings.azure_openai_api_version,
            api_key=settings.azure_openai_api_key,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
        )

    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
