# LiveBrief

**Real-time AI research and briefing engine with low-latency retrieval, evidence-grounded responses, and explicit abstention.**

LiveBrief is an interactive intelligence copilot that delivers rapid, structured briefing responses over dynamic knowledge bases. It combines in-process hybrid retrieval, evidence-grounded response assembly, and real-time voice interaction - without external API calls or cloud dependencies on the retrieval path.

---

## The Problem

Traditional research and Q&A systems can trade off retrieval speed and response grounding. LiveBrief is designed to address both by combining low-latency retrieval with evidence-grounded response handling:

- **Low-latency retrieval** via an in-process Rust engine - no network round trips on the retrieval path.
- **Evidence-grounded responses** - generated findings are tied to selected evidence and citation references. If evidence is insufficient, the system explicitly abstains rather than speculating.
- **Interactive voice + text** - ask questions naturally via speech or text, with real-time evidence provenance.

---

## Main Features

| Feature | Description |
|---|---|
| **In-Process Moss Retrieval** | Hybrid BM25 + dense vector search via embedded Rust `moss_core.Index` runtime |
| **MMR Evidence Selection** | Maximal Marginal Relevance deduplication with sentence-level span extraction and token budgeting |
| **Grounded Response Generation** | Structured responses with executive summary, key findings, and citation-anchored evidence ledger |
| **Abstention on Insufficient Evidence** | Explicit "insufficient context" response when evidence is missing or below relevance threshold |
| **Latency Instrumentation** | High-resolution stage-by-stage timing across ingestion, indexing, retrieval, selection, and synthesis |
| **Voice Intelligence Copilot** | Browser-based speech input via Web Speech API with utterance classification gate |
| **Conversational Context** | Follow-up question resolution with fresh retrieval on every turn |
| **Dynamic Document Management** | Add, list, and delete knowledge documents at runtime via REST API |
| **Interactive Evidence Provenance** | Clickable citation badges linked to source excerpts in the evidence ledger |

---

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌────────────────────────┐
│  Raw Documents  │ ──► │ Ingestion & Chunker  │ ──► │  Moss Indexing Engine  │
│ (.md, .txt, JSON│     │ (Parsers & Chunks)   │     │  (moss_core native)    │
└─────────────────┘     └──────────────────────┘     └───────────┬────────────┘
                                                                 │
                                                                 ▼
┌─────────────────┐     ┌──────────────────────┐     ┌────────────────────────┐
│ Structured      │ ◄── │  Evidence Selection  │ ◄── │   Semantic Retrieval   │
│ Grounded Brief  │     │  (MMR & Spans & Caps)│     │   (Moss Hybrid Search) │
└────────┬────────┘     └──────────────────────┘     └────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Latency Tracker │
│ (Stage Timings) │
└─────────────────┘
```

### Voice & Web Copilot Flow

```
User (Voice / Text) ──► Utterance Gate ──► Context Resolver ──► Moss Hybrid Retrieval
                                                                      │
UI (Grounded Brief + Citations) ◄── Grounded Synthesizer ◄── MMR Evidence Selector
```

### Component Breakdown

#### Document Ingestion (`livebrief.ingestion`)
- **Parsers**: Extract text and structured metadata from Markdown, plain text, and JSON documents.
- **Chunker**: Splits documents preserving paragraph/sentence boundaries with configurable size and overlap. Generates deterministic content-hashed chunk IDs (`sha256(doc_id:content)`).

#### Moss - The Native Retrieval Engine (`livebrief.moss`)
Moss is the core retrieval runtime. LiveBrief embeds `moss_core.Index`, a Rust-based in-process engine, directly into the Python process. This eliminates all network overhead on the search hot path.

- **Hybrid Index**: Combines BM25 lexical/keyword indexing with dense vector embeddings. The `alpha` parameter controls fusion weight (0.0 = pure BM25, 1.0 = pure vector).
- **Embedder Interface**: Pluggable embedding providers (`DeterministicEmbedder` for reproducible hashing, or custom `BaseEmbedder` implementations).
- **Structured Metadata Filtering**: Supports `$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin` operators.
- **Binary Serialization**: Full index persistence and restoration via `.moss` binary format using `moss_core.serializeToBinary` / `deserializeFromBinary`.

#### Hybrid BM25 + Dense Retrieval (`livebrief.retrieval`)
`MossSemanticRetriever` executes native Moss queries with configurable hybrid alpha fusion, score normalization, and minimum relevance thresholds. Candidates below the threshold are filtered before evidence selection.

#### MMR Evidence Selection (`livebrief.evidence`)
`EvidenceSelector` implements greedy Maximal Marginal Relevance:

1. **Diversity vs. Relevance**: Balances query relevance against inter-chunk redundancy using a configurable `diversity_lambda` parameter.
2. **Sentence Span Extraction**: Locates the most salient sentence-level spans within each chunk, scoring by query-term overlap.
3. **Token Budgeting**: Enforces strict token count limits (default: 2048 tokens, ~4 chars/token approximation) to prevent context overflow.
4. **Citation Anchoring**: Assigns sequential citation markers (`[1]`, `[2]`, ...) linked to source documents and character offsets.

#### Grounding & Abstention (`livebrief.synthesis`)
`GroundedSynthesizer` applies evidence-grounded response handling:

- **Structured Response**: Returns a typed `LiveBriefResponse` containing `executive_summary`, `key_findings` (with citation markers), `evidence_ledger` (full provenance), and `grounding_score` (0.0–1.0).
- **Abstention on Insufficient Evidence**: When evidence is absent or below the relevance threshold, the synthesizer explicitly declines to speculate. It returns `has_sufficient_evidence=False` with caveats explaining why no claims were generated.
- **Grounding Score**: Quantitative metric measuring the fraction of generated findings that have supporting evidence citations. This measures citation coverage, not factual truth by itself.

#### Evidence Ledger & Citation Provenance
Every response includes a full `evidence_ledger` - a list of `EvidenceCitation` objects containing:
- `citation_id`, `doc_id`, `chunk_id`
- `excerpt` (most salient span from the source chunk)
- `source_uri` (original file path if available)
- `relevance_score` and full metadata

In the web UI, clicking a citation badge `[1]` highlights the source excerpt in the ledger. Clicking the evidence card opens the Evidence Explorer modal with chunk-level provenance.

#### Latency Instrumentation (`livebrief.telemetry`)
`LatencyTracker` uses high-resolution `time.perf_counter()` timing across every pipeline stage:

| Stage | Field |
|---|---|
| Document Ingestion | `ingestion_ms` |
| Moss Indexing | `indexing_ms` |
| Moss Retrieval | `moss_retrieval_ms` |
| Evidence Selection & MMR | `evidence_selection_ms` |
| Grounded Synthesis | `synthesis_ms` |
| Total End-to-End | `total_pipeline_ms` |

#### Voice Layer (`livebrief.voice`)
- **Utterance Classification Gate**: Suppresses filler words, incomplete fragments, and non-substantive utterances before triggering retrieval.
- **Session Context Manager**: Resolves follow-up queries (e.g., "What about its latency?") while ensuring fresh Moss retrieval executes on every turn - context is never used as an answer source.
- **Document Registry**: Runtime document management with add/list/delete via REST API, backed by the same Moss indexer.
- **HTTP Server**: Lightweight `socketserver.TCPServer` serving the web UI and REST API endpoints (`/api/query`, `/api/documents`, `/api/health`, `/api/index-status`).

---

## Project Structure

```
LiveBrief/
├── livebrief/
│   ├── __init__.py              # Package root (version)
│   ├── pipeline.py              # End-to-end orchestrator
│   ├── cli.py                   # CLI: query, benchmark, serve-voice
│   ├── ingestion/
│   │   ├── parser.py            # Markdown/text/JSON document parsers
│   │   ├── chunker.py           # Boundary-preserving document chunker
│   │   └── pipeline.py          # Ingestion orchestration
│   ├── moss/
│   │   ├── indexer.py           # moss_core.Index wrapper (Rust runtime)
│   │   └── embedder.py          # Embedding providers (deterministic, pluggable)
│   ├── retrieval/
│   │   └── retriever.py         # Hybrid BM25 + dense retrieval
│   ├── evidence/
│   │   └── selector.py          # MMR deduplication, span extraction, token budgets
│   ├── synthesis/
│   │   └── grounder.py          # Grounded response synthesis & abstention
│   ├── telemetry/
│   │   └── latency.py           # Sub-ms stage timer & breakdown
│   ├── voice/
│   │   ├── server.py            # HTTP server & REST API
│   │   ├── adapter.py           # Voice-to-pipeline bridge
│   │   ├── utterance.py         # Utterance classification gate
│   │   ├── context.py           # Session context manager
│   │   ├── documents.py         # Runtime document registry
│   │   ├── models.py            # Voice data models
│   │   └── state_machine.py     # Voice state lifecycle
│   └── models/
│       ├── document.py          # Document & Chunk models
│       ├── query.py             # QueryRequest & filters
│       ├── evidence.py          # EvidenceItem, Span, SelectionResult
│       └── response.py          # LiveBriefResponse, LatencyBreakdown, GroundingMetric
├── web/
│   ├── index.html               # Intelligence copilot UI
│   ├── copilot.js               # Copilot interaction logic
│   ├── stt.js                   # Speech-to-text integration
│   └── styles.css               # UI styles
├── tests/                       # 15 test modules (unit, integration, e2e)
├── samples/
│   └── sample_knowledge.md      # Example knowledge base document
├── ARCHITECTURE.md              # Locked architecture specification
├── pyproject.toml               # Project metadata & dependencies
└── README.md
```

---

## Getting Started

### Prerequisites

- **Python 3.10+** (3.13 recommended)
- **moss** (`>= 1.12.0`) - installed automatically via `pip`
- **Google Chrome** or **Microsoft Edge** (required for Web Speech API voice input)

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/tafeemamair/LiveBrief.git
cd LiveBrief

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# Install in editable mode
pip install -e .
```

### 2. Launch the Web & Voice Intelligence Copilot

```bash
python -m livebrief.cli serve-voice --port 8000
```

Open **http://127.0.0.1:8000/** in Chrome or Edge. The server automatically ingests `samples/sample_knowledge.md` as the default knowledge base.

### 3. Query via CLI

```bash
python -m livebrief.cli query "What are the latency budgets and architecture?" --files samples/sample_knowledge.md
```

### 4. Benchmark Moss Retrieval Latency

```bash
python -m livebrief.cli benchmark --files samples/sample_knowledge.md --iterations 50
```

Reports p50, p95, p99, min, max, and average Moss retrieval latency.

### 5. Run the Test Suite

```bash
pip install -e ".[dev]"
pytest -v
```

---

## Dependencies

| Package | Purpose |
|---|---|
| `moss >= 1.12.0` | Native Rust retrieval engine (BM25 + dense hybrid) |
| `pydantic >= 2.0.0` | Typed data models and validation |
| `numpy >= 1.24.0` | Numerical operations for embeddings |
| `rich >= 13.0.0` | Terminal formatting for CLI output |
| `typing_extensions >= 4.8.0` | Extended type hints |

Dev dependencies: `pytest >= 8.0.0`, `pytest-cov >= 5.0.0`

---

## License

This project is submitted to the **HiDevs Hackathon - Doctor Agent** track.
