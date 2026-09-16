"""Tests for session context manager and follow-up resolution."""

import pytest
from livebrief.voice.context import SessionContextManager
from livebrief.voice.utterance import UtteranceType


def test_session_context_turn_recording():
    mgr = SessionContextManager(session_id="test_sess", max_history=3)
    assert mgr.active_topic is None

    mgr.add_turn(
        original_query="What is LiveBrief?",
        resolved_query="What is LiveBrief?",
        summary="LiveBrief is a real-time AI research engine.",
    )
    assert mgr.active_topic == "What is LiveBrief?"


def test_session_context_followup_resolution():
    mgr = SessionContextManager(session_id="test_sess")
    mgr.add_turn(
        original_query="LiveBrief system architecture",
        resolved_query="LiveBrief system architecture",
        summary="Architecture specification.",
    )

    # Contextual follow-up
    resolved, context_anchor = mgr.resolve_query("What about latency?", UtteranceType.FOLLOW_UP)
    assert "LiveBrief system architecture" in resolved
    assert context_anchor == "LiveBrief system architecture"
    assert resolved == "What about latency? [Context: LiveBrief system architecture]"


def test_session_context_direct_query_unaltered():
    mgr = SessionContextManager(session_id="test_sess")
    mgr.add_turn(
        original_query="LiveBrief system architecture",
        resolved_query="LiveBrief system architecture",
        summary="Architecture specification.",
    )

    # Direct query should not be modified
    resolved, context_anchor = mgr.resolve_query("How does indexing work?", UtteranceType.DIRECT_QUERY)
    assert resolved == "How does indexing work?"
    assert context_anchor is None


def test_session_context_clear():
    mgr = SessionContextManager(session_id="test_sess")
    mgr.add_turn("Query 1", "Query 1", "Summary 1")
    assert mgr.active_topic == "Query 1"

    mgr.clear()
    assert mgr.active_topic is None
