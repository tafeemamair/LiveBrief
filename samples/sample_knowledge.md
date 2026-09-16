---
title: LiveBrief System Architecture and Retrieval Specification
version: 1.0.0
author: LiveBrief Core Team
tags: architecture, retrieval, moss, latency
---

# LiveBrief System Architecture and Retrieval Specification

## Executive Overview
LiveBrief is a specialized real-time AI briefing engine architected for sub-second question answering and executive summaries over dynamic document corpora. The platform combines ultra-low latency semantic retrieval with strict factual grounding mechanisms to eliminate hallucinations in mission-critical decision workflows.

## Hot-Path Latency Budget
The LiveBrief Phase 1 retrieval vertical slice operates under strict timing constraints:
- In-memory Moss hybrid retrieval: 1ms to 8ms hot-path response budget.
- Sentence-level span extraction and MMR deduplication: under 5ms.
- Grounded structured response synthesis: under 15ms.
- End-to-end pipeline latency target: sub-30ms for local briefing synthesis.

## Moss Native Retrieval Integration
LiveBrief directly embeds the Rust-based `moss_core` retrieval engine. Unlike external vector databases that incur multi-millisecond network hops and serialization penalties, Moss operates entirely in-process:
1. Multi-representation indexing: Combines inverted BM25 keyword matching with dense semantic embeddings.
2. Hybrid search fusion: Configurable alpha weighting allows dynamic balancing between exact keyword matches (alpha = 0.0) and conceptual semantic matching (alpha = 1.0).
3. Memory layout and binary serialization: Serialized into native `.moss` binary payloads using compact integer quantization and compressed inverted lists.
4. Structured metadata filtering: Supports high-performance predicate filtering ($eq, $ne, $in, $gt, $lt) directly within the retrieval loop before rank aggregation.

## Evidence Selection and MMR Deduplication
Retrieved candidates undergo a secondary evidence selection pass:
- Maximal Marginal Relevance (MMR) balances query relevance against information redundancy using Jaccard word-overlap penalties.
- Token budgeting caps the evidence ledger at configurable boundaries (e.g. 2048 tokens) to prevent context saturation.
- Sentence boundary detection extracts discrete factual spans with character offsets for source auditing.

## Hallucination Safeguards and Grounding Score
LiveBrief enforces three strict anti-hallucination guardrails:
1. Citation Attribution: Every key finding must map to one or more verified citation anchors ([1], [2]).
2. Grounding Score: A quantitative metric evaluating the proportion of generated claims supported by retrieved evidence text.
3. Graceful Abstention: When relevant evidence is missing or falls below the minimum relevance threshold (0.05), the synthesizer explicitly reports insufficient context rather than hallucinating speculative facts.
