"""Tests for Moss native indexing, query execution, and serialization."""

from pathlib import Path
import pytest
from livebrief.models.document import Chunk
from livebrief.moss.embedder import DeterministicEmbedder
from livebrief.moss.indexer import MossIndexer


def test_moss_indexer_add_and_query():
    indexer = MossIndexer(index_name="test_index", embedder=DeterministicEmbedder(dimension=384))
    
    chunks = [
        Chunk.create(
            doc_id="doc1",
            text="Moss is a sub-10ms native Rust retrieval engine for AI agents.",
            chunk_index=0,
            start_char=0,
            end_char=60,
            metadata={"category": "tech", "priority": "high"},
        ),
        Chunk.create(
            doc_id="doc2",
            text="LiveBrief synthesizes structured executive briefs with citations.",
            chunk_index=0,
            start_char=0,
            end_char=65,
            metadata={"category": "product", "priority": "high"},
        ),
    ]

    added, updated = indexer.add_chunks(chunks)
    assert added == 2
    assert indexer.doc_count == 2

    # Query for retrieval
    result = indexer.query("Rust retrieval engine", top_k=2, alpha=0.8)
    assert len(result.docs) > 0
    assert result.docs[0].id == chunks[0].id
    assert "Rust retrieval" in result.docs[0].text


def test_moss_indexer_serialization_and_deserialization(tmp_path: Path):
    indexer = MossIndexer(index_name="save_test", embedder=DeterministicEmbedder(dimension=384))
    
    chunks = [
        Chunk.create(doc_id="d1", text="Knowledge retrieval unit alpha.", chunk_index=0, start_char=0, end_char=30),
        Chunk.create(doc_id="d2", text="Knowledge retrieval unit beta.", chunk_index=0, start_char=0, end_char=30),
    ]
    indexer.add_chunks(chunks)
    assert indexer.doc_count == 2

    # Save to file
    file_path = tmp_path / "test_snapshot.moss"
    indexer.save_to_file(file_path)
    assert file_path.exists()
    assert file_path.stat().st_size > 0

    # Load into new indexer
    restored_indexer = MossIndexer(index_name="restored", embedder=DeterministicEmbedder(dimension=384))
    count = restored_indexer.load_from_file(file_path)
    assert count == 2
    assert restored_indexer.doc_count == 2

    # Query restored index
    res = restored_indexer.query("unit alpha", top_k=1)
    assert len(res.docs) == 1
    assert "alpha" in res.docs[0].text


def test_moss_indexer_deletion():
    indexer = MossIndexer(index_name="delete_test")
    chunks = [
        Chunk.create(doc_id="d1", text="Chunk one text.", chunk_index=0, start_char=0, end_char=15),
        Chunk.create(doc_id="d2", text="Chunk two text.", chunk_index=0, start_char=0, end_char=15),
    ]
    indexer.add_chunks(chunks)
    assert indexer.doc_count == 2

    deleted = indexer.delete_chunks([chunks[0].id])
    assert deleted == 1
    assert indexer.doc_count == 1
    assert indexer.get_chunk(chunks[0].id) is None
    assert indexer.get_chunk(chunks[1].id) is not None
