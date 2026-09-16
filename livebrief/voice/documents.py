"""In-memory Document Registry and knowledge document lifecycle management for LiveBrief Phase 2.3."""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from livebrief.ingestion.pipeline import IngestionPipeline
from livebrief.models.document import Chunk, Document
from livebrief.moss.indexer import MossIndexer
from livebrief.pipeline import LiveBriefPipeline


class DocumentRecord(BaseModel):
    """Document metadata and associated indexed chunk tracking."""

    doc_id: str
    title: str
    source_format: str  # "markdown" | "json" | "text"
    chunk_count: int
    total_characters: int
    indexed_at_ms: float = Field(default_factory=lambda: time.time() * 1000.0)
    status: str = "INDEXED"  # "INDEXED" | "FAILED"
    chunk_ids: List[str] = Field(default_factory=list)


class DocumentRegistry:
    """
    In-memory Document Registry for managing document-level lifecycle and metadata.
    Coordinates document ingestion, chunk tracking, and deterministic deletion with MossIndexer.
    """

    def __init__(
        self,
        pipeline: Optional[LiveBriefPipeline] = None,
        indexer: Optional[MossIndexer] = None,
        ingestion: Optional[IngestionPipeline] = None,
    ) -> None:
        if pipeline:
            self.indexer = pipeline.indexer
            self.ingestion = pipeline.ingestion
        else:
            self.indexer = indexer
            self.ingestion = ingestion or IngestionPipeline()
        self._documents: Dict[str, DocumentRecord] = {}

    @property
    def total_documents(self) -> int:
        """Total number of registered documents."""
        return len(self._documents)

    @property
    def total_chunks(self) -> int:
        """Total number of registered chunks across all documents."""
        return sum(doc.chunk_count for doc in self._documents.values())

    def list_documents(self) -> List[DocumentRecord]:
        """Return all registered documents in chronological order."""
        return list(self._documents.values())

    def get_document(self, doc_id: str) -> Optional[DocumentRecord]:
        """Retrieve a registered document record by ID."""
        return self._documents.get(doc_id)

    def ingest_document(
        self,
        content: str,
        title: Optional[str] = None,
        doc_id: Optional[str] = None,
        format: str = "markdown",
    ) -> DocumentRecord:
        """
        Ingest, parse, chunk, and index a document into the native Moss index.
        
        Supported formats:
        - "markdown" / "md"
        - "text" / "txt"
        - "json" (deterministic sorted keys, 2-space indentation)
        
        Raises:
            ValueError: If format is unsupported, JSON is malformed, or content is empty.
        """
        if not content or not content.strip():
            raise ValueError("Document content cannot be empty")

        norm_format = format.lower().strip()
        if norm_format in ("markdown", "md"):
            canonical_format = "markdown"
            text_to_chunk = content.strip()
            extracted_title = title
        elif norm_format in ("text", "txt", "plain"):
            canonical_format = "text"
            text_to_chunk = content.strip()
            extracted_title = title
        elif norm_format == "json":
            canonical_format = "json"
            try:
                parsed_json = json.loads(content)
            except Exception as e:
                raise ValueError(f"Invalid JSON document syntax: {e}") from e

            # Deterministic serialization with sorted keys, 2-space indentation, ensure_ascii=False
            text_to_chunk = json.dumps(parsed_json, sort_keys=True, indent=2, ensure_ascii=False)
            
            # Extract title if present in top-level JSON object
            extracted_title = title
            if not extracted_title and isinstance(parsed_json, dict):
                extracted_title = parsed_json.get("title") or parsed_json.get("name")
        else:
            raise ValueError(f"Unsupported document format '{format}'. Supported formats: markdown, text, json")

        # Determine final document ID and Title
        final_doc_id = doc_id or (
            re.sub(r"[^a-zA-Z0-9_-]", "_", extracted_title.lower()).strip("_")
            if extracted_title
            else f"doc_{uuid.uuid4().hex[:8]}"
        )
        if not final_doc_id:
            final_doc_id = f"doc_{uuid.uuid4().hex[:8]}"

        final_title = extracted_title or title or final_doc_id

        # If re-indexing an existing doc_id, cleanly delete previous chunks first
        if final_doc_id in self._documents:
            self.delete_document(final_doc_id)

        # Chunk document using existing IngestionPipeline
        if not self.ingestion or not self.indexer:
            raise RuntimeError("DocumentRegistry is not attached to an active IngestionPipeline or MossIndexer")

        doc, chunks = self.ingestion.ingest_text(
            text=text_to_chunk,
            doc_id=final_doc_id,
            title=final_title,
            metadata={"format": canonical_format},
        )

        if not chunks:
            raise ValueError("Document parsing produced zero indexed chunks")

        # Index chunks into MossIndexer
        try:
            added, updated = self.indexer.add_chunks(chunks)
        except Exception as e:
            raise RuntimeError(f"Moss indexing failed: {e}") from e

        chunk_ids = [c.id for c in chunks]

        record = DocumentRecord(
            doc_id=final_doc_id,
            title=final_title,
            source_format=canonical_format,
            chunk_count=len(chunks),
            total_characters=len(text_to_chunk),
            indexed_at_ms=time.time() * 1000.0,
            status="INDEXED",
            chunk_ids=chunk_ids,
        )

        self._documents[final_doc_id] = record
        return record

    def register_existing_chunks(
        self,
        doc_id: str,
        title: str,
        chunks: List[Chunk],
        source_format: str = "markdown",
    ) -> DocumentRecord:
        """Register document metadata for chunks that are already indexed."""
        chunk_ids = [c.id for c in chunks]
        total_chars = sum(len(c.text) for c in chunks)
        record = DocumentRecord(
            doc_id=doc_id,
            title=title,
            source_format=source_format,
            chunk_count=len(chunks),
            total_characters=total_chars,
            indexed_at_ms=time.time() * 1000.0,
            status="INDEXED",
            chunk_ids=chunk_ids,
        )
        self._documents[doc_id] = record
        return record

    def delete_document(self, doc_id: str) -> bool:
        """
        Deterministically delete a document and all its indexed chunks from Moss.
        
        Flow:
        DocumentRegistry lookup -> record.chunk_ids -> MossIndexer.delete_chunks() -> remove from registry.
        """
        record = self._documents.get(doc_id)
        if not record:
            return False

        if self.indexer and record.chunk_ids:
            self.indexer.delete_chunks(record.chunk_ids)

        del self._documents[doc_id]
        return True

    def clear(self) -> None:
        """Clear all registered documents and remove their chunks from Moss."""
        for doc_id in list(self._documents.keys()):
            self.delete_document(doc_id)
        self._documents.clear()
