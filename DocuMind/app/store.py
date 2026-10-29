"""Armazenamento em memória (MVP) com política LRU."""
from collections import OrderedDict
from dataclasses import dataclass

from .chunking import Chunk
from .retriever import BM25Index


@dataclass(slots=True)
class StudyDocument:
    id: str
    filename: str
    pages: int
    chars: int
    chunks: list[Chunk]
    index: BM25Index


class DocumentStore:
    def __init__(self, max_docs: int = 20):
        self._docs: OrderedDict[str, StudyDocument] = OrderedDict()
        self._max = max_docs

    def add(self, doc: StudyDocument) -> None:
        self._docs[doc.id] = doc
        while len(self._docs) > self._max:
            self._docs.popitem(last=False)

    def get(self, doc_id: str) -> StudyDocument | None:
        doc = self._docs.get(doc_id)
        if doc:
            self._docs.move_to_end(doc_id)
        return doc

    def delete(self, doc_id: str) -> bool:
        return self._docs.pop(doc_id, None) is not None
