# LiveBrief

LiveBrief is a low-latency, real-time AI research and briefing engine. It delivers rapid, structured, and factual briefing responses backed by strict evidence citations over dynamic knowledge bases.

---

## Phase 2 — Live Intelligence Copilot (Web & Voice)

Phase 2 connects the high-performance retrieval pipeline to an interactive browser-based intelligence copilot with real-time speech streaming, dynamic document management, and interactive evidence provenance.

### Core Architecture & Execution Flow
```
User (Voice / Text) ──▶ Utterance Gate ──▶ Context Resolver ──▶ Moss Hybrid Retrieval (<1ms)
                                                                      │
UI (Grounded Brief + Citations) ◀── Grounded Synthesizer ◀── MMR Evidence Selector (<2ms)
```

1. **Speech / Text Input**: Browser captures natural speech streaming via Web Speech API or manual query input.
2. **Utterance Classification Gate**: Suppresses filler words and incomplete fragments before triggering search.
3. **Conversational Context**: Anchors follow-up questions (e.g., *"What about its latency?"*) while ensuring fresh retrieval executes on every turn.
4. **In-Process Moss Engine**: Utilizes embedded `moss` (`moss_core.Index`) Rust-based retrieval runtime for sub-millisecond hybrid BM25 and dense vector search on the hot path without external network round trips.
5. **MMR Evidence Selection**: Deduplicates retrieved chunks using Maximal Marginal Relevance and extracts salient sentence spans within strict token budgets.
6. **Strict Grounding & Abstention**: Every generated finding is tied to clickable citation markers (`[1]`, `[2]`). If evidence is missing or below the relevance threshold, the system explicitly reports insufficient context instead of speculating.
7. **Interactive Provenance**: Clicking citation badges highlights the source excerpt in the ledger, and clicking the evidence card opens the Evidence Explorer modal for chunk-level provenance.

---

## Quickstart

### 1. Installation & Environment Setup
```powershell
# Create and activate virtual environment (Python 3.13 recommended)
py -3.13 -m venv .venv
.venv\Scripts\activate

# Install dependencies in editable mode
pip install -e .
```

### 2. Launch the Web & Voice Intelligence Copilot
```powershell
.\.venv\Scripts\python.exe -m livebrief.cli serve-voice --port 8000
```
Open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** in **Google Chrome** or **Microsoft Edge** (required for browser-native Web Speech API microphone streaming).

### 3. Querying via CLI
```powershell
.\.venv\Scripts\python.exe -m livebrief.cli query "What are the latency budgets and architecture?" --files samples/sample_knowledge.md
```

### 4. Benchmarking In-Process Moss Retrieval Latency
```powershell
.\.venv\Scripts\python.exe -m livebrief.cli benchmark --files samples/sample_knowledge.md --iterations 50
```

### 5. Running the Test Suite
```powershell
.\.venv\Scripts\pytest.exe -v
```
