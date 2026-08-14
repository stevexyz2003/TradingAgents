import os
from typing import Optional, Tuple

from .base_client import BaseLLMClient

# Providers that use the OpenAI-compatible chat completions API
_OPENAI_COMPATIBLE = (
    "openai", "xai", "deepseek", "qwen", "glm", "ollama", "openrouter",
)


class MissingAPIKeyError(ValueError):
    """Raised at startup when the chosen provider's credentials are absent.

    Defined here (not in a provider module) so it is importable without
    pulling in heavy LLM SDKs.
    """


def _required_env_vars(provider_lower: str) -> Tuple[str, ...]:
    """Environment variables required by the given provider.

    OpenAI-compatible third-party providers reuse the env-var map from
    ``openai_client._PROVIDER_CONFIG`` (imported lazily and only in that
    branch — the same module is imported right after in create_llm_client,
    so the factory's lazy-import design stays intact for the other
    provider families).
    """
    if provider_lower == "openai":
        return ("OPENAI_API_KEY",)
    if provider_lower in _OPENAI_COMPATIBLE:
        from .openai_client import _PROVIDER_CONFIG

        env_var = _PROVIDER_CONFIG.get(provider_lower, (None, None))[1]
        return (env_var,) if env_var else ()
    if provider_lower == "anthropic":
        return ("ANTHROPIC_API_KEY",)
    if provider_lower == "google":
        return ("GOOGLE_API_KEY",)
    if provider_lower == "azure":
        # Source: azure_client.py docstring. OPENAI_API_VERSION is required by
        # AzureChatOpenAI and env is the only supported path (api_version is
        # not a passthrough kwarg) — validate it here for a clear message.
        return (
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT_NAME",
            "OPENAI_API_VERSION",
        )
    return ()


def _validate_credentials(provider: str, provider_lower: str, kwargs: dict) -> None:
    """Fail fast when the provider's credentials are missing or empty.

    An explicit ``api_key`` kwarg replaces ONLY the ``*_API_KEY`` checks;
    other required variables (Azure endpoint/deployment) stay validated.
    Values are never logged — only variable NAMES appear in the message.
    """
    required = _required_env_vars(provider_lower)
    if kwargs.get("api_key"):
        required = tuple(v for v in required if not v.endswith("_API_KEY"))
    missing = [v for v in required if not os.environ.get(v, "").strip()]
    if missing:
        raise MissingAPIKeyError(
            f"Missing credentials for LLM provider '{provider}': "
            + ", ".join(missing)
            + ". Set the variable(s) in your environment or .env file "
            "(cp .env.example .env) — see 'Required APIs' in README.md."
        )


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Provider modules are imported lazily so that simply importing this
    factory (e.g. during test collection) does not pull in heavy LLM SDKs
    or fail when their API keys are absent.

    Args:
        provider: LLM provider name
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured BaseLLMClient instance

    Raises:
        MissingAPIKeyError: If the provider's credentials are missing/empty
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()

    # Fail fast at startup (graph construction) instead of mid-run on the
    # first LLM call. Covers both entry paths: CLI and Python API.
    _validate_credentials(provider, provider_lower, kwargs)

    if provider_lower in _OPENAI_COMPATIBLE:
        from .openai_client import OpenAIClient
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "anthropic":
        from .anthropic_client import AnthropicClient
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        from .google_client import GoogleClient
        return GoogleClient(model, base_url, **kwargs)

    if provider_lower == "azure":
        from .azure_client import AzureOpenAIClient
        return AzureOpenAIClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
