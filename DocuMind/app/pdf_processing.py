"""Extração rápida e limpeza de texto de PDFs (PyMuPDF)."""
import re
from collections import Counter
from dataclasses import dataclass

import pymupdf  # PyMuPDF


@dataclass(slots=True)
class Page:
    number: int
    text: str


def extract_pages(data: bytes) -> list[Page]:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        if doc.needs_pass:
            raise ValueError("O PDF está protegido por senha.")
        raw = [(i, p.get_text("text")) for i, p in enumerate(doc, start=1)]
    finally:
        doc.close()

    cleaned = [Page(i, _normalize(t)) for i, t in raw]
    return _drop_running_headers(cleaned)


def _normalize(text: str) -> str:
    text = text.replace("\u00ad", "")                      # hífen suave
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)           # palavra hifenizada na quebra de linha
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _line_key(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip().lower())


def _drop_running_headers(pages: list[Page]) -> list[Page]:
    """Remove cabeçalhos/rodapés repetidos e numeração de página."""
    n = len(pages)
    if n < 5:
        return pages
    counter: Counter[str] = Counter()
    for p in pages:
        counter.update({_line_key(l) for l in p.text.split("\n") if l.strip()})
    noisy = {k for k, c in counter.items() if c / n >= 0.4 and len(k) < 120}
    for p in pages:
        kept = [l for l in p.text.split("\n") if _line_key(l) not in noisy]
        p.text = "\n".join(kept)
    return pages
