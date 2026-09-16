"""Tests for utterance classification and query detection."""

import pytest
from livebrief.voice.utterance import UtteranceDetector, UtteranceType


def test_utterance_rejects_phatic_fillers():
    fillers = ["um", "uh", "yeah", "okay", "like", "so", "um yeah", "uh ok right"]
    for f in fillers:
        utype, triggered, reason = UtteranceDetector.classify(f)
        assert triggered is False, f"Expected '{f}' to be suppressed, but was triggered."
        assert utype == UtteranceType.FILLER


def test_utterance_rejects_incomplete_fragments():
    fragments = ["can you", "the test", "and then", "if you", "because of", "testing mic"]
    for frag in fragments:
        utype, triggered, reason = UtteranceDetector.classify(frag)
        assert triggered is False, f"Expected fragment '{frag}' to be suppressed, but was triggered."
        assert utype == UtteranceType.FRAGMENT


def test_utterance_accepts_short_meaningful_queries():
    short_queries = [
        "Why?",
        "How so?",
        "What about latency?",
        "And performance?",
        "What else?",
    ]
    for sq in short_queries:
        utype, triggered, reason = UtteranceDetector.classify(sq)
        assert triggered is True, f"Expected short query '{sq}' to trigger, but was suppressed."
        assert utype == UtteranceType.FOLLOW_UP


def test_utterance_accepts_direct_questions():
    questions = [
        "What are the latency budgets in LiveBrief?",
        "How does Moss hybrid retrieval work?",
        "Where are documents stored?",
        "Who built the retrieval engine?",
    ]
    for q in questions:
        utype, triggered, reason = UtteranceDetector.classify(q)
        assert triggered is True
        assert utype == UtteranceType.DIRECT_QUERY


def test_utterance_accepts_directive_prompts():
    directives = [
        "Explain the hallucination safeguards.",
        "Summarize the system architecture.",
        "Describe MMR evidence selection.",
    ]
    for d in directives:
        utype, triggered, reason = UtteranceDetector.classify(d)
        assert triggered is True
        assert utype == UtteranceType.DIRECT_QUERY


def test_utterance_empty_text():
    utype, triggered, reason = UtteranceDetector.classify("   ")
    assert triggered is False
    assert utype == UtteranceType.FRAGMENT
