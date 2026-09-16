# LiveBrief Locked Architecture Specification

LiveBrief is a low-latency, real-time AI research and briefing engine designed for interactive synthesis and conversational grounding over dynamic knowledge bases.

## Phase 1 Scope: Retrieval Vertical Slice

Phase 1 establishes the core ingestion-to-grounded-brief pipeline with zero UI or voice layer dependencies:

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

## Architectural Components

### 1. Document Ingestion (`livebrief.ingestion`)
- **Parsers**: Extracts text content and structured metadata from Markdown, plain text, and structured JSON documents.
- **Chunker**: Preserves paragraph and sentence boundaries, generating deterministic content-hashed chunk IDs (`chunk_id = sha256(doc_id:content)`).
- **Metadata**: Normalizes metadata values to key-value string mappings required by native Moss indexing filters.

### 2. Moss Indexing Engine (`livebrief.moss`)
- **Native Runtime**: Integrates `moss_core.Index` (Rust-based in-process engine) as the mandatory retrieval engine.
- **Hybrid Index Representation**: Combines lexical/keyword indexing and dense vector embeddings with configurable fusion weight (`alpha`).
- **Embedder Interface**: Pluggable embedding providers (`DeterministicEmbedder`, local vectors, or foundation model embeddings) with dimension verification.
- **Binary Serialization**: Full persistence and restoration via native `moss_core.serializeToBinary` and `deserializeFromBinary` (.moss format).

### 3. Semantic Retrieval (`livebrief.retrieval`)
- **Hybrid Search**: Executes native Moss query with hybrid alpha fusion ($0 \le \alpha \le 1$).
- **Filtering**: Structured metadata filtering (`$eq`, `$ne`, `$gt`, `$gte`, `$lt`, `$lte`, `$in`, `$nin`).
- **Score Normalization**: Maps raw similarity/BM25 scores into calibrated relevance confidence intervals.

### 4. Evidence Selection (`livebrief.evidence`)
- **Maximal Marginal Relevance (MMR)**: Balances query relevance against redundancy to select diverse, non-repetitive evidence chunks.
- **Span Extraction**: Identifies the most salient sentence-level spans within retrieved chunks.
- **Context Budgeting**: Enforces strict token and count budgets.
- **Citation Anchoring**: Generates sequential citation numbers (`[1]`, `[2]`, ...) linked to source documents and offsets.

### 5. Grounded Synthesis (`livebrief.synthesis`)
- **Structured Response**: Generates typed `LiveBriefResponse` containing:
  - `executive_summary`: High-level synthesis.
  - `key_findings`: List of discrete findings with citation markers.
  - `evidence_ledger`: Detailed list of `EvidenceCitation` objects with source quotes and metadata.
  - `grounding_score`: Quantitative metric ($0.0 - 1.0$) evaluating claim-to-evidence coverage.
  - `has_sufficient_evidence`: Boolean flag indicating whether evidence met the relevance threshold.
- **No-Hallucination Fallback**: When relevant evidence is absent or below threshold, the synthesizer explicitly declines to speculate and returns an ungrounded state with `has_sufficient_evidence=False`.

### 6. Latency Instrumentation (`livebrief.telemetry`)
- Sub-millisecond timing across every pipeline phase:
  - `ingestion_ms`
  - `indexing_ms`
  - `moss_retrieval_ms`
  - `evidence_selection_ms`
  - `synthesis_ms`
  - `total_e2e_ms`
- Real-time latency tracking and telemetry reporting.
