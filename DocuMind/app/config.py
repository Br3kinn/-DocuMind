"""Configurações centralizadas (lidas do .env)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # --- Gemini ---
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    thinking_level: str = os.getenv("THINKING_LEVEL", "low")
    thinking_budget: int = int(os.getenv("THINKING_BUDGET", "0"))
    max_output_tokens: int = int(os.getenv("MAX_OUTPUT_TOKENS", "1500"))
    request_timeout_ms: int = int(os.getenv("REQUEST_TIMEOUT_MS", "60000"))
    fallback_models: tuple = tuple(
        m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()
    )

    # --- Upload ---
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "30"))
    max_docs: int = 20  # documentos mantidos em memória (LRU)

    # --- Chunking / recuperação ---
    chunk_size: int = 1100        # caracteres por chunk (~250 tokens)
    chunk_overlap: int = 180      # sobreposição entre chunks consecutivos
    top_k: int = 7                # trechos enviados ao Gemini em perguntas pontuais
    broad_budget_chars: int = 24000  # orçamento p/ resumos e visão geral
    max_history_turns: int = 6


settings = Settings()
