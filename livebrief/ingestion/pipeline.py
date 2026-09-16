"""Document ingestion pipeline orchestrating parsing and chunking."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union
from livebrief.ingestion.chunker import DocumentChunker
from livebrief.ingestion.parser import DocumentParser
from livebrief.models.document import Chunk, Document


class IngestionPipeline:
    """Manages document intake, parsing, and chunk generation."""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 30,
    ) -> None:
        self.parser = DocumentParser()
        self.chunker = DocumentChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_chunk_size=min_chunk_size,
        )

    def ingest_files(self, paths: List[Union[str, Path]]) -> Tuple[List[Document], List[Chunk]]:
        """Ingest a list of files, parse them into Documents, and generate Chunks."""
        documents: List[Document] = []
        all_chunks: List[Chunk] = []

        for p in paths:
            doc = self.parser.parse_file(p)
            documents.append(doc)
            chunks = self.chunker.chunk_document(doc)
            all_chunks.extend(chunks)

        return documents, all_chunks

    def ingest_directory(
        self,
        dir_path: Union[str, Path],
        extensions: Tuple[str, ...] = (".md", ".txt", ".json"),
    ) -> Tuple[List[Document], List[Chunk]]:
        """Scan directory and ingest all matching document files."""
        folder = Path(dir_path)
        if not folder.exists() or not folder.is_dir():
            raise NotADirectoryError(f"Directory not found: {folder}")

        files: List[Path] = []
        for ext in extensions:
            files.extend(folder.rglob(f"*{ext}"))

        return self.ingest_files(files)

    def ingest_text(
        self,
        text: str,
        doc_id: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Tuple[Document, List[Chunk]]:
        """Directly ingest a raw string of text."""
        doc = self.parser.parse_text(text, doc_id=doc_id, title=title, metadata=metadata)
        chunks = self.chunker.chunk_document(doc)
        return doc, chunks
