# LiveBrief Phase 2.3 Implementation Plan: Real-Time Intelligence Copilot Experience (Revised)

## Executive Summary & Objective

Phase 2.3 elevates the verified, sub-10ms voice-to-Moss pipeline from Phase 2.2 into a polished, resilient, and interactive real-time intelligence copilot experience.

This revised plan incorporates strict architectural corrections:
1. **Truthful Intelligence State UX**: The UI lifecycle reflects actual synchronous HTTP request milestones (`LISTENING` → `UNDERSTANDING` → `RETRIEVING + VERIFYING` → `READY`), without artificial delays, fake progression timers, or streaming/WebSocket backend redesigns.
2. **Frozen Adapter & Engine Foundation**: `livebrief/voice/adapter.py` and the `IntelligenceResponseEvent` contract remain strictly **FROZEN**. UI states are derived client-side from actual network and speech lifecycle events.
3. **Factual Privacy Boundaries**: Accurately clarifies that LiveBrief never uploads raw audio to its own backend and processes retrieval/evidence strictly in-process, while noting that browser-native Web Speech API speech-to-text operates under the browser vendor's platform capabilities.
4. **Document Registry Architecture**: Introduces a dedicated in-memory `DocumentRegistry` in `livebrief/voice/documents.py` that maps document-level metadata, lifecycle state, and associated chunk IDs to `MossIndexer` for deterministic addition and deletion.
5. **Deterministic JSON Ingestion**: Defines predictable, sorted-key JSON serialization before feeding existing `TextChunker`, returning HTTP 422 for malformed inputs.
6. **Fresh Retrieval for Contextual Follow-ups**: Guarantees that conversation context serves purely as a query-formulation aid; every follow-up executes fresh Moss hybrid retrieval and MMR evidence validation, strictly preventing answers from ungrounded session memory.
7. **Serialized Concurrency & Reliability**: Validates single-threaded `socketserver.TCPServer` request serialization, stale-response protection via request sequence IDs, safe debounce cancellation on `Stop`, and robust error handling.
8. **Separated Latency Targets**: Distinguishes server-side engineering targets (<5ms retrieval, <10ms MMR, <15ms total pipeline) from observed browser end-to-end measurements.

---

## Strict Frozen Boundary Invariants

The following components are **FROZEN** and will NOT be modified, bypassed, or replaced:

- **Phase 1 Retrieval & Grounding Core**:
  - `livebrief/moss/indexer.py`: `MossIndexer` remains the single in-process Rust `moss_core` wrapper.
  - `livebrief/moss/embedder.py`: `DeterministicEmbedder` / `BaseEmbedder` remain vector generation foundations.
  - `livebrief/retrieval/retriever.py`: `MossSemanticRetriever` remains the hybrid retriever.
  - `livebrief/evidence/selector.py`: `EvidenceSelector` remains the greedy MMR deduplication engine with token budgeting.
  - `livebrief/synthesis/grounder.py`: `GroundedSynthesizer` remains the deterministic citation anchor and grounding validator.
  - `livebrief/pipeline.py`: `LiveBriefPipeline` remains the central orchestrator.
- **Phase 2.1 Voice Foundation**:
  - `livebrief/voice/models.py`: `VoiceState`, `TranscriptSegment`, `VoiceSessionMetrics`, `VoiceEvent`.
  - `livebrief/voice/state_machine.py`: `VoiceActivationStateMachine` explicit state transition logic.
  - `web/stt.js`: Browser-native Web Speech API and local `AudioContext`/`AnalyserNode` VU metering.
- **Phase 2.2 Integration Core**:
  - `livebrief/voice/utterance.py`: `UtteranceDetector` classification engine.
  - `livebrief/voice/adapter.py`: `VoicePipelineAdapter` bridging speech to `LiveBriefPipeline` and `IntelligenceResponseEvent` data contract.

---

## 1. Current Architecture Inspection & Concurrency Model

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          BROWSER CLIENT                                                │
│                                                                                                        │
│  ┌───────────────────────────────┐     ┌────────────────────────────────────────────────────────────┐  │
│  │   LiveBriefSpeechController   │     │                 LiveBriefCopilotController                 │  │
│  │  - Web Speech API             │     │  - 600ms Utterance Coalescing                              │  │
│  │  - Local VU Metering          │────▶│  - Client-Driven Request Lifecycle UI                      │  │
│  │  - Start / Stop Lifecycle     │     │    [LISTENING -> UNDERSTANDING -> RETRIEVING -> READY]     │  │
│  │  - Stop Discards In-Flight    │     │  - Stale Response Sequence Guard (req_id counter)          │  │
│  └───────────────────────────────┘     │  - Evidence Explorer (Provenance inspection, no re-query)  │  │
│                                        │  - Document Registry UI (List, Ingest, Delete)             │  │
│                                        └─────────────────────────────┬──────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┼─────────────────────────────────┘
                                                                       │ Synchronous HTTP POST /api/query
                                                                       │ Synchronous HTTP GET/POST/DELETE
                                                                       │   /api/documents
┌──────────────────────────────────────────────────────────────────────▼─────────────────────────────────┐
│                                     LIVEBRIEF BACKEND SERVER                                           │
│                       (Single-Threaded socketserver.TCPServer - Serialized Execution)                  │
│                                                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ LiveBriefHTTPHandler                                                                             │  │
│  │                                                                                                  │  │
│  │   ├── POST /api/query                                                                            │  │
│  │   │     │                                                                                        │  │
│  │   │     ▼                                                                                        │  │
│  │   │   VoicePipelineAdapter.process_speech_utterance()                                            │  │
│  │   │     ├── 1. UtteranceDetector.classify()                                                      │  │
│  │   │     ├── 2. SessionContextManager.resolve_query() (Query formulation aid only)                │  │
│  │   │     └── 3. LiveBriefPipeline.query()                                                         │  │
│  │   │              ├── MossSemanticRetriever (moss_core.Index) ──▶ Fresh Hybrid Search (<5ms)      │  │
│  │   │              ├── EvidenceSelector (MMR Deduplication)    ──▶ Verified Evidence (<10ms)      │  │
│  │   │              └── GroundedSynthesizer                     ──▶ Grounded Brief + Citations      │  │
│  │   │                                                                                              │  │
│  │   ├── Document Management (via DocumentRegistry):                                                │  │
│  │   │     ├── GET    /api/documents       ──▶ DocumentRegistry.list_documents()                    │  │
│  │   │     ├── POST   /api/documents       ──▶ DocumentRegistry.ingest() ──▶ IngestionPipeline      │  │
│  │   │     │                                                                 ──▶ MossIndexer.add()  │  │
│  │   │     └── DELETE /api/documents/{id}  ──▶ DocumentRegistry.delete() ──▶ MossIndexer.delete()   │  │
│  └──────────────────────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. File Boundary: Exact Modified and New Files

### Files to Modify:
| File Path | Status | Justification / Minimal Changes |
|---|---|---|
| [`livebrief/voice/server.py`](file:///e:/coding/LiveBrief/livebrief/voice/server.py) | **Modify** | Add REST routing for `GET /api/documents`, `POST /api/documents`, `DELETE /api/documents/{doc_id}` wired to `DocumentRegistry`. Handle malformed JSON / oversized payload errors. |
| [`livebrief/voice/context.py`](file:///e:/coding/LiveBrief/livebrief/voice/context.py) | **Modify** | Polish anaphoric query rewriting rules (e.g., "what about its latency?", "why is that?") to formulate precise search queries without ever treating session history as evidence. |
| [`web/index.html`](file:///e:/coding/LiveBrief/web/index.html) | **Modify** | Add DOM containers for: (1) Request Lifecycle Status Indicator, (2) Evidence Explorer Modal/Drawer, (3) Document Management Drawer. |
| [`web/copilot.js`](file:///e:/coding/LiveBrief/web/copilot.js) | **Modify** | Implement client-driven state transitions, request sequencing (stale response protection), citation click-to-highlight/drawer, Document Registry REST integration, and debounce cancellation on `Stop`. |
| [`web/styles.css`](file:///e:/coding/LiveBrief/web/styles.css) | **Modify** | Add styling for Evidence Explorer modal, highlighted evidence spans, document management table/drawer, and state status pills. |

### Exact New Files Required:
| New File Path | Purpose / Description |
|---|---|
| `livebrief/voice/documents.py` | In-memory `DocumentRegistry` class: tracks document records, manages format validation (Markdown, Text, deterministic JSON), maps `doc_id` to chunk IDs, and coordinates additions/deletions with `MossIndexer`. |
| `tests/test_document_manager.py` | Unit tests for `DocumentRegistry`: document registration, chunk ID tracking, deterministic JSON parsing, format validation, deterministic chunk deletion, and duplicate handling. |
| `tests/test_copilot_interactions.py` | Integration tests verifying contextual follow-up query formulation, stale response guard logic, stop/debounce cancellation, and error handling. |

### Explicitly FROZEN Files (MUST NOT Be Modified):
- [`livebrief/moss/indexer.py`](file:///e:/coding/LiveBrief/livebrief/moss/indexer.py)
- [`livebrief/moss/embedder.py`](file:///e:/coding/LiveBrief/livebrief/moss/embedder.py)
- [`livebrief/retrieval/retriever.py`](file:///e:/coding/LiveBrief/livebrief/retrieval/retriever.py)
- [`livebrief/evidence/selector.py`](file:///e:/coding/LiveBrief/livebrief/evidence/selector.py)
- [`livebrief/synthesis/grounder.py`](file:///e:/coding/LiveBrief/livebrief/synthesis/grounder.py)
- [`livebrief/pipeline.py`](file:///e:/coding/LiveBrief/livebrief/pipeline.py)
- [`livebrief/voice/state_machine.py`](file:///e:/coding/LiveBrief/livebrief/voice/state_machine.py)
- [`livebrief/voice/models.py`](file:///e:/coding/LiveBrief/livebrief/voice/models.py)
- [`livebrief/voice/adapter.py`](file:///e:/coding/LiveBrief/livebrief/voice/adapter.py) *(Frozen: IntelligenceResponseEvent and process_speech_utterance remain as finalized in Phase 2.2)*
- [`livebrief/voice/utterance.py`](file:///e:/coding/LiveBrief/livebrief/voice/utterance.py)

---

## 3. Workstream Specifications

### 2.3.1 Intelligence State UX (Truthful Request Lifecycle)

The UI reflects the genuine state of the client and server without synthetic timers or fake progressive stages:

1. **`LISTENING`**:
   - Browser microphone is actively capturing audio via Web Speech API (`SpeechRecognition`).
   - VU level meter is active. Status reads: `"Listening for speech..."`.
2. **`UNDERSTANDING`**:
   - A finalized transcript segment is emitted by STT and coalesced (600ms window).
   - `UtteranceDetector` classifies the segment.
   - If classified as a substantive query or follow-up, UI displays: `"Understanding query: '<utterance>'..."`.
   - If classified as `FILLER` or `FRAGMENT`, UI shows subtle dismissal toast and returns to `LISTENING`.
3. **`RETRIEVING + VERIFYING`**:
   - The HTTP POST `/api/query` request is actively in flight over the wire.
   - Backend is executing `VoicePipelineAdapter.process_speech_utterance()` (Moss hybrid search + MMR selection + grounded synthesis).
   - UI displays: `"Searching knowledge & verifying evidence..."` with an active spinner.
4. **`READY`**:
   - The HTTP response returns successfully with `IntelligenceResponseEvent`.
   - UI renders executive summary, key findings, evidence citations, follow-up chips, and measured latency telemetry. Status reads: `"Intelligence Ready"`.
5. **`ERROR` / `ABSTAINED`**:
   - If request fails, renders error message in alert box.
   - If evidence is insufficient, renders `"⚠️ Insufficient Evidence (0 fabricated claims)"` with abstention caveats.

**Stale Response Protection Invariant**:
- Each dispatched `/api/query` increments a client-side `currentRequestId` integer.
- Responses returning with `requestId < currentRequestId` are safely discarded to prevent out-of-order race conditions from overwriting newer speech responses.

---

### 2.3.2 Evidence Explorer (Provenance Drill-Down Without Re-Retrieval)

1. **Clickable Citations**:
   - Citations `[1]`, `[2]` in Suggested Response and Key Findings are rendered as interactive buttons.
2. **Bidirectional Interaction**:
   - **Clicking `[n]` badge**: Smoothly scrolls the Evidence & Sources Ledger to card `[n]` and applies a CSS highlight pulse.
   - **Clicking Evidence Card**: Opens the **Evidence Explorer Drawer/Modal**, presenting:
     - Document Title & Source URI (`src.source_uri` / `src.metadata.title`)
     - Document ID (`src.doc_id`) & Chunk ID (`src.chunk_id`)
     - Exact Retrieved Excerpt with highlighted salient spans
     - Exact Moss relevance score (`src.relevance_score`)
3. **Strict No Re-Retrieval Invariant**:
   - The Evidence Explorer operates strictly against the `evidence_sources` array already provided in the `IntelligenceResponseEvent`. Zero secondary network calls, zero secondary vector lookups, and zero custom client-side ranking.

---

### 2.3.3 Contextual Conversation (Fresh Retrieval Guarantee)

1. **Query Formulation Assistance Only**:
   - `SessionContextManager` stores the last $N=5$ successful query turns (`original_query`, `resolved_query`, `summary`).
   - When incoming speech is classified as `FOLLOW_UP` (e.g., *"Why?"*, *"What about its latency?"*, *"How does that safeguard work?"*), the context manager formulates an anchored query string:
     `f"{clean_text} [Context: {last_turn.original_query}]"`
2. **Fresh Retrieval & Evidence Boundary**:
   - **Context is NEVER evidence**: Prior conversational turn summaries are never injected into the knowledge base or treated as verified evidence.
   - Every contextual query is dispatched as a fresh `QueryRequest` through `LiveBriefPipeline.query()`, executing:
     - Fresh `moss_core.Index` hybrid vector/BM25 retrieval.
     - Fresh `EvidenceSelector` MMR deduplication and relevance scoring.
     - Fresh `GroundedSynthesizer` factual verification.
   - If the newly formulated query does not match verified indexed documents in Moss, the system strictly returns `has_sufficient_evidence = False` with 0 fabricated claims.
3. **Clean Session Reset**:
   - Calling `SessionContextManager.clear()` or resetting the UI session empties context history, guaranteeing zero topic leakage across sessions.

---

### 2.3.4 Private Knowledge Base (In-Memory Document Registry & Deterministic Ingestion)

#### Architecture:
```
DocumentRegistry (livebrief/voice/documents.py)
  ├── _documents: Dict[doc_id, DocumentRecord]
  │     ├── doc_id: str
  │     ├── title: str
  │     ├── source_format: "markdown" | "json" | "text"
  │     ├── chunk_count: int
  │     ├── total_characters: int
  │     ├── indexed_at_ms: float
  │     └── chunk_ids: List[str]
  │
  ├── ingest_document(title, content, format)
  │     ├── 1. Validate format & content
  │     ├── 2. Deterministic serialization (sorted keys for JSON)
  │     ├── 3. IngestionPipeline.ingest_text() -> (doc, chunks)
  │     ├── 4. MossIndexer.add_chunks(chunks)
  │     └── 5. Register in _documents with chunk_ids
  │
  └── delete_document(doc_id)
        ├── 1. Lookup DocumentRecord -> chunk_ids
        ├── 2. MossIndexer.delete_chunks(chunk_ids)
        └── 3. Remove from _documents
```

#### Deterministic JSON Ingestion Semantics:
- When ingesting a JSON document, the payload is parsed via `json.loads()`.
- If parsing fails, the endpoint returns **HTTP 422 Unprocessable Entity** with `{"error": "Invalid JSON syntax: <details>"}`.
- Valid JSON is converted into a deterministic string representation using sorted keys and standard 2-space indentation:
  `text_content = json.dumps(parsed_json, sort_keys=True, indent=2, ensure_ascii=False)`
- The formatted text is then processed by the existing `TextChunker` and indexed into `MossIndexer`.
- Arbitrary `str(json_dict)` is strictly prohibited.

#### REST Endpoints in `livebrief/voice/server.py`:
1. `GET /api/documents`: Returns list of all registered documents with chunk counts and character stats.
2. `POST /api/documents`: Ingests new text/Markdown/JSON document, chunks and indexes it into Moss, updates registry.
3. `DELETE /api/documents/{doc_id}`: Removes all chunks associated with `doc_id` from Moss and updates registry.

---

### 2.3.5 Reliability, Concurrency & Lifecycle Hardening

1. **Serialized TCPServer Concurrency Model**:
   - `socketserver.TCPServer` processes one request at a time sequentially on the main server thread.
   - Preserves 100% thread confinement for the native Rust `moss_core.Index`.
2. **Stop / Debounce Safety**:
   - Clicking `Stop` immediately:
     - Cancels active JavaScript `coalesceTimer` (`clearTimeout`).
     - Sets `isQuerying = false` and increments `currentRequestId` so in-flight responses are ignored upon arrival.
     - Calls `teardownAudio()`, terminating Web Speech API and closing hardware MediaStream tracks.
3. **Structured Server Error Handling**:
   - Malformed JSON in `/api/query` -> HTTP 400 Bad Request.
   - Malformed JSON in `/api/documents` -> HTTP 422 Unprocessable Entity.
   - Missing document on DELETE -> HTTP 404 Not Found.
   - Internal pipeline errors -> HTTP 500 Internal Server Error with structured JSON `{ "error": "<msg>" }`.

---

## 4. Latency Targets vs. Observability

| Pipeline Stage | Engineering Target | Measurement Method |
|---|---|---|
| **Moss Hybrid Retrieval** | **< 5.0 ms** *(target)* | Server `LatencyTracker` (`time.perf_counter_ns()`) |
| **Evidence Selection (MMR)** | **< 10.0 ms** *(target)* | Server `LatencyTracker` (`time.perf_counter_ns()`) |
| **Grounded Response Synthesis** | **< 5.0 ms** *(target)* | Server `LatencyTracker` (`time.perf_counter_ns()`) |
| **Total Backend Intelligence** | **< 15.0 ms** *(target)* | Server `LatencyTracker` (`time.perf_counter_ns()`) |
| **Observed Browser E2E Latency** | *Measured per run* | JavaScript timestamp (`Date.now()` from query dispatch to UI render) |

> [!NOTE]
> Server latency targets are internal engineering benchmarks. Browser E2E latency depends on browser scheduling, network loopback, and UI DOM rendering, and will be measured and reported directly from the live browser test environment.

---

## 5. Security & Privacy Facts

- **LiveBrief Application Scope**:
  - LiveBrief does **NOT** upload raw microphone audio to its backend or any external cloud server.
  - Ingestion, text chunking, deterministic embedding, Moss indexing, MMR selection, and synthesis occur **100% locally and in-process** on `127.0.0.1`.
- **Browser STT Platform Nuance**:
  - Speech-to-text is performed via the browser's native Web Speech API (`window.SpeechRecognition` / `window.webkitSpeechRecognition`).
  - Depending on the browser engine (e.g. Google Chrome vs. Safari vs. local Edge offline model), speech transcription may be processed locally or via browser-managed platform speech services. LiveBrief itself receives only the resulting text transcript segments.

---

## 6. Scope Boundaries

### Explicitly IN SCOPE (Phase 2.3):
- Truthful request-driven UI lifecycle state progression.
- Stale response guard and safe debounce cancellation on `Stop`.
- Interactive Evidence Explorer (citation click to highlight/inspect).
- Fresh-retrieval contextual follow-up conversation formulation.
- In-memory `DocumentRegistry` with Markdown/Text/JSON ingestion and deterministic chunk deletion.
- Deterministic sorted-key JSON serialization and HTTP 422 validation.
- Serialized TCPServer concurrency verification and error hardening.
- Comprehensive automated regression tests and browser E2E test plan.

### Explicitly OUT OF SCOPE (Phase 2.3):
- ❌ Second vector database (Chroma, FAISS, Pinecone, SQLite vector).
- ❌ Custom BM25 or vector ranking outside `moss_core`.
- ❌ GitHub repository scrapers or web crawlers.
- ❌ Cloud retrieval or external cloud LLM dependencies.
- ❌ Passive always-on listening.
- ❌ Multi-speaker diarization / voice identification.
- ❌ Meeting audio summarization.
- ❌ Desktop native application / browser extension.
- ❌ General-purpose long-term memory across sessions.
- ❌ Streaming backend architecture / WebSocket / Server-Sent Events migration.
- ❌ Phase 3 multi-agent or audio streaming features.

---

## 7. Test Plan & Regression Strategy

### Existing Baseline:
- 51 / 51 tests passing (`tests/test_*.py`).
- Overall coverage baseline: **91%**.

### New Phase 2.3 Automated Test Suites:

#### 1. `tests/test_document_manager.py` (New)
- `test_document_registry_ingest_markdown`: Ingest Markdown, verify chunk count and metadata.
- `test_document_registry_ingest_text`: Ingest plain text document.
- `test_document_registry_ingest_json_deterministic`: Verify stable sorted-key JSON formatting before chunking.
- `test_document_registry_rejects_malformed_json`: Verify invalid JSON raises structured validation error.
- `test_document_registry_delete_removes_moss_chunks`: Verify deleting a document removes all associated chunks from Moss so they can no longer be retrieved.
- `test_document_registry_readd_lifecycle`: Verify add -> delete -> re-add cycle behaves deterministically.

#### 2. `tests/test_copilot_interactions.py` (New)
- `test_contextual_followup_fresh_retrieval`: Verify follow-up queries execute fresh Moss retrieval and evidence validation.
- `test_contextual_followup_absent_evidence_abstains`: Verify follow-up with absent evidence returns 0 claims.
- `test_session_context_clear_isolation`: Verify `clear()` resets history completely.
- `test_server_documents_api_get_post_delete`: Test `/api/documents` REST endpoints.
- `test_server_handles_malformed_query_json`: Verify HTTP 400 on malformed query body.
- `test_server_handles_malformed_document_json`: Verify HTTP 422 on invalid document JSON.
- `test_server_rapid_sequential_requests`: Verify single-threaded TCPServer handles rapid requests without state corruption.

---

## 8. Sequential Implementation Order & Verification Checkpoints

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Step 1: DocumentRegistry & Private Knowledge Base Backend                  │
│   - Create livebrief/voice/documents.py (DocumentRegistry, DocumentRecord) │
│   - Extend livebrief/voice/server.py with GET/POST/DELETE /api/documents   │
│   - Create tests/test_document_manager.py                                  │
│   - CHECKPOINT 1: Run pytest, verify all doc registry tests pass.          │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      │
┌─────────────────────────────────────▼──────────────────────────────────────┐
│ Step 2: Contextual Conversation Polish & Integration Tests                 │
│   - Refine livebrief/voice/context.py anaphoric query rewriting            │
│   - Create tests/test_copilot_interactions.py                              │
│   - CHECKPOINT 2: Run pytest, verify follow-up & fresh retrieval tests.    │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      │
┌─────────────────────────────────────▼──────────────────────────────────────┐
│ Step 3: UI Intelligence State UX, Evidence Explorer & Knowledge Drawer     │
│   - Update web/index.html with request state pill, explorer modal, drawer  │
│   - Update web/copilot.js with stale-guard, citation click, doc manager UI │
│   - Update web/styles.css with dark-mode styling and animations            │
│   - CHECKPOINT 3: Validate UI in test server; test debounce cancel.        │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      │
┌─────────────────────────────────────▼──────────────────────────────────────┐
│ Step 4: Full Regression & Phase 2.3 Verification                           │
│   - Run .venv\Scripts\pytest -v --cov=livebrief                            │
│   - Confirm >= 60 tests pass, coverage >= 91%, zero git boundary leaks.    │
│   - CHECKPOINT 4: Ready for Phase 2.3 freeze.                              │
└────────────────────────────────────────────────────────────────────────────┘
```
