"""Unit tests for Phase 2.3 DocumentRegistry and knowledge document management."""

import json
import socketserver
import threading
import urllib.error
import urllib.request
from pathlib import Path
import pytest
from livebrief.models.query import QueryRequest
from livebrief.pipeline import LiveBriefPipeline
from livebrief.voice.documents import DocumentRecord, DocumentRegistry
from livebrief.voice.server import create_handler


@pytest.fixture
def pipeline():
    """Create a fresh LiveBriefPipeline instance for testing."""
    return LiveBriefPipeline(index_name="test_doc_registry_idx")


@pytest.fixture
def registry(pipeline):
    """Create a fresh DocumentRegistry instance."""
    return DocumentRegistry(pipeline=pipeline)


def test_document_registration_markdown(registry, pipeline):
    md_content = """# Architecture Overview
LiveBrief uses in-process Rust Moss indexing for sub-10ms retrieval.
Deterministic embeddings provide stable vector representations."""

    record = registry.ingest_document(
        content=md_content,
        title="Architecture Overview",
        doc_id="arch_spec",
        format="markdown",
    )

    assert record.doc_id == "arch_spec"
    assert record.title == "Architecture Overview"
    assert record.source_format == "markdown"
    assert record.chunk_count > 0
    assert len(record.chunk_ids) == record.chunk_count
    assert record.status == "INDEXED"
    assert record.total_characters == len(md_content.strip())
    assert registry.total_documents == 1
    assert registry.total_chunks == record.chunk_count

    # Verify searchable in Moss
    retrieval = pipeline.retriever.retrieve(QueryRequest(query="Moss sub-10ms retrieval"))
    assert len(retrieval.candidates) > 0
    assert any("Moss" in c.chunk.text for c in retrieval.candidates)


def test_document_registration_text(registry, pipeline):
    text_content = "Latency budget for hot-path retrieval is bounded between 1ms and 8ms."

    record = registry.ingest_document(
        content=text_content,
        title="Latency Policy",
        doc_id="latency_doc",
        format="text",
    )

    assert record.doc_id == "latency_doc"
    assert record.source_format == "text"
    assert record.chunk_count >= 1
    assert registry.get_document("latency_doc") is not None

    retrieval = pipeline.retriever.retrieve(QueryRequest(query="Latency budget"))
    assert len(retrieval.candidates) > 0


def test_document_registration_deterministic_json(registry, pipeline):
    json_data = {
        "z_field": "Last field alphabetically",
        "title": "Config Spec",
        "a_field": "First field alphabetically",
        "nested": {"beta": 2, "alpha": 1},
    }
    raw_json_str = json.dumps(json_data)

    record = registry.ingest_document(
        content=raw_json_str,
        doc_id="config_doc",
        format="json",
    )

    assert record.doc_id == "config_doc"
    assert record.title == "Config Spec"
    assert record.source_format == "json"

    # Verify deterministic JSON formatting: sorted keys with 2-space indentation
    expected_formatted = json.dumps(json_data, sort_keys=True, indent=2, ensure_ascii=False)
    assert record.total_characters == len(expected_formatted)

    # Verify queryable
    retrieval = pipeline.retriever.retrieve(QueryRequest(query="alphabetically"))
    assert len(retrieval.candidates) > 0


def test_document_registration_rejects_malformed_json(registry):
    malformed_json = '{"title": "Broken JSON", "key": '

    with pytest.raises(ValueError, match="Invalid JSON document syntax"):
        registry.ingest_document(
            content=malformed_json,
            doc_id="bad_json_doc",
            format="json",
        )

    assert registry.total_documents == 0
    assert registry.get_document("bad_json_doc") is None


def test_document_registration_rejects_unsupported_format(registry):
    with pytest.raises(ValueError, match="Unsupported document format"):
        registry.ingest_document(
            content="Some text",
            format="pdf",
        )


def test_document_registration_rejects_empty_content(registry):
    with pytest.raises(ValueError, match="Document content cannot be empty"):
        registry.ingest_document(
            content="   ",
            format="markdown",
        )


def test_document_listing_and_metadata(registry):
    registry.ingest_document(content="# Doc One\nContent one.", doc_id="doc_1", format="md")
    registry.ingest_document(content="# Doc Two\nContent two.", doc_id="doc_2", format="md")

    docs = registry.list_documents()
    assert len(docs) == 2
    assert [d.doc_id for d in docs] == ["doc_1", "doc_2"]
    assert registry.total_documents == 2
    assert registry.total_chunks == sum(d.chunk_count for d in docs)


def test_deterministic_document_deletion(registry, pipeline):
    record = registry.ingest_document(
        content="Grounding guarantee enforces zero fabricated claims under absent evidence.",
        title="Safety Protocol",
        doc_id="safety_protocol",
        format="text",
    )
    chunk_ids = list(record.chunk_ids)
    assert len(chunk_ids) > 0

    # Confirm searchable before deletion
    retrieval_before = pipeline.retriever.retrieve(QueryRequest(query="fabricated claims"))
    assert len(retrieval_before.candidates) > 0

    # Execute deterministic deletion
    deleted = registry.delete_document("safety_protocol")
    assert deleted is True
    assert registry.get_document("safety_protocol") is None
    assert registry.total_documents == 0

    # Confirm chunks deleted from Moss
    for cid in chunk_ids:
        assert pipeline.indexer.get_chunk(cid) is None

    retrieval_after = pipeline.retriever.retrieve(QueryRequest(query="fabricated claims"))
    assert len(retrieval_after.candidates) == 0


def test_deletion_of_missing_document(registry):
    deleted = registry.delete_document("non_existent_doc")
    assert deleted is False


def test_delete_and_readd_lifecycle(registry, pipeline):
    content_v1 = "# Engine Spec\nVersion 1: Basic retrieval engine."
    record_v1 = registry.ingest_document(content=content_v1, doc_id="engine_spec", format="md")

    # Delete
    assert registry.delete_document("engine_spec") is True
    assert registry.get_document("engine_spec") is None

    # Re-add with new content
    content_v2 = "# Engine Spec\nVersion 2: High throughput sub-millisecond retrieval engine."
    record_v2 = registry.ingest_document(content=content_v2, doc_id="engine_spec", format="md")

    assert record_v2.doc_id == "engine_spec"
    assert registry.total_documents == 1

    # Verify query matches v2
    retrieval = pipeline.retriever.retrieve(QueryRequest(query="sub-millisecond throughput"))
    assert len(retrieval.candidates) > 0


def test_document_registry_clear(registry, pipeline):
    registry.ingest_document(content="Doc A content", doc_id="a", format="text")
    registry.ingest_document(content="Doc B content", doc_id="b", format="text")
    assert registry.total_documents == 2

    registry.clear()
    assert registry.total_documents == 0
    assert registry.total_chunks == 0
    assert pipeline.indexer.doc_count == 0


def test_document_registry_register_existing_chunks(registry, pipeline):
    doc, chunks = pipeline.ingestion.ingest_text("# Sample\nPre-indexed content.", doc_id="pre_doc")
    pipeline.indexer.add_chunks(chunks)
    record = registry.register_existing_chunks(
        doc_id="pre_doc",
        title="Pre Doc",
        chunks=chunks,
        source_format="markdown",
    )
    assert record.doc_id == "pre_doc"
    assert registry.total_documents == 1
    assert registry.total_chunks == len(chunks)


@pytest.fixture(scope="module")
def doc_test_server():
    web_dir = Path("web")
    server_ready = threading.Event()
    server_holder = {}

    def run_server():
        pipeline = LiveBriefPipeline(index_name="doc_server_test_pipeline")
        doc_registry = DocumentRegistry(pipeline=pipeline)
        handler = create_handler(web_dir, pipeline=pipeline, document_registry=doc_registry)
        socketserver.TCPServer.allow_reuse_address = True
        server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        server_holder["server"] = server
        server_holder["handler"] = handler
        server_holder["registry"] = doc_registry
        server_holder["port"] = server.server_address[1]
        server_ready.set()
        try:
            server.serve_forever()
        except Exception:
            pass
        finally:
            if hasattr(pipeline, "indexer") and pipeline.indexer is not None:
                pipeline.indexer._index = None
                pipeline.indexer = None

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server_ready.wait(timeout=5.0)

    port = server_holder["port"]
    base_url = f"http://127.0.0.1:{port}"
    yield base_url, server_holder["registry"]

    server = server_holder.get("server")
    if server:
        server.shutdown()
        server.server_close()
    handler = server_holder.get("handler")
    if handler:
        handler.pipeline = None
        handler.adapter = None
        handler.document_registry = None
    if server_holder.get("registry"):
        server_holder["registry"].indexer = None
        server_holder["registry"]._documents.clear()
    thread.join(timeout=2.0)


def test_server_documents_api_full_lifecycle(doc_test_server):
    base_url, registry = doc_test_server

    # 1. GET /api/documents (empty)
    req = urllib.request.Request(f"{base_url}/api/documents")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["total_documents"] == 0
        assert data["documents"] == []

    # 2. POST /api/documents (valid markdown)
    post_payload = json.dumps({
        "doc_id": "api_spec",
        "title": "API Specification",
        "content": "# LiveBrief API\nEndpoints for real-time grounded intelligence.",
        "format": "markdown",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/documents",
        data=post_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "SUCCESS"
        assert data["document"]["doc_id"] == "api_spec"
        assert registry.total_documents == 1

    # 3. POST /api/documents with malformed JSON body in content (HTTP 422)
    bad_json_payload = json.dumps({
        "doc_id": "bad_json",
        "content": '{"broken": [1, 2, }',
        "format": "json",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/documents",
        data=bad_json_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 422

    # 4. POST /api/documents with malformed HTTP request body (HTTP 400)
    req = urllib.request.Request(
        f"{base_url}/api/documents",
        data=b"invalid { json body",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 400

    # 5. POST /api/documents with empty content (HTTP 400)
    empty_payload = json.dumps({"content": "  "}).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/documents",
        data=empty_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 400

    # 6. DELETE /api/documents/api_spec (valid delete)
    req = urllib.request.Request(f"{base_url}/api/documents/api_spec", method="DELETE")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "DELETED"
        assert data["doc_id"] == "api_spec"
        assert registry.total_documents == 0

    # 7. DELETE /api/documents/non_existent (HTTP 404)
    req = urllib.request.Request(f"{base_url}/api/documents/non_existent", method="DELETE")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 404


def test_server_rapid_sequential_document_requests(doc_test_server):
    base_url, registry = doc_test_server

    for i in range(10):
        post_payload = json.dumps({
            "doc_id": f"rapid_doc_{i}",
            "title": f"Rapid Doc {i}",
            "content": f"Content for rapid document {i} with key search terms.",
            "format": "text",
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/documents",
            data=post_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200

    # Verify all 10 are listed
    req = urllib.request.Request(f"{base_url}/api/documents")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["total_documents"] == 10

    # Delete all 10 sequentially
    for i in range(10):
        req = urllib.request.Request(f"{base_url}/api/documents/rapid_doc_{i}", method="DELETE")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200

    # Verify list is empty
    req = urllib.request.Request(f"{base_url}/api/documents")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["total_documents"] == 0


def test_indexing_failure_consistency(registry):
    # Test that failed chunking/indexing leaves registry untouched
    class FailingIngestion:
        def ingest_text(self, *args, **kwargs):
            return None, []

    registry.ingestion = FailingIngestion()
    with pytest.raises(ValueError, match="zero indexed chunks"):
        registry.ingest_document(content="Some content", doc_id="failing_doc", format="text")

    assert registry.total_documents == 0
    assert registry.get_document("failing_doc") is None

