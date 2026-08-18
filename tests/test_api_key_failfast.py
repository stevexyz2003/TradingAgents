"""Fail-fast credential validation in the client factory (native providers).

Scope matches factory._required_env_vars: anthropic, google, and azure are
validated in create_llm_client (they previously crashed mid-run on the first
LLM call); OpenAI-compatible providers are validated inside
OpenAIClient.get_llm() via the provider registry and are deliberately NOT
duplicated here. Bedrock uses the AWS credential chain and is exempt.
"""

import pytest

from tradingagents.llm_clients.factory import MissingAPIKeyError, create_llm_client


class TestNativeProviderValidation:

    def test_missing_anthropic_key_fails_at_startup(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(MissingAPIKeyError, match="ANTHROPIC_API_KEY"):
            create_llm_client("anthropic", "claude-sonnet-5")

    def test_empty_google_key_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_API_KEY", "   ")
        with pytest.raises(MissingAPIKeyError, match="GOOGLE_API_KEY"):
            create_llm_client("google", "gemini-3-pro")

    def test_anthropic_with_key_passes_validation(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        client = create_llm_client("anthropic", "claude-sonnet-5")
        assert client is not None

    def test_explicit_api_key_kwarg_replaces_key_check(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        client = create_llm_client("anthropic", "claude-sonnet-5", api_key="sk-explicit")
        assert client is not None

    def test_error_message_never_contains_values(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        with pytest.raises(MissingAPIKeyError) as excinfo:
            create_llm_client("google", "gemini-3-pro")
        message = str(excinfo.value)
        assert "GOOGLE_API_KEY" in message
        assert ".env" in message  # points at the fix, names only

    def test_openai_compatible_not_checked_by_factory(self, monkeypatch):
        """Registry-driven providers validate in get_llm(), not the factory."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        client = create_llm_client("openai", "gpt-5.5")
        assert client is not None  # get_llm() would raise, construction not


class TestAzureValidation:

    @staticmethod
    def _set_all(monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://res.openai.azure.com/")
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "my-deployment")
        monkeypatch.setenv("OPENAI_API_VERSION", "2026-03-01-preview")

    def test_missing_azure_endpoint_fails_at_startup(self, monkeypatch):
        self._set_all(monkeypatch)
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        with pytest.raises(MissingAPIKeyError, match="AZURE_OPENAI_ENDPOINT"):
            create_llm_client("azure", "gpt-5.5")

    def test_missing_azure_api_version_fails_at_startup(self, monkeypatch):
        self._set_all(monkeypatch)
        monkeypatch.delenv("OPENAI_API_VERSION", raising=False)
        with pytest.raises(MissingAPIKeyError, match="OPENAI_API_VERSION"):
            create_llm_client("azure", "gpt-5.5")

    def test_missing_azure_vars_all_listed(self, monkeypatch):
        for var in (
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT_NAME",
            "OPENAI_API_VERSION",
        ):
            monkeypatch.delenv(var, raising=False)
        with pytest.raises(MissingAPIKeyError) as excinfo:
            create_llm_client("azure", "gpt-5.5")
        message = str(excinfo.value)
        assert "AZURE_OPENAI_API_KEY" in message
        assert "AZURE_OPENAI_ENDPOINT" in message
        assert "AZURE_OPENAI_DEPLOYMENT_NAME" in message
        assert "OPENAI_API_VERSION" in message

    def test_api_key_kwarg_does_not_skip_endpoint_check(self, monkeypatch):
        """Explicit api_key replaces ONLY *_API_KEY checks — endpoint,
        deployment, and api-version stay validated."""
        self._set_all(monkeypatch)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        with pytest.raises(MissingAPIKeyError, match="AZURE_OPENAI_ENDPOINT"):
            create_llm_client("azure", "gpt-5.5", api_key="sk-explicit")

    def test_azure_with_all_vars_passes_validation(self, monkeypatch):
        self._set_all(monkeypatch)
        client = create_llm_client("azure", "gpt-5.5")
        assert client is not None
