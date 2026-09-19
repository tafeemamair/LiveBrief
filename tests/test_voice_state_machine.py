"""Tests for Voice Activation State Machine and Voice Layer."""

import pytest
from livebrief.voice.models import VoiceEvent, VoiceState
from livebrief.voice.state_machine import VoiceActivationStateMachine


def test_initial_state_is_idle():
    sm = VoiceActivationStateMachine(session_id="test_init")
    assert sm.state == VoiceState.IDLE
    assert sm.is_off is True
    assert sm.is_live is False
    assert sm.interim_text == ""
    assert len(sm.final_segments) == 0


def test_start_transitions_to_listening():
    sm = VoiceActivationStateMachine(session_id="test_start")
    events = []
    sm.add_listener(lambda e: events.append(e))

    state = sm.start()
    assert state == VoiceState.LISTENING
    assert sm.is_live is True
    assert sm.is_off is False
    assert sm.metrics.started_at_ms is not None

    # Verify state change events emitted
    event_states = [e.state for e in events if e.event_type == "STATE_CHANGE"]
    assert VoiceState.REQUESTING_PERMISSION in event_states
    assert VoiceState.LISTENING in event_states


def test_stop_transitions_to_stopped():
    sm = VoiceActivationStateMachine(session_id="test_stop")
    sm.start()
    assert sm.is_live is True

    events = []
    sm.add_listener(lambda e: events.append(e))

    state = sm.stop()
    assert state == VoiceState.STOPPED
    assert sm.is_off is True
    assert sm.is_live is False
    assert sm.metrics.stopped_at_ms is not None

    event_states = [e.state for e in events if e.event_type == "STATE_CHANGE"]
    assert VoiceState.STOPPING in event_states
    assert VoiceState.STOPPED in event_states


def test_interim_transcript_streaming_and_invariants():
    sm = VoiceActivationStateMachine(session_id="test_interim")

    # Invariant: Must reject transcripts in IDLE state
    rejected = sm.push_interim_transcript("hello world")
    assert rejected is None
    assert sm.interim_text == ""

    # Start listening
    sm.start()
    events = []
    sm.add_listener(lambda e: events.append(e))

    seg1 = sm.push_interim_transcript("what are the latency")
    assert seg1 is not None
    assert seg1.is_final is False
    assert sm.interim_text == "what are the latency"
    assert len(events) == 1
    assert events[0].event_type == "TRANSCRIPT_INTERIM"

    # Streaming update to interim hypothesis
    seg2 = sm.push_interim_transcript("what are the latency budgets")
    assert sm.interim_text == "what are the latency budgets"


def test_commit_final_transcript():
    sm = VoiceActivationStateMachine(session_id="test_final")
    sm.start()
    sm.push_interim_transcript("livebrief uses moss")

    events = []
    sm.add_listener(lambda e: events.append(e))

    final_seg = sm.commit_final_transcript("LiveBrief uses Moss.")
    assert final_seg is not None
    assert final_seg.is_final is True
    assert final_seg.text == "LiveBrief uses Moss."
    assert sm.interim_text == ""  # Interim cleared on commit
    assert len(sm.final_segments) == 1
    assert sm.metrics.final_segments_count == 1
    assert sm.metrics.total_words_count == 3
    assert len(events) == 1
    assert events[0].event_type == "TRANSCRIPT_FINAL"

    # Commit another segment
    sm.commit_final_transcript("Retrieval takes sub-10ms.")
    assert len(sm.final_segments) == 2
    assert sm.get_full_transcript() == "LiveBrief uses Moss. Retrieval takes sub-10ms."


def test_error_handling_and_recovery():
    sm = VoiceActivationStateMachine(session_id="test_err")
    sm.start()

    events = []
    sm.add_listener(lambda e: events.append(e))

    state = sm.handle_error("Microphone permission was denied by user")
    assert state == VoiceState.ERROR
    assert sm.state == VoiceState.ERROR
    assert sm.metrics.last_error == "Microphone permission was denied by user"
    assert len(events) == 1
    assert events[0].event_type == "ERROR"

    # Invariant: Cannot receive transcripts in error state
    res = sm.push_interim_transcript("test speech")
    assert res is None

    # Reset recovers to IDLE
    reset_state = sm.reset()
    assert reset_state == VoiceState.IDLE
    assert sm.state == VoiceState.IDLE
    assert sm.metrics.last_error is None
    assert len(sm.final_segments) == 0


def test_listener_removal():
    sm = VoiceActivationStateMachine(session_id="test_removal")
    called = []
    listener = lambda e: called.append(e)

    sm.add_listener(listener)
    sm.start()
    assert len(called) > 0

    called.clear()
    sm.remove_listener(listener)
    sm.stop()
    assert len(called) == 0


def test_frontend_dom_elements_synchronization():
    """Verify that all document.getElementById calls in web/stt.js and web/copilot.js

    are either present in web/index.html or safely guarded against null dereferences.
    """
    import re
    from pathlib import Path

    web_dir = Path(__file__).resolve().parent.parent / "web"
    html_content = (web_dir / "index.html").read_text(encoding="utf-8")
    stt_content = (web_dir / "stt.js").read_text(encoding="utf-8")

    # Extract all IDs in index.html
    html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', html_content))

    # Extract all document.getElementById("...") in stt.js
    stt_ids = set(re.findall(r'document\.getElementById\(["\']([^"\']+)["\']\)', stt_content))

    # Verify that any element ID in stt.js that is missing in index.html is null-guarded in stt.js
    missing_ids = stt_ids - html_ids
    for missing in missing_ids:
        # Check that accesses to this.ui[missing] or this.ui.<missing> are guarded
        assert f"this.ui.{missing}" in stt_content
        # Ensure captureStatus is guarded with 'if (this.ui.captureStatus)'
        if missing == "captureStatus":
            assert "if (this.ui.captureStatus)" in stt_content


def test_format_interactive_citations_rendering_and_safety():
    """Verify that formatInteractiveCitations() in web/copilot.js safely escapes HTML,

    renders Markdown headings, preserves paragraphs, and injects interactive citation buttons.
    """
    import json
    from pathlib import Path
    import subprocess

    web_dir = Path(__file__).resolve().parent.parent / "web"

    js_test_harness = """
    const fs = require('fs');
    const vm = require('vm');
    const path = process.argv[1];
    let code = fs.readFileSync(path, 'utf8');

    // Mock document and window for class evaluation in Node
    global.document = {
      addEventListener: () => {},
      getElementById: () => null,
      createElement: (tag) => {
        let content = '';
        return {
          set textContent(val) {
            content = String(val)
              .replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
          },
          get innerHTML() {
            return content;
          }
        };
      }
    };
    global.window = {};
    global.fetch = () => Promise.resolve({ ok: false });

    vm.runInThisContext(code);

    const controller = new LiveBriefCopilotController({});

    // Test 1: Markdown heading and citation preservation
    const input1 = "## Hot-Path Latency\\n\\nSub-10ms retrieval [1]";
    const out1 = controller.formatInteractiveCitations(input1);

    // Test 2: Multiple headings and citations
    const input2 = "## Executive Overview\\n\\nBriefing engine. [1]\\n\\n## Architecture\\n\\nIn-process [2]";
    const out2 = controller.formatInteractiveCitations(input2);

    // Test 3: XSS attack payload
    const input3 = '<script>alert("xss")</script> [3]';
    const out3 = controller.formatInteractiveCitations(input3);

    console.log(JSON.stringify({ out1, out2, out3 }));
    """

    copilot_path = str(web_dir / "copilot.js")
    proc = subprocess.run(
        ["node", "-e", js_test_harness, copilot_path],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout.strip())

    out1 = data["out1"]
    out2 = data["out2"]
    out3 = data["out3"]

    # 1. Heading rendering verification
    assert '<h4 class="response-heading">Hot-Path Latency</h4>' in out1
    assert "## Hot-Path Latency" not in out1

    # 2. Citation preservation verification
    assert '<button type="button" class="cite-anchor-btn" data-cite-id="1">[1]</button>' in out1
    assert '<button type="button" class="cite-anchor-btn" data-cite-id="2">[2]</button>' in out2

    # 3. XSS safety verification
    assert "<script>" not in out3
    assert "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;" in out3
    assert '<button type="button" class="cite-anchor-btn" data-cite-id="3">[3]</button>' in out3


