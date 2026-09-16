"""Tests for Voice UI static server."""

from pathlib import Path
import pytest
from livebrief.voice.server import create_handler


def test_create_handler():
    web_dir = Path("web")
    handler_cls = create_handler(web_dir)
    assert handler_cls is not None
