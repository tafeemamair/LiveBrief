"""Lightweight in-session context manager for resolving conversational follow-ups."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple
from livebrief.voice.utterance import UtteranceType


class SessionContextTurn:
    """A single completed query turn in the current LiveBrief voice session."""

    def __init__(
        self,
        original_query: str,
        resolved_query: str,
        summary: str,
        keywords: Optional[List[str]] = None,
    ) -> None:
        self.original_query = original_query
        self.resolved_query = resolved_query
        self.summary = summary
        self.keywords = keywords or []


# Anaphoric references that typically signal dependency on prior topic
ANAPHORIC_PATTERNS = [
    re.compile(r"\b(why|how so|why so|how come)\b", re.IGNORECASE),
    re.compile(r"\b(what about|how about|and what about)\b", re.IGNORECASE),
    re.compile(r"\b(explain that|elaborate on that|tell me more|more details)\b", re.IGNORECASE),
    re.compile(r"\b(its|it|that|this|these|those|the former|the latter)\b", re.IGNORECASE),
]


class SessionContextManager:
    """
    Tracks recent conversation context within the active LiveBrief session.
    Enables accurate formulation of concise follow-ups (e.g. "Why?", "What about latency?")
    without modifying the underlying retrieval architecture or fabricating claims.
    
    Guarantees:
    1. Context serves strictly as a query-formulation aid.
    2. Session history is never injected as verified evidence.
    3. Every substantive query (direct or follow-up) executes fresh Moss retrieval and evidence validation.
    """

    def __init__(self, session_id: str = "default_session", max_history: int = 5) -> None:
        self.session_id = session_id
        self.max_history = max_history
        self._history: List[SessionContextTurn] = []

    @property
    def history(self) -> List[SessionContextTurn]:
        """Return chronological turn history."""
        return list(self._history)

    @property
    def active_topic(self) -> Optional[str]:
        """Return the most recent active topic or query."""
        if not self._history:
            return None
        last = self._history[-1]
        return last.original_query

    def add_turn(
        self,
        original_query: str,
        resolved_query: str,
        summary: str,
        keywords: Optional[List[str]] = None,
    ) -> None:
        """Record a completed query turn."""
        turn = SessionContextTurn(
            original_query=original_query.strip(),
            resolved_query=resolved_query.strip(),
            summary=summary.strip(),
            keywords=keywords,
        )
        self._history.append(turn)
        if len(self._history) > self.max_history:
            self._history.pop(0)

    def resolve_query(self, text: str, utterance_type: UtteranceType) -> Tuple[str, Optional[str]]:
        """
        Contextualize incoming text if it is a follow-up or contains anaphora.
        Returns: (query_to_send_to_pipeline, context_description_or_none).
        """
        clean_text = text.strip()
        if not self._history:
            return clean_text, None

        # Direct queries without anaphora execute as-is
        is_followup = utterance_type == UtteranceType.FOLLOW_UP
        has_anaphora = any(pattern.search(clean_text) for pattern in ANAPHORIC_PATTERNS)

        if not is_followup and not (has_anaphora and len(clean_text.split()) <= 6):
            return clean_text, None

        last_turn = self._history[-1]
        prior_context = last_turn.original_query
        
        # Formulate contextualized query string
        contextualized = f"{clean_text} [Context: {prior_context}]"
        return contextualized, prior_context

    def clear(self) -> None:
        """Clear session context."""
        self._history.clear()
