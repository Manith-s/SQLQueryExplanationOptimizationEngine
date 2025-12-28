"""
Structure tests for the application.

Verifies that all key modules can be imported and have expected structure.
"""

import pytest


def test_config_import():
    """Test that config module can be imported."""
    from app.core.config import Settings, settings

    assert Settings is not None
    assert settings is not None


def test_llm_adapter_import():
    """Test that LLM adapter module can be imported."""
    from app.core.llm_adapter import LLMProvider, get_llm

    assert LLMProvider is not None
    assert get_llm is not None


def test_sql_analyzer_import():
    """Test that SQL analyzer module can be imported."""
    from app.core.sql_analyzer import extract_columns, extract_tables, parse_sql

    assert parse_sql is not None
    assert extract_tables is not None
    assert extract_columns is not None


def test_plan_heuristics_import():
    """Test that plan heuristics module can be imported."""
    from app.core.plan_heuristics import analyze_plan, suggest_from_plan

    assert analyze_plan is not None
    assert suggest_from_plan is not None


def test_providers_import():
    """Test that provider modules can be imported."""
    from app.providers.provider_dummy import DummyLLMProvider
    from app.providers.provider_ollama import OllamaLLMProvider

    assert DummyLLMProvider is not None
    assert OllamaLLMProvider is not None


def test_routers_import():
    """Test that router modules can be imported."""
    from app.routers import explain, health, lint, optimize

    assert health is not None
    assert lint is not None
    assert explain is not None
    assert optimize is not None


def test_main_app_import():
    """Test that main app can be imported."""
    from app.main import app

    assert app is not None


def test_dummy_provider_works():
    """Test that dummy provider returns expected responses."""
    from app.providers.provider_dummy import DummyLLMProvider

    provider = DummyLLMProvider()
    assert provider.is_available() is True

    response = provider.generate("test prompt")
    assert isinstance(response, str)
    assert len(response) > 0


def test_ollama_provider_raises_not_implemented():
    """Test that Ollama provider raises NotImplementedError as expected."""
    from app.providers.provider_ollama import OllamaLLMProvider

    provider = OllamaLLMProvider()
    assert provider.is_available() is False

    with pytest.raises(NotImplementedError):
        provider.generate("test prompt")
