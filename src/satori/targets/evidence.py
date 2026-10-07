from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from satori.errors import ComponentBlocked


@dataclass(slots=True)
class SourceDocument:
    document_id: str
    source: str
    title: str
    text: str
    url: str
    published_at: str | None = None
    target_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class RetrievedEvidence:
    document: SourceDocument
    score: float
    retrieval_method: str


class EvidenceRetriever(Protocol):
    def retrieve(self, query: str, *, target_id: str | None = None,
                 limit: int = 10) -> list[RetrievedEvidence]: ...


class GraphRetriever:
    """Deterministic provenance-preserving retrieval over already-ingested evidence records."""

    def __init__(self, documents: list[SourceDocument]):
        self.documents = documents

    def retrieve(self, query: str, *, target_id: str | None = None,
                 limit: int = 10) -> list[RetrievedEvidence]:
        terms = {term.casefold() for term in query.split() if len(term) > 2}
        results: list[RetrievedEvidence] = []
        for document in self.documents:
            if target_id and document.target_ids and target_id not in document.target_ids:
                continue
            haystack = f"{document.title} {document.text}".casefold()
            overlap = sum(term in haystack for term in terms)
            if overlap:
                results.append(RetrievedEvidence(document, overlap / max(1, len(terms)), "graph/evidence lexical"))
        return sorted(results, key=lambda row: row.score, reverse=True)[:limit]


class VectorRetriever:
    """Adapter contract for a licensed embedding model/index; no fake vector scores."""

    def __init__(self, backend: EvidenceRetriever | None = None):
        self.backend = backend

    def retrieve(self, query: str, *, target_id: str | None = None,
                 limit: int = 10) -> list[RetrievedEvidence]:
        if self.backend is None:
            raise ComponentBlocked("Vector retrieval blocked: no embedding checkpoint/index is configured.")
        rows = self.backend.retrieve(query, target_id=target_id, limit=limit)
        for row in rows:
            row.retrieval_method = "vector"
        return rows


class SentenceTransformerRetriever:
    """Embedding retrieval adapter; defaults to the model already cached on this workstation."""

    def __init__(self, documents: list[SourceDocument],
                 model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
                 revision: str = "c9745ed1d9f207416be6d2e6f8de32d1f16199bf"):
        self.documents = documents
        self.model_name = model_name
        self.revision = revision
        self._model = None
        self._embeddings = None

    def _load(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            from satori.errors import DependencyUnavailable
            raise DependencyUnavailable("Embedding retrieval requires the [retrieval] extra.") from exc
        self._model = SentenceTransformer(self.model_name, revision=self.revision)
        texts = [f"{doc.title}\n{doc.text}" for doc in self.documents]
        self._embeddings = self._model.encode(texts, normalize_embeddings=True,
                                              convert_to_tensor=True, show_progress_bar=False)

    def retrieve(self, query: str, *, target_id: str | None = None,
                 limit: int = 10) -> list[RetrievedEvidence]:
        if self._model is None:
            self._load()
        import torch
        query_vector = self._model.encode(query, normalize_embeddings=True, convert_to_tensor=True)
        scores = self._embeddings @ query_vector
        order = torch.argsort(scores, descending=True).tolist()
        results: list[RetrievedEvidence] = []
        for index in order:
            document = self.documents[index]
            if target_id and document.target_ids and target_id not in document.target_ids:
                continue
            results.append(RetrievedEvidence(document, float(scores[index]), "sentence-transformer vector"))
            if len(results) == limit:
                break
        return results


class MultiHopEvidenceReasoner:
    """LLM-backed evidence synthesis contract; preserves citations and exposes model blocker."""

    def __init__(self, provider: object | None = None):
        self.provider = provider

    def reason(self, query: str, evidence: list[RetrievedEvidence]) -> dict[str, object]:
        if self.provider is None:
            raise ComponentBlocked("Multi-hop RAG blocked: no approved LLM checkpoint/provider is configured.")
        response = self.provider.reason(query=query, evidence=evidence)  # type: ignore[attr-defined]
        return {"answer": response, "citations": [
            {"document_id": row.document.document_id, "source": row.document.source,
             "url": row.document.url, "score": row.score} for row in evidence]}
