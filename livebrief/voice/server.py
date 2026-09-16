"""HTTP Server providing static UI hosting and intelligence pipeline API endpoints."""

from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
import socketserver
from typing import Optional
from livebrief.pipeline import LiveBriefPipeline
from livebrief.voice.adapter import VoicePipelineAdapter


class LiveBriefHTTPHandler(SimpleHTTPRequestHandler):
    """Handles static web assets and Phase 2.2 /api/query JSON requests."""

    pipeline: Optional[LiveBriefPipeline] = None
    adapter: Optional[VoicePipelineAdapter] = None

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._send_json(200, {"status": "ok", "phase": "2.2"})
            return
        if self.path == "/api/index-status":
            doc_count = self.pipeline.indexer.doc_count if self.pipeline else 0
            self._send_json(200, {"doc_count": doc_count, "engine": "moss_core"})
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/query":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8")
            try:
                data = json.loads(body)
                query_text = data.get("query", "")
                session_id = data.get("session_id")

                if not self.adapter:
                    self._send_json(500, {"error": "Voice pipeline adapter not initialized"})
                    return

                event, utype, triggered, reason = self.adapter.process_speech_utterance(
                    text=query_text,
                    session_id=session_id,
                )

                if not triggered:
                    self._send_json(200, {
                        "triggered": False,
                        "utterance_type": utype.value,
                        "reason": reason,
                    })
                    return

                self._send_json(200, {
                    "triggered": True,
                    "utterance_type": utype.value,
                    "event": event.model_dump() if event else None,
                })

            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        self._send_json(404, {"error": "Endpoint not found"})

    def _send_json(self, status_code: int, data: dict) -> None:
        response_bytes = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def create_handler(web_dir: Path, pipeline: Optional[LiveBriefPipeline] = None):
    adapter_instance = VoicePipelineAdapter(pipeline) if pipeline else None

    class CustomHandler(LiveBriefHTTPHandler):
        def __init__(self, request, client_address, server):
            super().__init__(request, client_address, server, directory=str(web_dir))

    CustomHandler.pipeline = pipeline
    CustomHandler.adapter = adapter_instance
    return CustomHandler


def serve_voice_ui(
    port: int = 8000,
    host: str = "127.0.0.1",
    docs_path: Optional[Path] = None,
) -> None:
    """Start local web server for LiveBrief Phase 2.2 intelligence copilot."""
    web_dir = Path(__file__).resolve().parent.parent.parent / "web"
    if not web_dir.exists():
        raise FileNotFoundError(f"Web directory not found at {web_dir}")

    # Initialize frozen LiveBriefPipeline on the server thread
    pipeline = LiveBriefPipeline(index_name="livebrief_server_idx")

    # Ingest default sample knowledge if available
    default_doc = docs_path or (Path(__file__).resolve().parent.parent.parent / "samples" / "sample_knowledge.md")
    if default_doc.exists():
        count = pipeline.ingest_and_index_files([default_doc])
        print(f"[LiveBrief] Ingested {count} knowledge chunks into in-process Moss index.")

    handler = create_handler(web_dir, pipeline=pipeline)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), handler) as httpd:
        print(f"\n=======================================================")
        print(f" LiveBrief Phase 2.2 Intelligence Copilot running at:")
        print(f" http://{host}:{port}/")
        print(f"=======================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down LiveBrief server.")


if __name__ == "__main__":
    serve_voice_ui()
