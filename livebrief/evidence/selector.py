"""Evidence selection, MMR deduplication, and span extraction."""

from __future__ import annotations

import re
from typing import List, Optional, Set
from livebrief.models.evidence import (
    EvidenceItem,
    EvidenceSelectionResult,
    EvidenceSpan,
)
from livebrief.retrieval.retriever import RetrievalResult, RetrievedCandidate


def estimate_token_count(text: str) -> int:
    """Fast approximation of token count (~4 characters per token)."""
    return max(1, len(text) // 4)


def extract_sentences(text: str) -> List[EvidenceSpan]:
    """Split chunk into sentence spans with offsets."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    spans: List[EvidenceSpan] = []
    cursor = 0
    for s in sentences:
        s_clean = s.strip()
        if not s_clean:
            continue
        start_idx = text.find(s_clean, cursor)
        if start_idx == -1:
            start_idx = cursor
        end_idx = start_idx + len(s_clean)
        cursor = end_idx
        spans.append(
            EvidenceSpan(
                text=s_clean,
                salience_score=1.0,
                start_char=start_idx,
                end_char=end_idx,
            )
        )
    return spans


def compute_jaccard_similarity(text_a: str, text_b: str) -> float:
    """Compute word-level Jaccard similarity for redundancy penalty."""
    words_a = set(re.findall(r"\w+", text_a.lower()))
    words_b = set(re.findall(r"\w+", text_b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = len(words_a.intersection(words_b))
    union = len(words_a.union(words_b))
    return intersection / union if union > 0 else 0.0


class EvidenceSelector:
    """
    Selects top evidence items using Maximal Marginal Relevance (MMR),
    sentence-level span localization, and context token budgeting.
    """

    def __init__(
        self,
        diversity_lambda: float = 0.7,
        min_relevance_threshold: float = 0.05,
    ) -> None:
        self.diversity_lambda = diversity_lambda
        self.min_relevance_threshold = min_relevance_threshold

    def select_evidence(
        self,
        retrieval: RetrievalResult,
        max_tokens: int = 2048,
        max_items: int = 5,
    ) -> EvidenceSelectionResult:
        """Select, deduplicate, and package evidence items."""
        candidates = retrieval.candidates
        if not candidates:
            return EvidenceSelectionResult(
                query=retrieval.query,
                items=[],
                total_tokens=0,
                candidate_count=0,
                selected_count=0,
                has_sufficient_evidence=False,
            )

        # Greedy MMR selection
        selected_candidates: List[RetrievedCandidate] = []
        remaining = list(candidates)

        while remaining and len(selected_candidates) < max_items:
            best_candidate: Optional[RetrievedCandidate] = None
            best_mmr_score = -float("inf")

            for cand in remaining:
                relevance = cand.score

                # Compute maximum similarity to already selected candidates
                max_sim = 0.0
                if selected_candidates:
                    max_sim = max(
                        compute_jaccard_similarity(cand.chunk.text, s.chunk.text)
                        for s in selected_candidates
                    )

                # MMR score formula: lambda * relevance - (1 - lambda) * max_redundancy
                mmr_score = (self.diversity_lambda * relevance) - ((1.0 - self.diversity_lambda) * max_sim)

                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_candidate = cand

            if best_candidate is not None:
                selected_candidates.append(best_candidate)
                remaining.remove(best_candidate)
            else:
                break

        # Package into EvidenceItems adhering to token budget
        items: List[EvidenceItem] = []
        total_tokens = 0
        citation_counter = 1

        for cand in selected_candidates:
            token_count = estimate_token_count(cand.chunk.text)
            if items and (total_tokens + token_count > max_tokens):
                # Token budget reached
                break

            spans = extract_sentences(cand.chunk.text)
            # Assign highest salience to spans matching query terms
            query_words = set(re.findall(r"\w+", retrieval.query.lower()))
            for span in spans:
                span_words = set(re.findall(r"\w+", span.text.lower()))
                overlap = len(query_words.intersection(span_words))
                span.salience_score = 1.0 + (0.5 * overlap)

            item = EvidenceItem(
                citation_id=citation_counter,
                chunk_id=cand.chunk.id,
                doc_id=cand.chunk.doc_id,
                text=cand.chunk.text,
                salient_spans=spans,
                relevance_score=cand.score,
                diversity_score=1.0,
                final_score=cand.score,
                metadata=dict(cand.chunk.metadata),
                token_estimate=token_count,
            )
            items.append(item)
            total_tokens += token_count
            citation_counter += 1

        has_sufficient = len(items) > 0 and max((item.relevance_score for item in items), default=0.0) >= self.min_relevance_threshold

        return EvidenceSelectionResult(
            query=retrieval.query,
            items=items,
            total_tokens=total_tokens,
            candidate_count=len(candidates),
            selected_count=len(items),
            has_sufficient_evidence=has_sufficient,
        )
