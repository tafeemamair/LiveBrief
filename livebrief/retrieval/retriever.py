"""Semantic and hybrid retrieval engine backed by Moss."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from livebrief.models.document import Chunk
from livebrief.models.query import QueryFilter, QueryRequest
from livebrief.moss.indexer import MossIndexer


class RetrievedCandidate(BaseModel):
    """Candidate chunk returned by Moss retrieval."""

    chunk: Chunk
    score: float
    rank: int


class RetrievalResult(BaseModel):
    """Aggregate search result from Moss retrieval."""

    query: str
    candidates: List[RetrievedCandidate] = Field(default_factory=list)
    latency_ms: float = 0.0
    total_docs_indexed: int = 0


class MossSemanticRetriever:
    """Orchestrates query execution and score formatting against Moss index."""

    def __init__(self, indexer: MossIndexer) -> None:
        self.indexer = indexer

    def retrieve(self, request: QueryRequest) -> RetrievalResult:
        """Execute semantic and hybrid retrieval against the Moss index."""
        t0 = time.perf_counter()

        # Build Moss filter dict if filters are provided
        moss_filter: Optional[Dict[str, Any]] = None
        if request.filters:
            if len(request.filters) == 1:
                moss_filter = request.filters[0].to_moss_dict()
            else:
                moss_filter = {
                    "$and": [f.to_moss_dict() for f in request.filters]
                }

        # Perform native Moss query
        search_result = self.indexer.query(
            query_text=request.query,
            top_k=request.top_k,
            alpha=request.alpha,
            filter_dict=moss_filter,
        )

        latency_ms = (time.perf_counter() - t0) * 1000.0

        candidates: List[RetrievedCandidate] = []
        for rank, doc in enumerate(search_result.docs):
            chunk = self.indexer.get_chunk(doc.id)
            if chunk is None:
                # Reconstruct chunk from returned Moss doc info
                chunk = Chunk.create(
                    doc_id=doc.metadata.get("doc_id", doc.id),
                    text=doc.text,
                    chunk_index=int(doc.metadata.get("chunk_index", 0)),
                    start_char=0,
                    end_char=len(doc.text),
                    metadata=doc.metadata,
                )

            # Filter candidates below minimum threshold if desired
            if doc.score >= request.min_relevance_threshold:
                candidates.append(
                    RetrievedCandidate(
                        chunk=chunk,
                        score=float(doc.score),
                        rank=rank + 1,
                    )
                )

        return RetrievalResult(
            query=request.query,
            candidates=candidates,
            latency_ms=latency_ms,
            total_docs_indexed=self.indexer.doc_count,
        )
