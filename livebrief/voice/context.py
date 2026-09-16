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


class SessionContextManager:
    """
    Tracks recent conversation context within the active LiveBrief session.
    Enables accurate resolution of concise follow-ups (e.g. "Why?", "What about latency?")
    without modifying the underlying retrieval architecture or fabricating claims.
    """

    def __init__(self, session_id: str = "default_session", max_history: int = 5) -> None:
        self.session_id = session_id
        self.max_history = max_history
        self._history: List[SessionContextTurn] = []

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
            original_query=original_query,
            resolved_query=resolved_query,
            summary=summary,
            keywords=keywords,
        )
        self._history.append(turn)
        if len(self._history) > self.max_history:
            self._history.pop(0)

    def resolve_query(self, text: str, utterance_type: UtteranceType) -> Tuple[str, Optional[str]]:
        """
        Contextualize incoming text if it is a follow-up.
        Returns: (query_to_send_to_pipeline, context_description_or_none).
        """
        clean_text = text.strip()
        if not self._history or utterance_type != UtteranceType.FOLLOW_UP:
            return clean_text, None

        last_turn = self._history[-1]
        # Use previous query as topic anchor
        prior_context = last_turn.original_query
        
        # Clean contextual query formulation
        contextualized = f"{clean_text} [Context: {prior_context}]"
        return contextualized, prior_context

    def clear(self) -> None:
        """Clear session context."""
        self._history.clear()
