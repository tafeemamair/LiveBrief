"""LiveBrief end-to-end pipeline connecting ingestion, Moss indexing, retrieval, evidence selection, and synthesis."""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Union
from livebrief.evidence.selector import EvidenceSelector
from livebrief.ingestion.pipeline import IngestionPipeline
from livebrief.models.document import Chunk, Document
from livebrief.models.query import QueryRequest
from livebrief.models.response import LiveBriefResponse
from livebrief.moss.embedder import BaseEmbedder, DeterministicEmbedder
from livebrief.moss.indexer import MossIndexer
from livebrief.retrieval.retriever import MossSemanticRetriever
from livebrief.synthesis.grounder import GroundedSynthesizer
from livebrief.telemetry.latency import LatencyTracker


class LiveBriefPipeline:
    """
    Primary Phase 1 orchestrator for LiveBrief.
    Executes Document Ingestion → Moss Indexing → Semantic Retrieval → Evidence Selection → Structured Grounded Brief.
    """

    def __init__(
        self,
        index_name: str = "livebrief_primary",
        model_id: str = "moss-minilm",
        embedder: Optional[BaseEmbedder] = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        diversity_lambda: float = 0.7,
    ) -> None:
        self.embedder = embedder or DeterministicEmbedder(dimension=384)
        self.ingestion = IngestionPipeline(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.indexer = MossIndexer(index_name=index_name, model_id=model_id, embedder=self.embedder)
        self.retriever = MossSemanticRetriever(self.indexer)
        self.selector = EvidenceSelector(diversity_lambda=diversity_lambda)
        self.synthesizer = GroundedSynthesizer()

    def ingest_and_index_files(
        self,
        paths: List[Union[str, Path]],
        tracker: Optional[LatencyTracker] = None,
    ) -> int:
        """Ingest files from disk and index into Moss."""
        local_tracker = tracker or LatencyTracker()

        with local_tracker.measure("ingestion"):
            documents, chunks = self.ingestion.ingest_files(paths)

        with local_tracker.measure("indexing"):
            added, updated = self.indexer.add_chunks(chunks)

        return added + updated

    def ingest_and_index_text(
        self,
        text: str,
        doc_id: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[dict] = None,
        tracker: Optional[LatencyTracker] = None,
    ) -> int:
        """Ingest raw text and index into Moss."""
        local_tracker = tracker or LatencyTracker()

        with local_tracker.measure("ingestion"):
            doc, chunks = self.ingestion.ingest_text(text, doc_id=doc_id, title=title, metadata=metadata)

        with local_tracker.measure("indexing"):
            added, updated = self.indexer.add_chunks(chunks)

        return added + updated

    def query(
        self,
        request: Union[str, QueryRequest],
        tracker: Optional[LatencyTracker] = None,
    ) -> LiveBriefResponse:
        """
        Execute full retrieval, evidence selection, and grounded briefing pipeline.
        Instruments latency at each step with sub-millisecond precision.
        """
        t0 = time.perf_counter()
        active_tracker = tracker or LatencyTracker()

        req = request if isinstance(request, QueryRequest) else QueryRequest(query=request)

        # 1. Moss Semantic & Hybrid Retrieval
        with active_tracker.measure("moss_retrieval"):
            retrieval_res = self.retriever.retrieve(req)

        # 2. Evidence Selection & MMR Deduplication
        with active_tracker.measure("evidence_selection"):
            evidence_res = self.selector.select_evidence(
                retrieval=retrieval_res,
                max_tokens=req.max_evidence_tokens,
                max_items=req.top_k,
            )

        # 3. Grounded Synthesis
        total_so_far = (time.perf_counter() - t0) * 1000.0
        breakdown = active_tracker.get_breakdown(total_elapsed_ms=total_so_far)

        with active_tracker.measure("synthesis"):
            response = self.synthesizer.synthesize(
                query=req.query,
                evidence=evidence_res,
                latency=breakdown,
            )

        total_elapsed = (time.perf_counter() - t0) * 1000.0
        final_breakdown = active_tracker.get_breakdown(total_elapsed_ms=total_elapsed)
        response.latency = final_breakdown

        return response
