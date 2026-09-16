/**
 * LiveBrief Real-Time Incremental Speech-to-Text Controller (Phase 2.1)
 * Manages explicit Start/Stop lifecycle, audio stream teardown, and Web Speech API streaming.
 */

class LiveBriefSpeechController {
  constructor(uiElements) {
    this.ui = uiElements;
    this.state = "IDLE"; // IDLE, REQUESTING_PERMISSION, LISTENING, STOPPED, ERROR
    
    this.recognition = null;
    this.mediaStream = null;
    this.audioContext = null;
    this.analyser = null;
    this.meterAnimationId = null;
    
    this.finalSegments = [];
    this.totalWords = 0;
    
    this.initRecognition();
    this.bindEvents();
    this.updateUI();
  }

  /**
   * Check browser support and instantiate SpeechRecognition.
   */
  initRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      this.showError(
        "Browser Not Supported",
        "Web Speech API is not supported in this browser. Please use Chrome, Edge, or Safari."
      );
      this.setState("ERROR");
      return;
    }

    this.recognition = new SpeechRecognition();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = "en-US";
    this.recognition.maxAlternatives = 1;

    // Incremental speech event handler
    this.recognition.onresult = (event) => this.handleRecognitionResult(event);

    // Error handler
    this.recognition.onerror = (event) => this.handleRecognitionError(event);

    // Unexpected end / boundary handler
    this.recognition.onend = () => {
      // If we are still in LISTENING state (e.g. Chrome silent timeout), auto-restart
      if (this.state === "LISTENING") {
        try {
          this.recognition.start();
        } catch (e) {
          // Ignore if already active
        }
      }
    };
  }

  /**
   * Bind UI event listeners.
   */
  bindEvents() {
    this.ui.startBtn.addEventListener("click", () => this.start());
    this.ui.stopBtn.addEventListener("click", () => this.stop());
    this.ui.clearBtn.addEventListener("click", () => this.clearTranscript());
    this.ui.dismissErrorBtn.addEventListener("click", () => this.hideError());
  }

  /**
   * Start LiveBrief voice capture (explicit user action).
   */
  async start() {
    if (this.state === "LISTENING") return;
    this.hideError();

    try {
      this.setState("REQUESTING_PERMISSION");

      // 1. Explicitly request microphone stream
      this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });

      // 2. Setup AudioContext for input level metering
      this.setupAudioMetering(this.mediaStream);

      // 3. Start Web Speech recognition
      this.recognition.start();

      this.setState("LISTENING");
    } catch (err) {
      console.error("Microphone activation failed:", err);
      let msg = "Microphone access failed. Please ensure a microphone is connected.";
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        msg = "Microphone permission was denied. Please allow microphone access in your browser address bar settings.";
      } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
        msg = "No microphone hardware detected on this device.";
      }
      this.showError("Microphone Activation Error", msg);
      this.teardownAudio();
      this.setState("ERROR");
    }
  }

  /**
   * Stop LiveBrief voice capture immediately (explicit user action).
   */
  stop() {
    if (this.state === "IDLE" || this.state === "STOPPED") return;

    this.setState("STOPPED");
    this.teardownAudio();
  }

  /**
   * Completely release hardware audio tracks, audio context, and recognition.
   */
  teardownAudio() {
    // 1. Stop Speech Recognition
    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch (e) {
        // Safe ignore
      }
    }

    // 2. Stop and release all MediaStream audio tracks
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch (e) {}
      });
      this.mediaStream = null;
    }

    // 3. Close AudioContext
    if (this.meterAnimationId) {
      cancelAnimationFrame(this.meterAnimationId);
      this.meterAnimationId = null;
    }

    if (this.audioContext && this.audioContext.state !== "closed") {
      try {
        this.audioContext.close();
      } catch (e) {}
      this.audioContext = null;
    }

    // Reset meter UI
    this.ui.meterBar.style.width = "0%";
    this.ui.meterVal.textContent = "0%";
    this.ui.interimContainer.classList.add("hidden");
    this.ui.interimText.textContent = "";
  }

  /**
   * Setup Web Audio API analyser to measure real-time microphone VU level.
   */
  setupAudioMetering(stream) {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new AudioCtx();
      const source = this.audioContext.createMediaStreamSource(stream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
      source.connect(this.analyser);

      const buffer = new Uint8Array(this.analyser.frequencyBinCount);

      const updateMeter = () => {
        if (this.state !== "LISTENING" || !this.analyser) {
          this.ui.meterBar.style.width = "0%";
          this.ui.meterVal.textContent = "0%";
          return;
        }

        this.analyser.getByteFrequencyData(buffer);
        let sum = 0;
        for (let i = 0; i < buffer.length; i++) {
          sum += buffer[i];
        }
        const avg = sum / buffer.length;
        const percent = Math.min(100, Math.round((avg / 128) * 100));

        this.ui.meterBar.style.width = `${percent}%`;
        this.ui.meterVal.textContent = `${percent}%`;

        this.meterAnimationId = requestAnimationFrame(updateMeter);
      };

      this.meterAnimationId = requestAnimationFrame(updateMeter);
    } catch (e) {
      console.warn("Audio metering setup failed, falling back without VU meter:", e);
    }
  }

  /**
   * Process incremental speech recognition results.
   */
  handleRecognitionResult(event) {
    if (this.state !== "LISTENING") return;

    let interimTranscript = "";

    for (let i = event.resultIndex; i < event.results.length; ++i) {
      const res = event.results[i];
      const text = res[0].transcript;

      if (res.isFinal) {
        this.commitFinalSegment(text.trim());
      } else {
        interimTranscript += text;
      }
    }

    // Update live interim transcript display
    if (interimTranscript.trim()) {
      this.ui.interimContainer.classList.remove("hidden");
      this.ui.interimText.textContent = interimTranscript.trim();
      this.ui.emptyState.style.display = "none";
      this.ui.transcriptViewport.scrollTop = this.ui.transcriptViewport.scrollHeight;
    } else {
      this.ui.interimContainer.classList.add("hidden");
      this.ui.interimText.textContent = "";
    }
  }

  /**
   * Commit a finalized sentence segment to the transcript history.
   */
  commitFinalSegment(text) {
    if (!text) return;

    const timestamp = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const segment = { id: `seg_${Date.now()}`, text, timestamp };
    this.finalSegments.push(segment);

    // Render segment DOM element
    const segEl = document.createElement("div");
    segEl.className = "transcript-segment";
    segEl.innerHTML = `
      <span class="segment-time">[${timestamp}]</span>
      <span class="segment-text">${escapeHtml(text)}</span>
    `;
    this.ui.finalizedContainer.appendChild(segEl);

    // Update stats
    const wordsInSeg = text.split(/\s+/).filter(Boolean).length;
    this.totalWords += wordsInSeg;
    this.ui.wordCountBadge.textContent = `${this.totalWords} words`;
    this.ui.segmentCountBadge.textContent = `${this.finalSegments.length} segments`;

    this.ui.emptyState.style.display = "none";
    this.ui.transcriptViewport.scrollTop = this.ui.transcriptViewport.scrollHeight;

    // Phase 2.2 Integration: Forward finalized transcript segment to copilot controller
    if (window.copilotController && typeof window.copilotController.handleTranscriptSegment === "function") {
      window.copilotController.handleTranscriptSegment(text);
    }
  }

  /**
   * Handle recognition errors gracefully.
   */
  handleRecognitionError(event) {
    console.warn("Speech recognition error:", event.error);

    if (event.error === "no-speech") {
      // User paused speaking; normal in continuous conversation
      return;
    }

    if (event.error === "aborted" && (this.state === "STOPPED" || this.state === "IDLE")) {
      // Normal intentional stop
      return;
    }

    let title = "Speech Recognition Error";
    let desc = `Error: ${event.error}`;

    if (event.error === "not-allowed") {
      title = "Microphone Permission Denied";
      desc = "Permission to access the microphone was blocked. Please enable microphone permissions in your browser.";
    } else if (event.error === "audio-capture") {
      title = "No Microphone Found";
      desc = "Unable to capture audio. Ensure your microphone is plugged in and recognized by your system.";
    } else if (event.error === "network") {
      title = "Network Connection Issue";
      desc = "Speech recognition service encountered a network error. Check your internet connection.";
    }

    this.showError(title, desc);
    this.stop();
    this.setState("ERROR");
  }

  /**
   * Clear all transcript history.
   */
  clearTranscript() {
    this.finalSegments = [];
    this.totalWords = 0;
    this.ui.finalizedContainer.innerHTML = "";
    this.ui.interimContainer.classList.add("hidden");
    this.ui.interimText.textContent = "";
    this.ui.wordCountBadge.textContent = "0 words";
    this.ui.segmentCountBadge.textContent = "0 segments";
    this.ui.emptyState.style.display = "flex";
  }

  /**
   * Update internal state and synchronize UI.
   */
  setState(newState) {
    this.state = newState;
    this.updateUI();
  }

  updateUI() {
    const isLive = this.state === "LISTENING";
    const isError = this.state === "ERROR";
    const isReq = this.state === "REQUESTING_PERMISSION";

    // Buttons
    this.ui.startBtn.disabled = isLive || isReq;
    this.ui.stopBtn.disabled = !isLive && !isReq;

    // Status Badge & Meta
    if (isLive) {
      this.ui.statusBadge.className = "status-badge status-live";
      this.ui.statusText.textContent = "Status: 🔴 LIVE / Listening";
      this.ui.stateMeta.textContent = "State: LISTENING (Microphone & STT Active)";
      if (this.ui.captureStatus) {
        this.ui.captureStatus.textContent = "Active (Streaming)";
        this.ui.captureStatus.style.color = "#4ade80";
      }
    } else if (isError) {
      this.ui.statusBadge.className = "status-badge status-error";
      this.ui.statusText.textContent = "Status: ⚠️ Error";
      this.ui.stateMeta.textContent = "State: ERROR (Hardware stream closed)";
      if (this.ui.captureStatus) {
        this.ui.captureStatus.textContent = "Closed";
        this.ui.captureStatus.style.color = "#f87171";
      }
    } else if (isReq) {
      this.ui.statusBadge.className = "status-badge status-off";
      this.ui.statusText.textContent = "Status: ⏳ Requesting Permission...";
      this.ui.stateMeta.textContent = "State: REQUESTING_PERMISSION";
      if (this.ui.captureStatus) {
        this.ui.captureStatus.textContent = "Initializing...";
        this.ui.captureStatus.style.color = "#38bdf8";
      }
    } else {
      this.ui.statusBadge.className = "status-badge status-off";
      this.ui.statusText.textContent = "Status: ⚪ OFF / Inactive";
      this.ui.stateMeta.textContent = "State: IDLE (Hardware stream closed)";
      if (this.ui.captureStatus) {
        this.ui.captureStatus.textContent = "Closed";
        this.ui.captureStatus.style.color = "var(--text-secondary)";
      }
    }
  }

  showError(title, message) {
    this.ui.errorTitle.textContent = title;
    this.ui.errorMessage.textContent = message;
    this.ui.errorBanner.classList.remove("hidden");
  }

  hideError() {
    this.ui.errorBanner.classList.add("hidden");
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Instantiate on DOM load
document.addEventListener("DOMContentLoaded", () => {
  const uiElements = {
    startBtn: document.getElementById("startBtn"),
    stopBtn: document.getElementById("stopBtn"),
    clearBtn: document.getElementById("clearBtn"),
    dismissErrorBtn: document.getElementById("dismissErrorBtn"),
    errorBanner: document.getElementById("errorBanner"),
    errorTitle: document.getElementById("errorTitle"),
    errorMessage: document.getElementById("errorMessage"),
    statusBadge: document.getElementById("statusBadge"),
    statusText: document.getElementById("statusText"),
    stateMeta: document.getElementById("stateMeta"),
    captureStatus: document.getElementById("captureStatus"),
    meterBar: document.getElementById("meterBar"),
    meterVal: document.getElementById("meterVal"),
    transcriptViewport: document.getElementById("transcriptViewport"),
    finalizedContainer: document.getElementById("finalizedContainer"),
    interimContainer: document.getElementById("interimContainer"),
    interimText: document.getElementById("interimText"),
    emptyState: document.getElementById("emptyState"),
    wordCountBadge: document.getElementById("wordCountBadge"),
    segmentCountBadge: document.getElementById("segmentCountBadge"),
  };

  window.speechController = new LiveBriefSpeechController(uiElements);
});
