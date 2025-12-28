"""
Ollama LLM provider implementation.

This provider uses the Ollama HTTP API to generate completions using
locally running models.
"""

from typing import Optional

import requests

from app.core.config import settings
from app.core.llm_adapter import LLMProvider


class OllamaLLMProvider(LLMProvider):
    """
    LLM provider that uses local Ollama server for completions.

    Configuration via environment variables:
    - OLLAMA_HOST: Ollama server URL (default: http://127.0.0.1:11434)
    - LLM_MODEL: Model to use (default: llama2:13b-instruct)
    - LLM_TIMEOUT_S: Request timeout in seconds (default: 30)
    """

    def __init__(self):
        """Initialize provider with configuration from settings."""
        self.host = settings.OLLAMA_HOST.rstrip("/")
        self.model = settings.LLM_MODEL
        self.timeout = 30  # Default timeout
        self.max_retries = 2  # Number of retries on timeout
        self.retry_timeout = 15  # Shorter timeout for retries

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        """
        Generate completion using Ollama's HTTP API.

        Args:
            prompt: The prompt to complete
            system: Optional system context/instruction

        Returns:
            Generated completion text

        Raises:
            Exception: If completion fails
        """
        import time
        start_time = time.time()
        last_error = None

        # Prepare headers and payload
        headers = {'Content-Type': 'application/json'}
        payload = {
            "model": self.model,
            "prompt": prompt[:1000],  # Limit prompt size
            "stream": False
        }

        # Add system context if provided
        if system:
            payload["system"] = system[:500]  # Limit system prompt size

        # Try with initial timeout, then retry with shorter timeouts
        timeouts = [self.timeout] + [self.retry_timeout] * self.max_retries

        for attempt, timeout in enumerate(timeouts, 1):
            try:
                print(f"Attempt {attempt}/{len(timeouts)} with {timeout}s timeout")
                print(f"Making request to {self.host}/api/generate")
                print(f"Model: {self.model}")

                # Make request
                response = requests.post(
                    f"{self.host}/api/generate",
                    headers=headers,
                    json=payload,
                    timeout=timeout
                )

                # Check for errors
                response.raise_for_status()

                # Parse response
                result = response.json()
                if "error" in result:
                    raise Exception(f"Ollama error: {result['error']}")

                # Log timing information
                end_time = time.time()
                duration = end_time - start_time
                print(f"Request completed in {duration:.2f}s")
                print(f"Model metrics: {result.get('total_duration', 0) / 1e9:.2f}s total")

                return result.get("response", "").strip()

            except Exception as e:
                last_error = e
                print(f"Attempt {attempt} failed: {str(e)}")
                if attempt < len(timeouts):
                    print("Retrying with shorter timeout...")
                    continue
                break

        # If all attempts failed, raise the last error
        raise Exception(f"All {len(timeouts)} attempts failed. Last error: {str(last_error)}")

    @classmethod
    def is_available(cls) -> bool:
        """
        Check if Ollama server is available.

        Returns:
            True if Ollama server responds to version check
        """
        try:
            host = settings.OLLAMA_HOST.rstrip("/")
            response = requests.get(f"{host}/api/version", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

