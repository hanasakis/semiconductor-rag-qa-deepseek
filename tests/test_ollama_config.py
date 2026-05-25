"""Tests for Ollama client configuration and model resolution."""

import os
import sys

import pytest


def test_ollama_model_from_env(monkeypatch):
    """Model MUST come from OLLAMA_MODEL env, not hardcoded."""
    monkeypatch.setenv("OLLAMA_MODEL", "deepseek-r1:8b")

    import src.config
    import importlib
    importlib.reload(src.config)

    assert src.config.OLLAMA_MODEL == "deepseek-r1:8b"


def test_ollama_model_custom_env(monkeypatch):
    """Verify that changing OLLAMA_MODEL env changes the config value."""
    monkeypatch.setenv("OLLAMA_MODEL", "my-custom-model:latest")

    import src.config
    import importlib
    importlib.reload(src.config)

    assert src.config.OLLAMA_MODEL == "my-custom-model:latest"


def test_client_uses_config_model():
    """OllamaClient reads model from config, not a hardcoded string."""
    from src.llm.ollama_client import OllamaClient
    from src.config import OLLAMA_MODEL

    client = OllamaClient(model=OLLAMA_MODEL)
    assert client.model == OLLAMA_MODEL


def test_client_default_uses_config():
    """When no model arg given, OllamaClient() uses OLLAMA_MODEL from config."""
    from src.llm.ollama_client import OllamaClient
    from src.config import OLLAMA_MODEL

    client = OllamaClient()
    assert client.model == OLLAMA_MODEL


def test_no_cloud_api_keys():
    """Verify no cloud API keys exist in the llm module source."""
    import inspect
    from src.llm import ollama_client, output_cleaner, prompts

    for module in (ollama_client, output_cleaner, prompts):
        source = inspect.getsource(module)
        assert "OPENAI_API_KEY" not in source
        assert "ANTHROPIC_API_KEY" not in source
        assert "DEEPSEEK_API_KEY" not in source
        assert "api.deepseek.com" not in source
        assert "api.openai.com" not in source


def test_no_hardcoded_deepseek_v4():
    """Neither deepseek-v4-flash nor deepseek-v4-pro may be hardcoded."""
    import inspect
    from src.llm import ollama_client

    source = inspect.getsource(ollama_client)
    assert "deepseek-v4-flash" not in source
    assert "deepseek-v4-pro" not in source
