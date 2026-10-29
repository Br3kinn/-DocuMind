"""Recuperação lexical BM25 (sem chamadas de rede => ~ms de latência)."""
import heapq
import math
import re
import unicodedata
from collections import Counter, defaultdict

from .chunking import Chunk
from .config import settings


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


_STOP = {_norm(w) for w in """
a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sob sobre entre
ate e ou mas que se como ao aos é ser foi são sua seu suas seus este esta estes estas isso isto
esse essa pelo pela pelos pelas qual quais quando onde quem mais menos muito muita já também não
the of and to in is are for on with as by an be this that from at or it its was were which
""".split()}
_TOKEN = re.compile(r"[a-z0-9]+")
_STEM = 7  # truncamento simples: "metodologia"/"metodológico" -> "metodol"


def tokenize(text: str) -> list[str]:
    return [t[:_STEM] for t in _TOKEN.findall(_norm(text)) if len(t) > 1 and t not in _STOP]


class BM25Index:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.lens: list[int] = []
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, d in enumerate(docs):
            tf = Counter(tokenize(d))
            self.lens.append(sum(tf.values()))
            for t, f in tf.items():
                self.postings[t].append((i, f))
        n = len(docs)
        self.avg = (sum(self.lens) / n) if n else 1.0
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for t in set(tokenize(query)):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i, f in self.postings[t]:
                denom = f + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg)
                scores[i] += idf * f * (self.k1 + 1) / denom
        return heapq.nlargest(top_k, scores.items(), key=lambda x: x[1])


# ---------------------------------------------------------------- seleção de contexto
_BROAD = re.compile(
    r"\b(resum\w*|sintetiz\w*|vis[aã]o geral|panorama|sobre o que|do que (?:se )?trata|"
    r"principais (?:pontos|ideias|conclus\w+|contribui\w+)|overview|summar\w+|tl;?dr|"
    r"pontos[- ]chave|ideia central|tema central|mapa mental|perguntas de revis\w+|"
    r"flashcards?|quest[oõ]es de estudo|conceitos[- ]chave)\b",
    re.I,
)
_PRIORITY = re.compile(r"resumo|abstract|introdu|conclus|considera|resultado|discuss", re.I)
_REFS = re.compile(r"refer[eê]ncias|references|bibliografia", re.I)


def select_broad(chunks: list[Chunk], budget: int) -> list[Chunk]:
    """Cobertura do documento todo: seções-chave primeiro, depois amostragem uniforme."""
    pool = [c for c in chunks if not _REFS.search(c.section)] or chunks
    if sum(len(c.text) for c in pool) <= budget:
        return pool
    chosen: dict[int, Chunk] = {}
    used = 0
    for c in pool:
        if _PRIORITY.search(c.section) and used + len(c.text) <= budget * 0.6:
            chosen[c.id] = c
            used += len(c.text)
    rest = [c for c in pool if c.id not in chosen]
    if rest:
        avg = sum(len(c.text) for c in rest) / len(rest)
        slots = max(1, int((budget - used) // avg))
        step = max(1, math.ceil(len(rest) / slots))
        for c in rest[::step]:
            if used + len(c.text) > budget:
                break
            chosen[c.id] = c
            used += len(c.text)
    return sorted(chosen.values(), key=lambda c: c.id)


def select_context(
    index: BM25Index, chunks: list[Chunk], question: str, prev_question: str | None = None
) -> tuple[list[Chunk], str]:
    if _BROAD.search(question):
        return select_broad(chunks, settings.broad_budget_chars), "visao_geral"
    # follow-up curto ("e a amostra?") herda o tema da pergunta anterior
    q = f"{prev_question} {question}" if prev_question and len(question.split()) <= 6 else question
    hits = index.search(q, settings.top_k)
    if not hits:
        return select_broad(chunks, settings.broad_budget_chars), "visao_geral"
    picked = sorted((chunks[i] for i, _ in hits), key=lambda c: c.id)  # ordem do documento
    return picked, "busca"


def format_context(chunks: list[Chunk]) -> str:
    return "\n\n".join(
        f"[Trecho {i} | p. {c.page} | Seção: {c.section}]\n{c.text}" for i, c in enumerate(chunks, 1)
    )
