"""Query request and filtering models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QueryFilter(BaseModel):
    """Filter specification compatible with Moss indexing engine."""

    field: str
    operator: str = "$eq"  # $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin
    value: Any

    def to_moss_dict(self) -> Dict[str, Any]:
        """Convert to the dictionary format expected by Moss query filters."""
        return {
            "field": self.field,
            "condition": {self.operator: self.value},
        }


class QueryRequest(BaseModel):
    """User retrieval & briefing query."""

    query: str
    top_k: int = Field(default=5, ge=1, le=50)
    alpha: float = Field(default=0.8, ge=0.0, le=1.0)
    filters: Optional[List[QueryFilter]] = None
    max_evidence_tokens: int = Field(default=2048, ge=64)
    min_relevance_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
