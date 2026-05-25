"""Configuration management for Semiconductor RAG QA System.

All settings can be overridden via environment variables or .env file.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


# Ollama
OLLAMA_BASE_URL: str = _env("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = _env("OLLAMA_MODEL", "deepseek-r1:8b")

# ChromaDB
CHROMA_PERSIST_DIR: str = _env("CHROMA_PERSIST_DIR", "./chroma_db")
CHROMA_COLLECTION_NAME: str = _env("CHROMA_COLLECTION_NAME", "semiconductor_docs")

# Document Processing
CHUNK_SIZE: int = int(_env("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP: int = int(_env("CHUNK_OVERLAP", "200"))

# Retrieval
TOP_K: int = int(_env("TOP_K", "5"))
SIMILARITY_THRESHOLD: float = float(_env("SIMILARITY_THRESHOLD", "0.3"))

# Generation
MAX_TOKENS: int = int(_env("MAX_TOKENS", "2048"))
TEMPERATURE: float = float(_env("TEMPERATURE", "0.1"))

# Logging
LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")
