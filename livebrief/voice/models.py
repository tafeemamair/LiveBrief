"""Data models for voice activation, speech-to-text streaming, and state machine."""

from __future__ import annotations

import enum
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class VoiceState(str, enum.Enum):
    """Explicit lifecycle states for LiveBrief voice activation."""

    IDLE = "IDLE"  # OFF state: Microphone inactive, no stream open
    REQUESTING_PERMISSION = "REQUESTING_PERMISSION"  # User clicked Start, awaiting mic grant
    LISTENING = "LISTENING"  # LIVE state: Active mic stream and STT processing
    STOPPING = "STOPPING"  # Teardown in progress
    STOPPED = "STOPPED"  # Fully terminated and returned to OFF
    ERROR = "ERROR"  # Error state (e.g. permission denied, device missing)


class TranscriptSegment(BaseModel):
    """Incremental transcript segment emitted during speech."""

    id: str
    text: str
    is_final: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp_ms: float = Field(default_factory=lambda: time.time() * 1000.0)
    speaker_id: Optional[str] = None
    language: str = "en-US"


class VoiceSessionMetrics(BaseModel):
    """Observability metrics for a voice session."""

    session_id: str
    started_at_ms: Optional[float] = None
    stopped_at_ms: Optional[float] = None
    total_segments_count: int = 0
    final_segments_count: int = 0
    total_words_count: int = 0
    last_error: Optional[str] = None


class VoiceEvent(BaseModel):
    """Event emitted across voice lifecycle state changes and speech stream."""

    event_type: str  # "STATE_CHANGE", "TRANSCRIPT_INTERIM", "TRANSCRIPT_FINAL", "ERROR"
    state: VoiceState
    segment: Optional[TranscriptSegment] = None
    error_message: Optional[str] = None
    timestamp_ms: float = Field(default_factory=lambda: time.time() * 1000.0)
