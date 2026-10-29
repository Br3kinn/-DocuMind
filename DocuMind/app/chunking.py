"""Chunking consciente da estrutura acadêmica (página + seção)."""
import re
from dataclasses import dataclass

from .config import settings
from .pdf_processing import Page


@dataclass(slots=True)
class Chunk:
    id: int
    page: int
    section: str
    text: str

    @property
    def index_text(self) -> str:
        # a seção entra no índice: perguntas como "metodologia" encontram a seção certa
        return f"{self.section} {self.text}"


_KNOWN = re.compile(
    r"^(?:\d{1,2}(?:\.\d{1,2})*\.?\s*)?"
    r"(resumo|abstract|resumen|introdu[cç][aã]o|introduction|"
    r"revis[aã]o (?:da |de )?literatura|referencial te[oó]rico|fundamenta[cç][aã]o te[oó]rica|"
    r"metodologia|materiais e m[eé]todos|m[eé]todos|methods|methodology|"
    r"resultados(?: e discuss[aã]o)?|results|discuss[aã]o|discussion|"
    r"considera[cç][oõ]es finais|conclus[aã]o|conclus[oõ]es|conclusions?|"
    r"refer[eê]ncias(?: bibliogr[aá]ficas)?|references|bibliografia|agradecimentos|"
    r"ap[eê]ndices?|anexos?)\.?\s*$",
    re.I,
)
_NUMBERED = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,3}\.?\s+(\S.*)$")


def is_heading(line: str) -> bool:
    s = line.strip()
    if not 3 <= len(s) <= 100:
        return False
    if _KNOWN.match(s):
        return True
    letters = sum(c.isalpha() for c in s)
    if letters < 4 or s.endswith((".", ",", ";", ":")):
        return False
    m = _NUMBERED.match(s)
    if m and m.group(1)[0].isupper() and len(s) <= 90 and s.count(" ") <= 12:
        return True
    return s.isupper() and len(s) <= 80


def _tail(text: str, overlap: int) -> str:
    if len(text) <= overlap:
        return text
    t = text[-overlap:]
    i = t.find(" ")
    return t[i + 1:] if i >= 0 else t


def chunk_pages(pages: list[Page], size: int | None = None, overlap: int | None = None) -> list[Chunk]:
    size = size or settings.chunk_size
    overlap = overlap if overlap is not None else settings.chunk_overlap
    chunks: list[Chunk] = []
    section = "Início do documento"

    def emit(page: int, sec: str, lines: list[str]) -> None:
        text = " ".join(lines).strip()
        if len(text) >= 30:
            chunks.append(Chunk(len(chunks), page, sec, text))

    for page in pages:
        buf: list[str] = []
        n = 0
        fresh = 0  # linhas novas desde o último flush (evita chunk só de overlap)
        for raw in page.text.split("\n"):
            line = raw.strip()
            if not line:
                continue
            if is_heading(line):
                if fresh:
                    emit(page.number, section, buf)
                section = line[:80]
                buf, n, fresh = [line], len(line), 1
                continue
            buf.append(line)
            n += len(line) + 1
            fresh += 1
            ends_sentence = line.endswith((".", "!", "?", ":", ";"))
            if (n >= size and ends_sentence) or n >= size * 1.3:
                emit(page.number, section, buf)
                tail = _tail(" ".join(buf), overlap)
                buf, n, fresh = ([tail] if tail else []), len(tail), 0
        if fresh:
            emit(page.number, section, buf)
    return chunks
