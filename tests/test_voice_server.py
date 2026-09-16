"""Tests for Voice UI and Intelligence API Server."""

import json
import socketserver
import threading
import urllib.request
from pathlib import Path
import pytest
from livebrief.pipeline import LiveBriefPipeline
from livebrief.voice.server import create_handler


@pytest.fixture(scope="module")
def test_server():
    web_dir = Path("web")
    server_ready = threading.Event()
    server_holder = {}

    def run_server():
        pipeline = LiveBriefPipeline(index_name="test_server_pipeline")
        doc_path = Path("samples/sample_knowledge.md")
        if doc_path.exists():
            pipeline.ingest_and_index_files([doc_path])

        handler = create_handler(web_dir, pipeline=pipeline)
        socketserver.TCPServer.allow_reuse_address = True
        server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        server_holder["server"] = server
        server_holder["handler"] = handler
        server_holder["port"] = server.server_address[1]
        server_ready.set()
        try:
            server.serve_forever()
        except Exception:
            pass
        finally:
            if hasattr(pipeline, "indexer"):
                pipeline.indexer = None
            del pipeline

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server_ready.wait(timeout=5.0)

    port = server_holder["port"]
    yield f"http://127.0.0.1:{port}"

    handler = server_holder.get("handler")
    if handler:
        handler.pipeline = None
        handler.adapter = None
    server = server_holder.get("server")
    if server:
        server.shutdown()
        server.server_close()
    thread.join(timeout=2.0)


def test_api_health_endpoint(test_server: str):
    url = f"{test_server}/api/health"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert data["phase"] == "2.2"


def test_api_index_status_endpoint(test_server: str):
    url = f"{test_server}/api/index-status"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["doc_count"] > 0
        assert data["engine"] == "moss_core"


def test_api_query_substantive_endpoint(test_server: str):
    url = f"{test_server}/api/query"
    payload = json.dumps({"query": "What are the latency budgets in LiveBrief?", "session_id": "test_s"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["triggered"] is True
        event = data["event"]
        assert event is not None
        assert event["has_sufficient_evidence"] is True
        assert len(event["key_findings"]) > 0
        assert len(event["evidence_sources"]) > 0
        assert event["grounding_score"] == 1.0


def test_api_query_fragment_suppressed_endpoint(test_server: str):
    url = f"{test_server}/api/query"
    payload = json.dumps({"query": "can you", "session_id": "test_s"}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["triggered"] is False
        assert data["utterance_type"] == "FRAGMENT"
