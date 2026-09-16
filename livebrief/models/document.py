"""Document and chunk data models for LiveBrief."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def compute_content_hash(text: str) -> str:
    """Generate deterministic SHA-256 hash prefix for content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Document(BaseModel):
    """Raw or parsed input document."""

    id: str
    content: str
    metadata: Dict[str, str] = Field(default_factory=dict)
    title: Optional[str] = None
    source_uri: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def create(
        cls,
        content: str,
        doc_id: Optional[str] = None,
        title: Optional[str] = None,
        source_uri: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "Document":
        cleaned_meta: Dict[str, str] = {}
        if metadata:
            for k, v in metadata.items():
                cleaned_meta[str(k)] = str(v)
        
        computed_id = doc_id or f"doc_{compute_content_hash(content)}"
        return cls(
            id=computed_id,
            content=content,
            metadata=cleaned_meta,
            title=title,
            source_uri=source_uri,
        )


class Chunk(BaseModel):
    """Atomic chunk unit indexed by Moss and used for evidence retrieval."""

    id: str
    doc_id: str
    text: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata: Dict[str, str] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None

    @classmethod
    def create(
        cls,
        doc_id: str,
        text: str,
        chunk_index: int,
        start_char: int,
        end_char: int,
        metadata: Optional[Dict[str, Any]] = None,
        embedding: Optional[List[float]] = None,
    ) -> "Chunk":
        chunk_hash = compute_content_hash(f"{doc_id}:{chunk_index}:{text}")
        chunk_id = f"{doc_id}_c{chunk_index}_{chunk_hash}"
        
        cleaned_meta: Dict[str, str] = {"doc_id": str(doc_id), "chunk_index": str(chunk_index)}
        if metadata:
            for k, v in metadata.items():
                cleaned_meta[str(k)] = str(v)

        return cls(
            id=chunk_id,
            doc_id=doc_id,
            text=text,
            chunk_index=chunk_index,
            start_char=start_char,
            end_char=end_char,
            metadata=cleaned_meta,
            embedding=embedding,
        )
