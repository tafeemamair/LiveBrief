"""Lightweight HTTP server to serve the LiveBrief Phase 2.1 voice interface."""

from __future__ import annotations

import functools
import http.server
import socketserver
from pathlib import Path


def create_handler(web_dir: Path):
    return functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(web_dir))


def serve_voice_ui(port: int = 8000, host: str = "127.0.0.1") -> None:
    """Start local web server for LiveBrief Phase 2.1 voice layer."""
    web_dir = Path(__file__).resolve().parent.parent.parent / "web"
    if not web_dir.exists():
        raise FileNotFoundError(f"Web directory not found at {web_dir}")

    handler = create_handler(web_dir)
    # Enable address reuse
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((host, port), handler) as httpd:
        print(f"\n=======================================================")
        print(f" LiveBrief Phase 2.1 Voice Layer running at:")
        print(f" http://{host}:{port}/")
        print(f"=======================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down LiveBrief Voice server.")


if __name__ == "__main__":
    serve_voice_ui()
