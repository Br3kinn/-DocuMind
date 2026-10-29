"""DocuMind — API FastAPI (upload de PDF, RAG e chat em streaming)."""
import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .chunking import chunk_pages
from .config import settings
from .llm import GeminiService
from .pdf_processing import extract_pages
from .retriever import BM25Index, format_context, select_context
from .store import DocumentStore, StudyDocument

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("documind")

BASE_DIR = Path(__file__).resolve().parent.parent
store = DocumentStore(settings.max_docs)
state: dict[str, GeminiService] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.gemini_api_key:
        raise RuntimeError("Defina GEMINI_API_KEY no arquivo .env")
    llm = GeminiService()
    state["llm"] = llm
    warm = asyncio.create_task(llm.warmup())  # não bloqueia o startup
    yield
    warm.cancel()
    await llm.aclose()


app = FastAPI(title="DocuMind", lifespan=lifespan)


# ------------------------------------------------------------------ modelos
class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=6000)


class ChatRequest(BaseModel):
    doc_id: str
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = []


# ------------------------------------------------------------------ ingestão
def ingest(data: bytes, filename: str) -> tuple[StudyDocument, str | None]:
    """Roda em thread (CPU-bound): extração -> chunking -> índice BM25."""
    pages = extract_pages(data)
    total = sum(len(p.text) for p in pages)
    if total == 0:
        raise ValueError("Nenhum texto extraível. O PDF parece ser escaneado (imagem); use uma versão com OCR.")
    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError("Não foi possível gerar trechos a partir do PDF.")
    index = BM25Index([c.index_text for c in chunks])
    warning = None
    if total / len(pages) < 200:
        warning = "Pouco texto por página: partes do PDF podem ser imagens/escaneadas e ficarão fora das respostas."
    doc = StudyDocument(uuid.uuid4().hex[:12], filename, len(pages), total, chunks, index)
    return doc, warning


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)):
    t0 = time.perf_counter()
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Arquivo maior que {settings.max_upload_mb} MB.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(415, "Envie um arquivo PDF válido.")
    try:
        doc, warning = await asyncio.to_thread(ingest, data, file.filename or "documento.pdf")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception:
        log.exception("Falha ao processar PDF")
        raise HTTPException(400, "Não foi possível ler o PDF (arquivo corrompido?).")
    store.add(doc)
    elapsed = time.perf_counter() - t0
    log.info("PDF %s: %d págs, %d chunks em %.2fs", doc.filename, doc.pages, len(doc.chunks), elapsed)
    return {
        "id": doc.id, "filename": doc.filename, "pages": doc.pages, "chunks": len(doc.chunks),
        "chars": doc.chars, "warning": warning, "elapsed": round(elapsed, 2),
    }


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    return {"deleted": store.delete(doc_id)}


# ------------------------------------------------------------------ chat (streaming NDJSON)
def _line(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode()


@app.post("/api/chat")
async def chat(req: ChatRequest):
    t0 = time.perf_counter()  # ⏱️ começa assim que a pergunta chega
    doc = store.get(req.doc_id)
    if not doc:
        raise HTTPException(404, "Documento não encontrado. Envie o PDF novamente.")

    prev_q = next((t.content for t in reversed(req.history) if t.role == "user"), None)
    chunks, mode = select_context(doc.index, doc.chunks, req.question, prev_q)
    context = format_context(chunks)
    history = [(t.role, t.content) for t in req.history]
    sources = [
        {"page": c.page, "section": c.section, "preview": c.text[:160]} for c in chunks
    ]
    t_retrieval = time.perf_counter() - t0

    async def stream():
        ttft: float | None = None
        got_text = False
        yield _line({"type": "sources", "mode": mode, "sources": sources})
        try:
            async for piece in state["llm"].stream_answer(req.question, context, history):
                if ttft is None:
                    ttft = time.perf_counter() - t0
                got_text = True
                yield _line({"type": "token", "text": piece})
        except Exception as e:  # noqa: BLE001
            log.exception("Erro no Gemini")
            yield _line({"type": "error", "message": f"Falha ao consultar o Gemini: {str(e)[:200]}"})
        if not got_text:
            yield _line({"type": "error", "message": "O modelo não retornou texto (resposta bloqueada ou vazia)."})
        elapsed = time.perf_counter() - t0  # ⏱️ fim da geração
        log.info("chat: retrieval=%.0fms ttft=%s total=%.2fs", t_retrieval * 1000,
                 f"{ttft:.2f}s" if ttft else "-", elapsed)
        yield _line({
            "type": "done",
            "elapsed": round(elapsed, 2),
            "ttft": round(ttft, 2) if ttft else None,
            "retrieval_ms": round(t_retrieval * 1000),
        })

    return StreamingResponse(
        stream(), media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": settings.gemini_model}


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "frontend" / "index.html")
