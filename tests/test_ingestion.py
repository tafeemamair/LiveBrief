"""Tests for document parsing and chunking."""

import json
from pathlib import Path
import pytest
from livebrief.ingestion.chunker import DocumentChunker
from livebrief.ingestion.parser import DocumentParser, extract_markdown_metadata
from livebrief.ingestion.pipeline import IngestionPipeline
from livebrief.models.document import Document


def test_markdown_parser_extracts_frontmatter_and_title(tmp_path: Path):
    content = """---
title: Test Architecture
author: Alice
category: engineering
---

# Test Architecture Document

This is the introductory paragraph.

## Section 1
Detailed technical discussion about performance.
"""
    file_path = tmp_path / "test_doc.md"
    file_path.write_text(content, encoding="utf-8")

    doc = DocumentParser.parse_file(file_path)
    assert doc.id == "test_doc"
    assert doc.title == "Test Architecture"
    assert doc.metadata["author"] == "Alice"
    assert doc.metadata["category"] == "engineering"
    assert "This is the introductory paragraph" in doc.content


def test_json_parser(tmp_path: Path):
    data = {
        "id": "json_doc_01",
        "title": "API Specification",
        "content": "Endpoint descriptions and schemas.",
        "version": "2.1",
    }
    file_path = tmp_path / "api_spec.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    doc = DocumentParser.parse_file(file_path)
    assert doc.id == "json_doc_01"
    assert doc.title == "API Specification"
    assert doc.content == "Endpoint descriptions and schemas."
    assert doc.metadata["version"] == "2.1"


def test_chunker_splits_paragraphs_and_preserves_offsets():
    text = (
        "First section with introductory context.\n\n"
        "Second section containing extensive details on latency and retrieval performance.\n\n"
        "Third section summarizing key findings."
    )
    doc = Document.create(content=text, doc_id="doc_sample")
    chunker = DocumentChunker(chunk_size=100, chunk_overlap=20, min_chunk_size=10)
    chunks = chunker.chunk_document(doc)

    assert len(chunks) >= 2
    for c in chunks:
        assert c.doc_id == "doc_sample"
        assert len(c.text) > 0
        assert c.start_char >= 0
        assert c.end_char > c.start_char
        assert c.id.startswith("doc_sample_c")


def test_ingestion_pipeline_directory(tmp_path: Path):
    (tmp_path / "doc1.md").write_text("# Doc One\n\nContent for doc 1.", encoding="utf-8")
    (tmp_path / "doc2.txt").write_text("Plain text content for doc 2.", encoding="utf-8")

    pipeline = IngestionPipeline()
    docs, chunks = pipeline.ingest_directory(tmp_path)

    assert len(docs) == 2
    assert len(chunks) >= 2
    doc_ids = {d.id for d in docs}
    assert "doc1" in doc_ids
    assert "doc2" in doc_ids
