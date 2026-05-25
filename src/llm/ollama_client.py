"""Ollama DeepSeek-R1 client for local LLM inference.

All model calls are local. No cloud API keys or external services.
"""

import logging
from typing import Optional

import ollama

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL, MAX_TOKENS, TEMPERATURE
from src.llm.output_cleaner import clean_r1_output_full
from src.llm.prompts import SYSTEM_PROMPT, RAG_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


class OllamaClient:
    """Wrapper around ollama Python SDK for DeepSeek-R1 inference."""

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        max_tokens: int = MAX_TOKENS,
        temperature: float = TEMPERATURE,
    ):
        self._base_url = base_url
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._client = ollama.Client(host=base_url)

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def verify_model(self) -> bool:
        """Check that the configured model exists in the local Ollama instance."""
        try:
            models = self._client.list()
            model_names = [m["name"] for m in models.get("models", [])]
            return self._model in model_names
        except Exception as e:
            logger.error("Cannot connect to Ollama at %s: %s", self._base_url, e)
            return False

    def generate(
        self,
        prompt: str,
        system: str = SYSTEM_PROMPT,
    ) -> dict:
        """Generate a response from DeepSeek-R1.

        Args:
            prompt: The full prompt to send.
            system: System prompt (not supported natively by DeepSeek-R1,
                    so it is prepended to the prompt).

        Returns:
            dict with keys: reasoning, answer, raw, model, usage.
        """
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        try:
            response = self._client.generate(
                model=self._model,
                prompt=full_prompt,
                options={
                    "temperature": self._temperature,
                    "num_predict": self._max_tokens,
                },
            )
        except Exception as e:
            logger.error("Ollama generate failed: %s", e)
            raise

        raw = response.get("response", "")
        cleaned = clean_r1_output_full(raw)

        return {
            "reasoning": cleaned["reasoning"],
            "answer": cleaned["answer"],
            "raw": raw,
            "model": self._model,
            "usage": {
                "total_duration_ns": response.get("total_duration", 0),
                "eval_count": response.get("eval_count", 0),
            },
        }

    def rag_query(
        self,
        question: str,
        context: str,
    ) -> dict:
        """Run a RAG query with retrieved context.

        Args:
            question: The user's question.
            context: Retrieved document chunks assembled as a single string.

        Returns:
            Same dict structure as generate().
        """
        prompt = RAG_PROMPT_TEMPLATE.format(
            system_prompt=SYSTEM_PROMPT,
            context=context,
            question=question,
        )
        return self.generate(prompt, system="")


_client: Optional[OllamaClient] = None


def get_client() -> OllamaClient:
    """Return a singleton OllamaClient configured from environment."""
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client
