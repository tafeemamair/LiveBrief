/**
 * LiveBrief Intelligence Copilot Controller (Phase 2.2)
 * Manages utterance coalescing, API query execution, and compact copilot card rendering.
 */

class LiveBriefCopilotController {
  constructor(uiElements) {
    this.ui = uiElements;
    this.sessionId = `sess_${Date.now().toString(36)}`;
    this.coalesceTimer = null;
    this.coalesceDelayMs = 600; // 600ms debounce/coalescing window
    this.pendingUtterance = "";
    this.isQuerying = false;

    this.bindEvents();
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

    this.showCopilotLoading("Listening... Coalescing speech utterance");

    this.coalesceTimer = setTimeout(() => {
      const fullUtterance = this.pendingUtterance;
      this.pendingUtterance = "";
      this.triggerQuery(fullUtterance);
    }, this.coalesceDelayMs);
  }

  /**
   * Send speech query to local LiveBrief backend bridge.
   */
  async triggerQuery(queryText) {
    if (!queryText || !queryText.trim()) return;

    this.showCopilotLoading(`Analyzing: "${queryText}"...`);
    this.isQuerying = true;

    try {
      const resp = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: queryText.trim(),
          session_id: this.sessionId,
        }),
      });

      if (!resp.ok) {
        throw new Error(`HTTP error ${resp.status}`);
      }

      const data = await resp.json();

      if (!data.triggered) {
        this.renderSuppressedUtterance(queryText, data.reason || "Non-substantive fragment");
        return;
      }

      if (data.event) {
        this.renderIntelligenceEvent(data.event);
      }
    } catch (err) {
      console.error("Intelligence query failed:", err);
      this.renderCopilotError(queryText, err.message || "Failed to reach LiveBrief backend.");
    } finally {
      this.isQuerying = false;
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
    this.ui.copilotStatusText.textContent = "Intelligence Ready";

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

    // 3. Suggested Response
    this.ui.suggestedResponseText.innerHTML = formatCitations(event.suggested_response);

    // 4. Key Findings
    this.ui.keyFindingsContainer.innerHTML = "";
    if (event.key_findings && event.key_findings.length > 0) {
      this.ui.keyFindingsSection.classList.remove("hidden");
      event.key_findings.forEach((finding) => {
        const li = document.createElement("li");
        li.className = "finding-item";
        const cites = finding.citations.map((c) => `<span class="cite-anchor">[${c}]</span>`).join(" ");
        li.innerHTML = `<span>${escapeHtml(finding.claim)}</span> ${cites}`;
        this.ui.keyFindingsContainer.appendChild(li);
      });
    } else {
      this.ui.keyFindingsSection.classList.add("hidden");
    }

    // 5. Evidence & Sources Ledger
    this.ui.evidenceLedgerContainer.innerHTML = "";
    if (event.evidence_sources && event.evidence_sources.length > 0) {
      this.ui.evidenceSection.classList.remove("hidden");
      event.evidence_sources.forEach((src) => {
        const card = document.createElement("div");
        card.className = "evidence-card";
        card.innerHTML = `
          <div class="evidence-card-header">
            <span class="evidence-cite-id">[${src.citation_id}]</span>
            <span class="evidence-doc-id">${escapeHtml(src.doc_id)}</span>
            <span class="evidence-score">Relevance: ${src.relevance_score.toFixed(3)}</span>
          </div>
          <div class="evidence-excerpt">"${escapeHtml(src.excerpt)}"</div>
        `;
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

function formatCitations(text) {
  if (!text) return "";
  return escapeHtml(text).replace(/\[(\d+)\]/g, '<span class="cite-anchor">[$1]</span>');
}

function escapeHtml(str) {
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
  };

  window.copilotController = new LiveBriefCopilotController(copilotUI);
});
