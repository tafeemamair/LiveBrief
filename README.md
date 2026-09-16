# LiveBrief

LiveBrief is a low-latency, real-time AI research and briefing engine. It delivers rapid, structured, and factual briefing responses backed by strict evidence citations.

## Phase 1: Retrieval Vertical Slice

Phase 1 establishes the core pipeline with zero UI or voice layer dependencies:
**Document Ingestion → Moss Native Indexing → Semantic Retrieval → Evidence Selection → Structured Grounded Brief**

### Key Features
- **In-Process Moss Engine**: Utilizes `moss` (`moss_core.Index`) Rust-based retrieval runtime for sub-10ms search without external network round trips.
- **Hybrid Retrieval**: Combines keyword BM25 search with dense semantic embeddings via configurable $\alpha$ weight.
- **Maximal Marginal Relevance (MMR)**: Suppresses redundant chunks and extracts sentence-level salient spans.
- **Strict Grounding & Hallucination Defense**: Every finding is tied to citation markers (`[1]`, `[2]`), with an automated grounding metric and graceful abstention when evidence is absent.
- **Sub-Millisecond Telemetry**: High-precision stage-by-stage latency instrumentation.

## Quickstart

### 1. Installation
```powershell
# Create and activate virtual environment
py -3.13 -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -e .
```

### 2. Querying Knowledge Documents
```powershell
python -m livebrief.cli query "What are the latency budgets and architecture?" --files samples/sample_knowledge.md
```

### 3. Benchmarking Moss Retrieval Latency
```powershell
python -m livebrief.cli benchmark --files samples/sample_knowledge.md --iterations 100
```

### 4. Running the Test Suite
```powershell
pytest -v --tb=short
```
