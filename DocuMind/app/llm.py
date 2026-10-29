"""Cliente assíncrono do Gemini com streaming, retry e modelo de reserva."""
import asyncio
import logging
from collections.abc import AsyncIterator

import httpx
from google import genai
from google.genai import types

from .config import settings
from .prompts import SYSTEM_PROMPT

log = logging.getLogger("documind")
RETRYABLE = {429, 500, 503, 504}


def _retryable(e: Exception) -> bool:
    return getattr(e, "code", None) in RETRYABLE or isinstance(e, httpx.TimeoutException)


def _thinking(model: str):
    if model.startswith("gemini-3"):
        return types.ThinkingConfig(thinking_level=settings.thinking_level)
    if "flash" in model:  # família 2.5 (legado)
        return types.ThinkingConfig(thinking_budget=settings.thinking_budget)
    return None


class GeminiService:
    def __init__(self) -> None:
        self.client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=settings.request_timeout_ms),
        )

    def _config(self, model: str, **extra) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
            top_p=0.9,
            max_output_tokens=settings.max_output_tokens,
            thinking_config=_thinking(model),
            **extra,
        )

    async def warmup(self) -> None:
        try:
            await self.client.aio.models.generate_content(
                model=settings.gemini_model, contents="ok",
                config=types.GenerateContentConfig(
                    max_output_tokens=1, thinking_config=_thinking(settings.gemini_model)),
            )
        except Exception:
            pass

    async def aclose(self) -> None:
        try:
            await self.client.aio.aclose()
        except Exception:
            pass

    @staticmethod
    def _contents(question: str, context: str, history: list[tuple[str, str]]) -> list[types.Content]:
        turns = history[-settings.max_history_turns:]
        while turns and turns[0][0] != "user":
            turns = turns[1:]
        contents = [
            types.Content(role="user" if r == "user" else "model",
                          parts=[types.Part.from_text(text=t[:1500])])
            for r, t in turns
        ]
        prompt = (f"<contexto_do_documento>\n{context}\n</contexto_do_documento>\n\n"
                  f"<pergunta_do_estudante>\n{question}\n</pergunta_do_estudante>")
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=prompt)]))
        return contents

    async def stream_answer(self, question: str, context: str,
                            history: list[tuple[str, str]]) -> AsyncIterator[str]:
        contents = self._contents(question, context, history)
        models = [settings.gemini_model, settings.gemini_model, *settings.fallback_models]
        last: Exception | None = None
        for attempt, model in enumerate(models):
            got = False
            try:
                stream = await self.client.aio.models.generate_content_stream(
                    model=model, contents=contents, config=self._config(model))
                async for chunk in stream:
                    if chunk.text:
                        got = True
                        yield chunk.text
                if attempt:
                    log.info("Respondido por %s (tentativa %d)", model, attempt + 1)
                return
            except Exception as e:  # noqa: BLE001
                if got or not _retryable(e):
                    raise  # já enviou texto, ou erro definitivo (chave, modelo, etc.)
                last = e
                log.warning("Falha em %s (%s); tentando novamente…", model, type(e).__name__)
                await asyncio.sleep(0.5)
        raise last