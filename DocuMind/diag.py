# diag2.py
import asyncio, os, time
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
c = genai.Client(api_key=os.getenv("GEMINI_API_KEY"),
                 http_options=types.HttpOptions(timeout=60000))

async def testar(modelo, cfg, rotulo):
    t = time.perf_counter()
    try:
        r = await c.aio.models.generate_content(model=modelo, contents="Diga: ok", config=cfg)
        print(f"OK   {modelo} [{rotulo}]: {r.text!r} em {time.perf_counter()-t:.2f}s")
    except Exception as e:
        print(f"ERRO {modelo} [{rotulo}]: {type(e).__name__} {str(e)[:120]} em {time.perf_counter()-t:.2f}s")

async def main():
    print("Modelos flash disponíveis para a sua chave:")
    async for m in await c.aio.models.list():
        if "flash" in m.name and "generateContent" in (m.supported_actions or []):
            print("  ", m.name)
    print()
    low = types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level="low"))
    await testar("gemini-3.8-flash", low, "thinking=low")
    await testar("gemini-3.8-flash", None, "padrão")

asyncio.run(main())