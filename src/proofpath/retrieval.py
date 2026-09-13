"""BM25 retrieval over page-anchored chunks.

Deliberately dependency-free. A hackathon demo must not need an embedding
service or a vector database to answer a question about one uploaded PDF, and a
lexical index is the right tool when the user's wording largely matches the
document's wording (policy text is quoted, not paraphrased).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from . import config
from .errors import EmptyIndexError
from .models import Chunk, Document
from .text import tokenize


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A retrieval hit."""

    chunk: Chunk
    score: float


class Bm25Index:
    """Immutable BM25 index built once per document."""

    __slots__ = ("_chunks", "_term_freqs", "_doc_lengths", "_avg_length", "_idf")

    def __init__(self, chunks: tuple[Chunk, ...]) -> None:
        if not chunks:
            raise EmptyIndexError("cannot build an index over zero chunks")

        self._chunks = chunks
        self._term_freqs: tuple[Counter[str], ...] = tuple(
            Counter(tokenize(chunk.text)) for chunk in chunks
        )
        self._doc_lengths: tuple[int, ...] = tuple(
            sum(freqs.values()) for freqs in self._term_freqs
        )
        total_length = sum(self._doc_lengths)
        self._avg_length = total_length / len(chunks) if total_length else 1.0

        doc_freq: Counter[str] = Counter()
        for freqs in self._term_freqs:
            doc_freq.update(freqs.keys())

        n_docs = len(chunks)
        # Probabilistic IDF with the +1 smoothing that keeps every weight
        # positive; the raw form can go negative for terms in >half the chunks,
        # which would make common terms actively harmful to a match.
        self._idf: dict[str, float] = {
            term: math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            for term, df in doc_freq.items()
        }

    @classmethod
    def from_document(cls, document: Document) -> Bm25Index:
        return cls(document.chunks)

    def __len__(self) -> int:
        return len(self._chunks)

    def _score_chunk(self, index: int, query_terms: Counter[str]) -> float:
        freqs = self._term_freqs[index]
        length = self._doc_lengths[index]
        norm = config.BM25_K1 * (
            1.0 - config.BM25_B + config.BM25_B * length / self._avg_length
        )

        score = 0.0
        for term, query_count in query_terms.items():
            tf = freqs.get(term, 0)
            if not tf:
                continue
            idf = self._idf.get(term, 0.0)
            score += query_count * idf * (tf * (config.BM25_K1 + 1.0)) / (tf + norm)
        return score

    def search(self, query: str, top_k: int = config.DEFAULT_TOP_K) -> tuple[ScoredChunk, ...]:
        """Top-k chunks for a query, best first. Zero-score hits are dropped."""
        if top_k <= 0:
            return ()

        query_terms = Counter(tokenize(query))
        if not query_terms:
            return ()

        scored = [
            ScoredChunk(chunk=self._chunks[i], score=self._score_chunk(i, query_terms))
            for i in range(len(self._chunks))
        ]
        hits = [item for item in scored if item.score > 0.0]
        # Tie-break by document order so output is deterministic across runs.
        hits.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
        return tuple(hits[:top_k])


def build_context(hits: tuple[ScoredChunk, ...], *, char_budget: int = 12_000) -> str:
    """Render hits as page-labelled context for a prompt.

    The page label is what lets the model cite a page at all, so it is part of
    the payload rather than metadata kept on the side.
    """
    parts: list[str] = []
    used = 0
    for hit in hits:
        block = f"[第 {hit.chunk.page} 页]\n{hit.chunk.text.strip()}"
        if used + len(block) > char_budget:
            break
        parts.append(block)
        used += len(block)
    return "\n\n---\n\n".join(parts)
