# diag3.py
import asyncio, os, time
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
c = genai.Client(api_key=os.getenv("GEMINI_API_KEY"),
                 http_options=types.HttpOptions(timeout=20000))
CANDIDATOS = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3.5-flash",
              "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash"]
cfg = types.GenerateContentConfig(
    max_output_tokens=200,
    thinking_config=types.ThinkingConfig(thinking_level="low"))

async def medir(m):
    t = time.perf_counter(); ttft = None
    try:
        s = await c.aio.models.generate_content_stream(
            model=m, contents="Explique em 3 frases o que é um chunk em RAG.", config=cfg)
        async for ch in s:
            if ch.text and ttft is None:
                ttft = time.perf_counter() - t
        return f"OK   {m:24} 1º token {ttft:.2f}s | total {time.perf_counter()-t:.2f}s"
    except Exception as e:
        return f"ERRO {m:24} {type(e).__name__} {str(e)[:70]} | {time.perf_counter()-t:.2f}s"

async def main():
    for linha in await asyncio.gather(*(medir(m) for m in CANDIDATOS)):
        print(linha)

asyncio.run(main())