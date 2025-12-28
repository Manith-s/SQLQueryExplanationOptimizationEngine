"""
LLM provider interface and factory.

This module provides a common interface for LLM providers and a factory
to instantiate the configured provider.
"""

import importlib
import os
from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        """
        Generate completion for a prompt with optional system context.

        Args:
            prompt: The prompt to complete
            system: Optional system context/instruction

        Returns:
            Generated completion text

        Raises:
            Exception: If completion fails
        """
        pass


def get_llm() -> LLMProvider:
    """
    Get the configured LLM provider instance.

    The provider is determined by settings.LLM_PROVIDER:
    - "dummy": Returns fixed responses (for testing)
    - "ollama": Uses local Ollama server

    Returns:
        LLMProvider instance

    Raises:
        ValueError: If provider not found or initialization fails
    """
    provider_map = {
        "dummy": "app.providers.provider_dummy",
        "ollama": "app.providers.provider_ollama",
    }

    # Always read from env at call time to respect test overrides
    provider_name = os.getenv("LLM_PROVIDER", "dummy")  # Default to dummy if not set
    provider_module = provider_map.get(provider_name)
    if not provider_module:
        raise ValueError(
            f"Unknown LLM provider: {provider_name}. "
            f"Valid options are: {list(provider_map.keys())}"
        )

    try:
        # Import the provider module
        module = importlib.import_module(provider_module)

        # Get the provider class (assumed to be the only class inheriting from LLMProvider)
        provider_class = None
        for attr in dir(module):
            obj = getattr(module, attr)
            if (
                isinstance(obj, type)
                and issubclass(obj, LLMProvider)
                and obj != LLMProvider
            ):
                provider_class = obj
                break

        if not provider_class:
            raise ValueError(
                f"No LLMProvider implementation found in {provider_module}"
            )

        # Instantiate the provider
        instance = provider_class()

        # If ollama selected but unavailable, fallback to dummy
        if provider_name == "ollama":
            try:
                from app.providers.provider_ollama import OllamaLLMProvider as _OL

                if hasattr(_OL, "is_available") and not _OL.is_available():
                    # fallback to dummy
                    module = importlib.import_module(provider_map["dummy"])
                    for attr in dir(module):
                        obj = getattr(module, attr)
                        if (
                            isinstance(obj, type)
                            and issubclass(obj, LLMProvider)
                            and obj != LLMProvider
                        ):
                            return obj()
            except Exception:
                pass

        return instance

    except Exception as e:
        raise ValueError(
            f"Failed to initialize LLM provider '{provider_name}': {str(e)}"
        ) from e
