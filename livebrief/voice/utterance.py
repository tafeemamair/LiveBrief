"""Utterance classification and meaningful query detection for speech streams."""

from __future__ import annotations

import enum
import re
from typing import List, Optional, Set, Tuple


class UtteranceType(str, enum.Enum):
    """Categorization of incoming speech utterances."""

    FILLER = "FILLER"  # Conversational filler/phatic speech ("um", "uh", "yeah", "like")
    FRAGMENT = "FRAGMENT"  # Incomplete fragment ("can you", "and then", "the test")
    FOLLOW_UP = "FOLLOW_UP"  # Contextual follow-up ("Why?", "What about latency?", "How so?")
    DIRECT_QUERY = "DIRECT_QUERY"  # Full substantive question or research statement


# Common conversational fillers and phatic expressions
PHATIC_FILLERS: Set[str] = {
    "um", "uh", "uhm", "er", "ah", "like", "yeah", "yep", "yes", "no", "nah",
    "okay", "ok", "right", "so", "well", "hmm", "hm", "you know", "i mean",
    "hey", "hello", "hi", "testing", "check", "one two three",
}

# Fragments that indicate incomplete grammatical constructs
FRAGMENT_PATTERNS: List[re.Pattern] = [
    re.compile(r"^(can you|could you|would you|if you|so if|and then|because of|with the|to the|of the|in the)$", re.IGNORECASE),
    re.compile(r"^(the test|test test|testing mic|mic check|just a test)$", re.IGNORECASE),
    re.compile(r"^(i think|i guess|maybe|perhaps|actually|honestly)$", re.IGNORECASE),
]

# Follow-up patterns that depend on preceding conversation context
FOLLOW_UP_PATTERNS: List[re.Pattern] = [
    re.compile(r"^(why|why is that|why so|how so|how come)\??$", re.IGNORECASE),
    re.compile(r"^(what about|how about|and what about)\s+.+", re.IGNORECASE),
    re.compile(r"^(what else|anything else|what more)\??$", re.IGNORECASE),
    re.compile(r"^(and performance|and latency|and security|and cost|and accuracy)\??$", re.IGNORECASE),
    re.compile(r"^(who built it|who created it|when was this|where is this)\??$", re.IGNORECASE),
]

# Question indicators and intent verbs
INTERROGATIVE_WORDS: Set[str] = {
    "what", "why", "how", "where", "when", "who", "which", "whose", "whom",
    "is", "are", "was", "were", "do", "does", "did", "can", "could", "should", "would",
}

DIRECTIVE_VERBS: Set[str] = {
    "explain", "describe", "summarize", "detail", "clarify", "elaborate",
    "outline", "analyze", "compare", "contrast", "list", "show",
}


class UtteranceDetector:
    """
    Evaluates finalized speech segments to determine if they represent a substantive
    query that should trigger LiveBrief intelligence retrieval.
    """

    @classmethod
    def classify(cls, text: str) -> Tuple[UtteranceType, bool, str]:
        """
        Classify text and return (UtteranceType, should_trigger_retrieval, reason).
        """
        clean = text.strip()
        if not clean:
            return UtteranceType.FRAGMENT, False, "Empty text"

        lower = clean.lower().rstrip(".?!,")
        words = re.findall(r"\b[a-z0-9'-]+\b", lower)

        if not words:
            return UtteranceType.FRAGMENT, False, "No valid words"

        # 1. Check for pure phatic filler speech
        if lower in PHATIC_FILLERS or all(w in PHATIC_FILLERS for w in words):
            return UtteranceType.FILLER, False, f"Phatic/filler expression: '{clean}'"

        # 2. Check for explicit follow-up patterns
        for pattern in FOLLOW_UP_PATTERNS:
            if pattern.match(clean) or pattern.match(lower):
                return UtteranceType.FOLLOW_UP, True, f"Contextual follow-up: '{clean}'"

        # 3. Check for incomplete fragments
        for pattern in FRAGMENT_PATTERNS:
            if pattern.match(lower):
                return UtteranceType.FRAGMENT, False, f"Incomplete speech fragment: '{clean}'"

        # Very short 1-word inputs that are not follow-ups
        if len(words) == 1 and words[0] not in DIRECTIVE_VERBS:
            return UtteranceType.FRAGMENT, False, f"Single isolated non-directive word: '{clean}'"

        # 4. Check for substantive questions or directives
        first_word = words[0]
        has_question_mark = clean.endswith("?")
        is_interrogative = first_word in INTERROGATIVE_WORDS or has_question_mark
        is_directive = first_word in DIRECTIVE_VERBS

        # Substantive statement or query (e.g. "LiveBrief latency budget in memory")
        has_substantive_content = len(words) >= 3 or is_interrogative or is_directive

        if has_substantive_content:
            return UtteranceType.DIRECT_QUERY, True, f"Substantive query: '{clean}'"

        return UtteranceType.FRAGMENT, False, f"Insufficient grammatical intent: '{clean}'"
