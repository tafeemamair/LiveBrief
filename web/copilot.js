/**
 * LiveBrief Intelligence Copilot Controller (Phase 2.3)
 * Manages truthful request lifecycle, stale response protection, interactive evidence explorer,
 * and private knowledge base drawer REST operations.
 */

class LiveBriefCopilotController {
  constructor(uiElements) {
    this.ui = uiElements;
    this.sessionId = `sess_${Date.now().toString(36)}`;
    this.coalesceTimer = null;
    this.coalesceDelayMs = 600; // 600ms debounce/coalescing window
    this.pendingUtterance = "";
    this.isQuerying = false;
    this.currentRequestId = 0; // Stale-response guard sequence counter
    this.currentEvidenceSources = []; // In-memory evidence cache for provenance inspection

    this.bindEvents();
    this.loadDocuments();
    this.setCopilotState("READY", "Ready for speech");
  }

  bindEvents() {
    // Manual query submit fallback
    if (this.ui.manualQueryBtn && this.ui.manualQueryInput) {
      this.ui.manualQueryBtn.addEventListener("click", () => {
        const text = this.ui.manualQueryInput.value.trim();
        if (text) {
          this.triggerQuery(text);
          this.ui.manualQueryInput.value = "";
        }
      });

      this.ui.manualQueryInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          const text = this.ui.manualQueryInput.value.trim();
          if (text) {
            this.triggerQuery(text);
            this.ui.manualQueryInput.value = "";
          }
        }
      });
    }

    // Stop and Clear button safety: cancel pending debounce and invalidate in-flight queries
    const stopBtn = document.getElementById("stopBtn");
    if (stopBtn) {
      stopBtn.addEventListener("click", () => this.cancelPendingOperations());
    }

    const clearBtn = document.getElementById("clearBtn");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        this.cancelPendingOperations();
        this.resetCopilotDisplay();
      });
    }

    // Evidence Explorer Modal Close
    if (this.ui.closeEvidenceModalBtn) {
      this.ui.closeEvidenceModalBtn.addEventListener("click", () => this.closeEvidenceModal());
    }
    if (this.ui.evidenceModal) {
      this.ui.evidenceModal.addEventListener("click", (e) => {
        if (e.target === this.ui.evidenceModal) {
          this.closeEvidenceModal();
        }
      });
    }

    // Knowledge Base Drawer
    if (this.ui.kbToggleBtn) {
      this.ui.kbToggleBtn.addEventListener("click", () => this.openKbDrawer());
    }
    if (this.ui.closeKbDrawerBtn) {
      this.ui.closeKbDrawerBtn.addEventListener("click", () => this.closeKbDrawer());
    }
    if (this.ui.kbDrawer) {
      this.ui.kbDrawer.addEventListener("click", (e) => {
        if (e.target === this.ui.kbDrawer) {
          this.closeKbDrawer();
        }
      });
    }
    if (this.ui.kbIndexBtn) {
      this.ui.kbIndexBtn.addEventListener("click", () => this.indexDocument());
    }
    if (this.ui.kbRefreshBtn) {
      this.ui.kbRefreshBtn.addEventListener("click", () => this.loadDocuments());
    }

    // Escape key to close open modals
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        this.closeEvidenceModal();
        this.closeKbDrawer();
      }
    });
  }

  /**
   * Cancel pending debounce timer and increment request ID to drop stale in-flight responses.
   */
  cancelPendingOperations() {
    if (this.coalesceTimer) {
      clearTimeout(this.coalesceTimer);
      this.coalesceTimer = null;
    }
    this.pendingUtterance = "";
    this.isQuerying = false;
    this.currentRequestId++;
    this.setCopilotState("READY", "Stopped / Ready");
  }

  /**
   * Reset copilot display to initial placeholder state.
   */
  resetCopilotDisplay() {
    this.ui.copilotContent.classList.add("hidden");
    this.ui.copilotPlaceholder.classList.remove("hidden");
    this.currentEvidenceSources = [];
  }

  /**
   * Update the truthful intelligence lifecycle state indicator.
   */
  setCopilotState(state, message) {
    if (this.ui.copilotStatusText && message) {
      this.ui.copilotStatusText.textContent = message;
    }

    const pillListening = document.getElementById("pillListening");
    const pillUnderstanding = document.getElementById("pillUnderstanding");
    const pillRetrieving = document.getElementById("pillRetrieving");
    const pillReady = document.getElementById("pillReady");

    const allPills = [pillListening, pillUnderstanding, pillRetrieving, pillReady];
    allPills.forEach((p) => p && p.classList.remove("active"));

    switch (state) {
      case "LISTENING":
        if (pillListening) pillListening.classList.add("active");
        break;
      case "UNDERSTANDING":
        if (pillUnderstanding) pillUnderstanding.classList.add("active");
        break;
      case "RETRIEVING":
        if (pillRetrieving) pillRetrieving.classList.add("active");
        break;
      case "READY":
      default:
        if (pillReady) pillReady.classList.add("active");
        break;
    }
  }

  /**
   * Called by STT controller whenever a new final transcript segment is emitted.
   */
  handleTranscriptSegment(text) {
    if (!text || !text.trim()) return;

    if (this.pendingUtterance) {
      this.pendingUtterance += " " + text.trim();
    } else {
      this.pendingUtterance = text.trim();
    }

    // Reset coalescing timer
    if (this.coalesceTimer) {
      clearTimeout(this.coalesceTimer);
    }

    this.setCopilotState("UNDERSTANDING", `Understanding query: "${this.pendingUtterance}"...`);
    this.showCopilotLoading(`Coalescing speech utterance: "${this.pendingUtterance}"...`);

    this.coalesceTimer = setTimeout(() => {
      const fullUtterance = this.pendingUtterance;
      this.pendingUtterance = "";
      this.coalesceTimer = null;
      this.triggerQuery(fullUtterance);
    }, this.coalesceDelayMs);
  }

  /**
   * Send speech query to local LiveBrief backend bridge with stale response guard.
   */
  async triggerQuery(queryText) {
    if (!queryText || !queryText.trim()) return;

    const thisRequestId = ++this.currentRequestId;
    this.isQuerying = true;
    this.setCopilotState("RETRIEVING", "Searching knowledge & verifying evidence...");
    this.showCopilotLoading(`Searching knowledge & verifying evidence for: "${queryText}"...`);

    try {
      const resp = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: queryText.trim(),
          session_id: this.sessionId,
        }),
      });

      // Discard stale responses if newer request was dispatched or operation was cancelled
      if (thisRequestId !== this.currentRequestId) {
        console.log(`[Copilot] Discarding stale response for request #${thisRequestId} (current: #${this.currentRequestId})`);
        return;
      }

      if (!resp.ok) {
        throw new Error(`HTTP error ${resp.status}`);
      }

      const data = await resp.json();

      if (thisRequestId !== this.currentRequestId) {
        return;
      }

      if (!data.triggered) {
        this.setCopilotState("READY", `Ignored fragment: "${queryText}"`);
        this.renderSuppressedUtterance(queryText, data.reason || "Non-substantive fragment");
        return;
      }

      if (data.event) {
        this.setCopilotState("READY", "Intelligence Ready");
        this.renderIntelligenceEvent(data.event);
      }
    } catch (err) {
      if (thisRequestId === this.currentRequestId) {
        console.error("Intelligence query failed:", err);
        this.setCopilotState("READY", `Query Error: ${err.message}`);
        this.renderCopilotError(queryText, err.message || "Failed to reach LiveBrief backend.");
      }
    } finally {
      if (thisRequestId === this.currentRequestId) {
        this.isQuerying = false;
      }
    }
  }

  showCopilotLoading(message) {
    this.ui.copilotPlaceholder.classList.add("hidden");
    this.ui.copilotContent.classList.remove("hidden");
    this.ui.copilotStatusText.textContent = message;
    this.ui.copilotSpinner.classList.remove("hidden");
  }

  /**
   * Render the structured IntelligenceResponseEvent in the compact side-panel.
   */
  renderIntelligenceEvent(event) {
    this.ui.copilotSpinner.classList.add("hidden");
    this.currentEvidenceSources = event.evidence_sources || [];

    // 1. Context & Active Query
    this.ui.copilotActiveQuery.textContent = event.query;
    if (event.contextual_query && event.contextual_query !== event.query) {
      this.ui.copilotContextTag.classList.remove("hidden");
      this.ui.copilotContextTag.textContent = `Context: ${event.contextual_query}`;
    } else {
      this.ui.copilotContextTag.classList.add("hidden");
    }

    // 2. Grounding Badge & Alerts
    if (event.has_sufficient_evidence) {
      this.ui.groundingBadge.className = "grounding-pill grounding-verified";
      this.ui.groundingBadge.innerHTML = `✓ ${Math.round(event.grounding_score * 100)}% Grounded (${event.supported_claims_count}/${event.total_claims_count} claims verified)`;
      this.ui.alertBox.classList.add("hidden");
    } else {
      this.ui.groundingBadge.className = "grounding-pill grounding-absent";
      this.ui.groundingBadge.innerHTML = `⚠️ Insufficient Evidence (0 fabricated claims)`;
      if (event.alerts && event.alerts.length > 0) {
        this.ui.alertBox.classList.remove("hidden");
        this.ui.alertText.textContent = event.alerts[0];
      }
    }

    // 3. Suggested Response with Clickable Interactive Citations
    this.ui.suggestedResponseText.innerHTML = this.formatInteractiveCitations(event.suggested_response);
    this.bindCitationButtons(this.ui.suggestedResponseText);

    // 4. Key Findings
    this.ui.keyFindingsContainer.innerHTML = "";
    if (event.key_findings && event.key_findings.length > 0) {
      this.ui.keyFindingsSection.classList.remove("hidden");
      event.key_findings.forEach((finding) => {
        const li = document.createElement("li");
        li.className = "finding-item";
        const cites = finding.citations
          .map((c) => `<button type="button" class="cite-anchor-btn" data-cite-id="${c}">[${c}]</button>`)
          .join(" ");
        li.innerHTML = `<span>${escapeHtml(finding.claim)}</span> ${cites}`;
        this.bindCitationButtons(li);
        this.ui.keyFindingsContainer.appendChild(li);
      });
    } else {
      this.ui.keyFindingsSection.classList.add("hidden");
    }

    // 5. Evidence & Sources Ledger (Clickable to open Evidence Explorer Modal)
    this.ui.evidenceLedgerContainer.innerHTML = "";
    if (this.currentEvidenceSources.length > 0) {
      this.ui.evidenceSection.classList.remove("hidden");
      this.currentEvidenceSources.forEach((src) => {
        const card = document.createElement("div");
        card.className = "evidence-card";
        card.id = `evidenceCard_${src.citation_id}`;
        card.setAttribute("data-cite-id", src.citation_id);
        card.innerHTML = `
          <div class="evidence-card-header">
            <span class="evidence-cite-id">[${src.citation_id}]</span>
            <span class="evidence-doc-id">${escapeHtml(src.doc_id)}</span>
            <span class="evidence-score">Relevance: ${src.relevance_score.toFixed(3)}</span>
          </div>
          <div class="evidence-excerpt">"${escapeHtml(src.excerpt)}"</div>
        `;
        card.addEventListener("click", () => this.openEvidenceModal(src));
        this.ui.evidenceLedgerContainer.appendChild(card);
      });
    } else {
      this.ui.evidenceSection.classList.add("hidden");
    }

    // 6. Contextual Follow-up Chips
    this.ui.followupsContainer.innerHTML = "";
    if (event.suggested_followups && event.suggested_followups.length > 0) {
      this.ui.followupsSection.classList.remove("hidden");
      event.suggested_followups.forEach((fText) => {
        const chip = document.createElement("button");
        chip.className = "followup-chip";
        chip.textContent = fText;
        chip.addEventListener("click", () => this.triggerQuery(fText));
        this.ui.followupsContainer.appendChild(chip);
      });
    } else {
      this.ui.followupsSection.classList.add("hidden");
    }

    // 7. Telemetry Breakdown
    const lat = event.latency;
    this.ui.telemetrySummary.textContent = `Moss: ${lat.moss_retrieval_ms.toFixed(2)}ms | MMR: ${lat.evidence_selection_ms.toFixed(2)}ms | Synthesis: ${lat.synthesis_ms.toFixed(2)}ms | Total E2E: ${event.e2e_voice_to_ui_ms.toFixed(1)}ms`;
  }

  formatInteractiveCitations(text) {
    if (!text) return "";
    const escaped = escapeHtml(text);

    // Split by lines to deterministically handle headings and paragraphs
    const lines = escaped.split(/\r?\n/);
    const formattedBlocks = [];
    let currentParagraph = [];

    const flushParagraph = () => {
      if (currentParagraph.length > 0) {
        formattedBlocks.push(`<p>${currentParagraph.join("<br>")}</p>`);
        currentParagraph = [];
      }
    };

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) {
        flushParagraph();
        continue;
      }

      const headingMatch = line.match(/^#{1,4}\s+(.+)$/);
      if (headingMatch) {
        flushParagraph();
        formattedBlocks.push(`<h4 class="response-heading">${headingMatch[1]}</h4>`);
      } else {
        currentParagraph.push(line);
      }
    }
    flushParagraph();

    const resultHtml = formattedBlocks.length > 0 ? formattedBlocks.join("") : escaped;

    return resultHtml.replace(
      /\[(\d+)\]/g,
      '<button type="button" class="cite-anchor-btn" data-cite-id="$1">[$1]</button>'
    );
  }

  bindCitationButtons(parentElement) {
    const buttons = parentElement.querySelectorAll(".cite-anchor-btn");
    buttons.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const citeId = btn.getAttribute("data-cite-id");
        this.highlightAndScrollEvidenceCard(citeId);
      });
    });
  }

  highlightAndScrollEvidenceCard(citeId) {
    const targetCard = document.getElementById(`evidenceCard_${citeId}`);
    if (targetCard) {
      targetCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      targetCard.classList.remove("evidence-highlight-pulse");
      // Trigger reflow to restart CSS animation
      void targetCard.offsetWidth;
      targetCard.classList.add("evidence-highlight-pulse");
    }
  }

  /**
   * Evidence Explorer Modal (In-Memory Provenance Drill-Down Without Re-Retrieval)
   */
  openEvidenceModal(source) {
    if (!this.ui.evidenceModal) return;

    const modalCitationId = document.getElementById("modalCitationId");
    const modalDocId = document.getElementById("modalDocId");
    const modalChunkId = document.getElementById("modalChunkId");
    const modalRelevanceScore = document.getElementById("modalRelevanceScore");
    const modalSourceUri = document.getElementById("modalSourceUri");
    const modalChunkContent = document.getElementById("modalChunkContent");

    if (modalCitationId) modalCitationId.textContent = `[${source.citation_id}]`;
    if (modalDocId) modalDocId.textContent = source.doc_id || "unknown";
    if (modalChunkId) modalChunkId.textContent = source.chunk_id || "unknown";
    if (modalRelevanceScore) modalRelevanceScore.textContent = source.relevance_score ? source.relevance_score.toFixed(4) : "0.0000";
    if (modalSourceUri) modalSourceUri.textContent = (source.metadata && source.metadata.source_uri) || source.source_uri || source.doc_id || "In-Memory Knowledge Base";
    if (modalChunkContent) modalChunkContent.textContent = source.excerpt || "No excerpt text available.";

    this.ui.evidenceModal.classList.remove("hidden");
  }

  closeEvidenceModal() {
    if (this.ui.evidenceModal) {
      this.ui.evidenceModal.classList.add("hidden");
    }
  }

  /**
   * Knowledge Base Drawer Controller (GET / POST / DELETE /api/documents)
   */
  openKbDrawer() {
    if (this.ui.kbDrawer) {
      this.ui.kbDrawer.classList.remove("hidden");
      this.loadDocuments();
    }
  }

  closeKbDrawer() {
    if (this.ui.kbDrawer) {
      this.ui.kbDrawer.classList.add("hidden");
    }
  }

  async loadDocuments() {
    try {
      const resp = await fetch("/api/documents");
      if (!resp.ok) return;

      const data = await resp.json();
      const docs = data.documents || [];

      if (this.ui.kbDocCountBadge) {
        this.ui.kbDocCountBadge.textContent = String(docs.length);
      }
      if (this.ui.kbListCount) {
        this.ui.kbListCount.textContent = String(docs.length);
      }

      this.renderDocumentList(docs);
    } catch (e) {
      console.warn("Failed to load documents list:", e);
    }
  }

  renderDocumentList(docs) {
    if (!this.ui.kbDocList) return;
    this.ui.kbDocList.innerHTML = "";

    if (docs.length === 0) {
      this.ui.kbDocList.innerHTML = '<div class="kb-empty">No documents registered. Ingest one above.</div>';
      return;
    }

    docs.forEach((doc) => {
      const card = document.createElement("div");
      card.className = "kb-doc-card";
      const dateStr = new Date(doc.indexed_at_ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

      card.innerHTML = `
        <div class="kb-doc-header">
          <span class="kb-doc-title">${escapeHtml(doc.title)}</span>
          <span class="kb-doc-badge badge-${doc.source_format}">${doc.source_format.toUpperCase()}</span>
        </div>
        <div class="kb-doc-stats">
          <span>Chunks: <strong>${doc.chunk_count}</strong></span>
          <span>Chars: <strong>${doc.total_characters}</strong></span>
          <span>Indexed: <strong>${dateStr}</strong></span>
        </div>
        <div class="kb-doc-actions">
          <span class="kb-doc-id">ID: ${escapeHtml(doc.doc_id)}</span>
          <button class="btn btn-danger btn-sm btn-delete-doc" data-doc-id="${escapeHtml(doc.doc_id)}">Delete</button>
        </div>
      `;

      const deleteBtn = card.querySelector(".btn-delete-doc");
      if (deleteBtn) {
        deleteBtn.addEventListener("click", () => this.deleteDocument(doc.doc_id, doc.title));
      }

      this.ui.kbDocList.appendChild(card);
    });
  }

  async indexDocument() {
    const titleInput = document.getElementById("kbDocTitle");
    const formatSelect = document.getElementById("kbDocFormat");
    const contentTextarea = document.getElementById("kbDocContent");
    const alertBox = document.getElementById("kbAlertBox");
    const alertText = document.getElementById("kbAlertText");

    const title = titleInput ? titleInput.value.trim() : "";
    const format = formatSelect ? formatSelect.value : "markdown";
    const content = contentTextarea ? contentTextarea.value.trim() : "";

    if (!title || !content) {
      if (alertBox && alertText) {
        alertText.textContent = "Please provide both a Document Title and Content.";
        alertBox.classList.remove("hidden");
      }
      return;
    }

    if (alertBox) alertBox.classList.add("hidden");

    try {
      const resp = await fetch("/api/documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          content,
          format,
        }),
      });

      const data = await resp.json();

      if (!resp.ok) {
        if (alertBox && alertText) {
          alertText.textContent = data.error || `Server error (${resp.status})`;
          alertBox.classList.remove("hidden");
        }
        return;
      }

      // Success
      if (titleInput) titleInput.value = "";
      if (contentTextarea) contentTextarea.value = "";
      if (alertBox) alertBox.classList.add("hidden");
      await this.loadDocuments();
    } catch (e) {
      if (alertBox && alertText) {
        alertText.textContent = `Network error: ${e.message}`;
        alertBox.classList.remove("hidden");
      }
    }
  }

  async deleteDocument(docId, title) {
    if (!confirm(`Are you sure you want to remove "${title}" from the knowledge base?`)) {
      return;
    }

    try {
      const resp = await fetch(`/api/documents/${encodeURIComponent(docId)}`, {
        method: "DELETE",
      });

      if (resp.ok) {
        await this.loadDocuments();
      } else {
        const data = await resp.json();
        alert(data.error || "Failed to delete document.");
      }
    } catch (e) {
      alert(`Network error deleting document: ${e.message}`);
    }
  }

  renderSuppressedUtterance(queryText, reason) {
    this.ui.copilotSpinner.classList.add("hidden");
    this.ui.copilotStatusText.textContent = `Ignored fragment: "${queryText}" (${reason})`;
  }

  renderCopilotError(queryText, errorMessage) {
    this.ui.copilotSpinner.classList.add("hidden");
    this.ui.copilotStatusText.textContent = `Query Error: ${errorMessage}`;
    this.ui.alertBox.classList.remove("hidden");
    this.ui.alertText.textContent = `Failed to process query "${queryText}": ${errorMessage}`;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Instantiate Copilot Controller on DOM load
document.addEventListener("DOMContentLoaded", () => {
  const copilotUI = {
    copilotPlaceholder: document.getElementById("copilotPlaceholder"),
    copilotContent: document.getElementById("copilotContent"),
    copilotSpinner: document.getElementById("copilotSpinner"),
    copilotStatusText: document.getElementById("copilotStatusText"),
    copilotActiveQuery: document.getElementById("copilotActiveQuery"),
    copilotContextTag: document.getElementById("copilotContextTag"),
    groundingBadge: document.getElementById("groundingBadge"),
    alertBox: document.getElementById("alertBox"),
    alertText: document.getElementById("alertText"),
    suggestedResponseText: document.getElementById("suggestedResponseText"),
    keyFindingsSection: document.getElementById("keyFindingsSection"),
    keyFindingsContainer: document.getElementById("keyFindingsContainer"),
    evidenceSection: document.getElementById("evidenceSection"),
    evidenceLedgerContainer: document.getElementById("evidenceLedgerContainer"),
    followupsSection: document.getElementById("followupsSection"),
    followupsContainer: document.getElementById("followupsContainer"),
    telemetrySummary: document.getElementById("telemetrySummary"),
    manualQueryInput: document.getElementById("manualQueryInput"),
    manualQueryBtn: document.getElementById("manualQueryBtn"),
    evidenceModal: document.getElementById("evidenceModal"),
    closeEvidenceModalBtn: document.getElementById("closeEvidenceModalBtn"),
    kbDrawer: document.getElementById("kbDrawer"),
    kbToggleBtn: document.getElementById("kbToggleBtn"),
    closeKbDrawerBtn: document.getElementById("closeKbDrawerBtn"),
    kbDocCountBadge: document.getElementById("kbDocCountBadge"),
    kbListCount: document.getElementById("kbListCount"),
    kbDocList: document.getElementById("kbDocList"),
    kbIndexBtn: document.getElementById("kbIndexBtn"),
    kbRefreshBtn: document.getElementById("kbRefreshBtn"),
  };

  window.copilotController = new LiveBriefCopilotController(copilotUI);
});
