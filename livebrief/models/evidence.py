"""Evidence selection and span citation models."""

from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceSpan(BaseModel):
    """Fine-grained text excerpt extracted from a chunk."""

    text: str
    salience_score: float
    start_char: int
    end_char: int


class EvidenceItem(BaseModel):
    """Grounded evidence unit selected from retrieval results."""

    citation_id: int
    chunk_id: str
    doc_id: str
    text: str
    salient_spans: List[EvidenceSpan] = Field(default_factory=list)
    relevance_score: float
    diversity_score: float = 1.0
    final_score: float
    metadata: Dict[str, str] = Field(default_factory=dict)
    token_estimate: int = 0


class EvidenceSelectionResult(BaseModel):
    """Result of the evidence selection and deduplication process."""

    query: str
    items: List[EvidenceItem] = Field(default_factory=list)
    total_tokens: int = 0
    candidate_count: int = 0
    selected_count: int = 0
    has_sufficient_evidence: bool = True
