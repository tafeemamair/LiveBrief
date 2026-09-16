"""Document parsers for extracting text and metadata from various file formats."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from livebrief.models.document import Document


def extract_markdown_metadata(content: str) -> Tuple[str, Dict[str, str], Optional[str]]:
    """Extract YAML-like frontmatter and leading header from Markdown."""
    metadata: Dict[str, str] = {}
    title: Optional[str] = None
    body = content

    # Check for YAML frontmatter between --- and ---
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if frontmatter_match:
        frontmatter_text = frontmatter_match.group(1)
        body = content[frontmatter_match.end() :]
        for line in frontmatter_text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                metadata[k.strip()] = v.strip().strip("\"'")
        if "title" in metadata:
            title = metadata["title"]

    # Extract top heading if title not already specified in frontmatter
    header_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if header_match:
        header_title = header_match.group(1).strip()
        if not title:
            title = header_title
            metadata["title"] = header_title

    return body.strip(), metadata, title


class DocumentParser:
    """Parses raw text, markdown, or JSON files into Document instances."""

    @staticmethod
    def parse_file(file_path: Union[str, Path]) -> Document:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Document file not found: {path}")

        suffix = path.suffix.lower()
        raw_text = path.read_text(encoding="utf-8")

        if suffix in (".md", ".markdown"):
            body, meta, title = extract_markdown_metadata(raw_text)
            meta["source_file"] = path.name
            meta["file_type"] = "markdown"
            return Document.create(
                content=body,
                doc_id=path.stem,
                title=title or path.stem,
                source_uri=str(path.resolve()),
                metadata=meta,
            )

        elif suffix == ".json":
            try:
                data = json.loads(raw_text)
                if isinstance(data, dict):
                    content = data.get("content") or data.get("text") or data.get("body") or json.dumps(data)
                    title = data.get("title") or path.stem
                    meta = {k: str(v) for k, v in data.items() if k not in ("content", "text", "body")}
                    meta["source_file"] = path.name
                    meta["file_type"] = "json"
                    return Document.create(
                        content=str(content),
                        doc_id=data.get("id") or path.stem,
                        title=str(title),
                        source_uri=str(path.resolve()),
                        metadata=meta,
                    )
                else:
                    return Document.create(
                        content=raw_text,
                        doc_id=path.stem,
                        title=path.stem,
                        source_uri=str(path.resolve()),
                        metadata={"source_file": path.name, "file_type": "json"},
                    )
            except Exception as e:
                raise ValueError(f"Failed to parse JSON document: {e}") from e

        else:
            # Default plain text
            return Document.create(
                content=raw_text,
                doc_id=path.stem,
                title=path.stem,
                source_uri=str(path.resolve()),
                metadata={"source_file": path.name, "file_type": "text"},
            )

    @staticmethod
    def parse_text(
        content: str,
        doc_id: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Document:
        body, extracted_meta, extracted_title = extract_markdown_metadata(content)
        combined_meta = dict(extracted_meta)
        if metadata:
            for k, v in metadata.items():
                combined_meta[str(k)] = str(v)

        return Document.create(
            content=body,
            doc_id=doc_id,
            title=title or extracted_title or doc_id or "Untitled Document",
            metadata=combined_meta,
        )
