"""Finite State Machine managing microphone activation and incremental STT streaming."""

from __future__ import annotations

import time
import uuid
from typing import Callable, List, Optional
from livebrief.voice.models import (
    TranscriptSegment,
    VoiceEvent,
    VoiceSessionMetrics,
    VoiceState,
)


class VoiceActivationStateMachine:
    """
    Finite State Machine governing LiveBrief voice session lifecycle.
    Guarantees:
    1. Microphone and audio processing are strictly OFF in IDLE and STOPPED states.
    2. Microphone capture begins ONLY upon explicit Start activation.
    3. Stop activation terminates capture immediately and transitions to safe OFF state.
    4. Errors (permission denial, hardware unavailability) cleanly transition to ERROR state with actionable detail.
    """

    def __init__(self, session_id: Optional[str] = None) -> None:
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self._state: VoiceState = VoiceState.IDLE
        self._interim_text: str = ""
        self._final_segments: List[TranscriptSegment] = []
        self._listeners: List[Callable[[VoiceEvent], None]] = []
        self._metrics = VoiceSessionMetrics(session_id=self.session_id)
        self._segment_counter = 0

    @property
    def state(self) -> VoiceState:
        """Current lifecycle state."""
        return self._state

    @property
    def is_live(self) -> bool:
        """Check if currently in LIVE listening state."""
        return self._state == VoiceState.LISTENING

    @property
    def is_off(self) -> bool:
        """Check if currently in OFF (IDLE or STOPPED) state."""
        return self._state in (VoiceState.IDLE, VoiceState.STOPPED)

    @property
    def interim_text(self) -> str:
        """Current live uncommitted speech hypothesis."""
        return self._interim_text

    @property
    def final_segments(self) -> List[TranscriptSegment]:
        """All committed final transcript segments in chronological order."""
        return list(self._final_segments)

    @property
    def metrics(self) -> VoiceSessionMetrics:
        """Observability metrics for current session."""
        return self._metrics

    def add_listener(self, callback: Callable[[VoiceEvent], None]) -> None:
        """Register a callback for voice lifecycle and transcript events."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[VoiceEvent], None]) -> None:
        """Unregister an event callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _emit(self, event: VoiceEvent) -> None:
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                # Do not allow listener failures to break state machine
                pass

    def start(self) -> VoiceState:
        """
        Explicitly request Start LiveBrief activation.
        Transitions: IDLE/STOPPED/ERROR -> REQUESTING_PERMISSION -> LISTENING.
        """
        if self._state == VoiceState.LISTENING:
            return self._state

        self._state = VoiceState.REQUESTING_PERMISSION
        self._emit(VoiceEvent(event_type="STATE_CHANGE", state=self._state))

        # Permission granted -> transition to LIVE
        self._state = VoiceState.LISTENING
        self._metrics.started_at_ms = time.time() * 1000.0
        self._metrics.last_error = None
        self._interim_text = ""
        self._emit(VoiceEvent(event_type="STATE_CHANGE", state=self._state))
        return self._state

    def stop(self) -> VoiceState:
        """
        Explicitly request Stop LiveBrief deactivation.
        Terminates live capture immediately and returns to OFF state.
        """
        if self.is_off:
            return self._state

        self._state = VoiceState.STOPPING
        self._emit(VoiceEvent(event_type="STATE_CHANGE", state=self._state))

        # Teardown complete -> transition to STOPPED
        self._state = VoiceState.STOPPED
        self._metrics.stopped_at_ms = time.time() * 1000.0
        self._interim_text = ""
        self._emit(VoiceEvent(event_type="STATE_CHANGE", state=self._state))
        return self._state

    def push_interim_transcript(self, text: str, confidence: float = 0.8) -> Optional[TranscriptSegment]:
        """
        Receive incremental uncommitted speech transcript while user is speaking.
        Ignored if not in LIVE LISTENING state.
        """
        if not self.is_live:
            return None

        clean_text = text.strip()
        self._interim_text = clean_text

        segment = TranscriptSegment(
            id=f"seg_interim_{self._segment_counter}",
            text=clean_text,
            is_final=False,
            confidence=confidence,
        )
        self._emit(VoiceEvent(event_type="TRANSCRIPT_INTERIM", state=self._state, segment=segment))
        return segment

    def commit_final_transcript(self, text: str, confidence: float = 1.0) -> Optional[TranscriptSegment]:
        """
        Commit a finalized sentence or speech segment.
        Ignored if not in LIVE LISTENING state.
        """
        if not self.is_live:
            return None

        clean_text = text.strip()
        if not clean_text:
            return None

        self._segment_counter += 1
        segment = TranscriptSegment(
            id=f"seg_{self._segment_counter}",
            text=clean_text,
            is_final=True,
            confidence=confidence,
        )
        self._final_segments.append(segment)
        self._interim_text = ""

        # Update metrics
        self._metrics.final_segments_count += 1
        self._metrics.total_segments_count += 1
        self._metrics.total_words_count += len(clean_text.split())

        self._emit(VoiceEvent(event_type="TRANSCRIPT_FINAL", state=self._state, segment=segment))
        return segment

    def handle_error(self, error_message: str) -> VoiceState:
        """
        Handle a hardware or speech recognition error.
        Transitions state machine to ERROR state.
        """
        self._state = VoiceState.ERROR
        self._interim_text = ""
        self._metrics.last_error = error_message
        self._emit(VoiceEvent(event_type="ERROR", state=self._state, error_message=error_message))
        return self._state

    def reset(self) -> VoiceState:
        """Reset state machine back to clean IDLE (OFF) state."""
        self._state = VoiceState.IDLE
        self._interim_text = ""
        self._final_segments.clear()
        self._segment_counter = 0
        self._metrics = VoiceSessionMetrics(session_id=self.session_id)
        self._emit(VoiceEvent(event_type="STATE_CHANGE", state=self._state))
        return self._state

    def get_full_transcript(self) -> str:
        """Return full concatenated transcript text from all committed final segments."""
        return " ".join(seg.text for seg in self._final_segments if seg.text)
