"""Fail-fast API key validation at client creation (D6).

create_llm_client must reject a missing/empty key for the chosen provider at
startup with a clear message naming the environment variable — instead of
crashing mid-run on the first LLM call.

Note: the autouse _dummy_api_keys fixture in conftest sets placeholder values
for all key variables, so each test explicitly deletes/empties what it needs.
"""

import pytest

from tradingagents.llm_clients.factory import MissingAPIKeyError, create_llm_client


class TestFailFastKeyValidation:

    def test_missing_openai_key_fails_at_startup(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(MissingAPIKeyError, match="OPENAI_API_KEY"):
            create_llm_client("openai", "gpt-5.4")

    def test_empty_openai_key_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "")
        with pytest.raises(MissingAPIKeyError, match="OPENAI_API_KEY"):
            create_llm_client("openai", "gpt-5.4")

    def test_whitespace_key_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "   ")
        with pytest.raises(MissingAPIKeyError, match="OPENAI_API_KEY"):
            create_llm_client("openai", "gpt-5.4")

    def test_compatible_provider_env_var_from_provider_config(self, monkeypatch):
        """xai and friends reuse the _PROVIDER_CONFIG env-var map."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        with pytest.raises(MissingAPIKeyError, match="XAI_API_KEY"):
            create_llm_client("xai", "grok-4")

    def test_ollama_needs_no_keys(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        client = create_llm_client("ollama", "llama3")
        assert client is not None

    def test_explicit_api_key_kwarg_replaces_key_check(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        client = create_llm_client("openai", "gpt-5.4", api_key="sk-explicit")
        assert client is not None


class TestAzureValidation:

    def test_missing_azure_endpoint_fails_at_startup(self, monkeypatch):
        # AZURE_OPENAI_API_KEY has a conftest placeholder; deployment set here.
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "my-deployment")
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        with pytest.raises(MissingAPIKeyError, match="AZURE_OPENAI_ENDPOINT"):
            create_llm_client("azure", "gpt-5.4")

    def test_missing_azure_vars_all_listed(self, monkeypatch):
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
        with pytest.raises(MissingAPIKeyError) as excinfo:
            create_llm_client("azure", "gpt-5.4")
        message = str(excinfo.value)
        assert "AZURE_OPENAI_API_KEY" in message
        assert "AZURE_OPENAI_ENDPOINT" in message
        assert "AZURE_OPENAI_DEPLOYMENT_NAME" in message

    def test_api_key_kwarg_does_not_skip_endpoint_check(self, monkeypatch):
        """Explicit api_key replaces ONLY *_API_KEY checks — endpoint and
        deployment stay validated (Codex MEDIUM 4)."""
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "my-deployment")
        with pytest.raises(MissingAPIKeyError, match="AZURE_OPENAI_ENDPOINT"):
            create_llm_client("azure", "gpt-5.4", api_key="sk-explicit")

    def test_azure_with_all_vars_passes_validation(self, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://res.openai.azure.com/")
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "my-deployment")
        client = create_llm_client("azure", "gpt-5.4")
        assert client is not None
