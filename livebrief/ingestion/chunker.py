"""Document chunker preserving structure and token/char bounds."""

from __future__ import annotations

import re
from typing import Dict, List, Optional
from livebrief.models.document import Chunk, Document


class DocumentChunker:
    """Splits documents into contextual chunks suitable for Moss indexing."""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 40,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk_document(self, document: Document) -> List[Chunk]:
        """Split a Document into indexed Chunk models with character offsets."""
        text = document.content
        if not text.strip():
            return []

        # Split along major structural breaks (paragraphs / headings)
        paragraphs = re.split(r"(\n{2,}|\n(?=#+\s))", text)
        
        raw_units: List[Dict[str, int | str]] = []
        cursor = 0
        for block in paragraphs:
            if not block:
                continue
            start_idx = text.find(block, cursor)
            if start_idx == -1:
                start_idx = cursor
            end_idx = start_idx + len(block)
            cursor = end_idx

            stripped = block.strip()
            if stripped:
                raw_units.append({
                    "text": stripped,
                    "start": start_idx,
                    "end": end_idx,
                })

        chunks: List[Chunk] = []
        current_text = ""
        current_start = 0
        current_end = 0
        chunk_idx = 0

        for unit in raw_units:
            unit_text = str(unit["text"])
            unit_start = int(unit["start"])
            unit_end = int(unit["end"])

            if not current_text:
                current_text = unit_text
                current_start = unit_start
                current_end = unit_end
            elif len(current_text) + len(unit_text) + 1 <= self.chunk_size:
                current_text += "\n\n" + unit_text
                current_end = unit_end
            else:
                # Flush current chunk
                if len(current_text) >= self.min_chunk_size:
                    chunks.append(
                        Chunk.create(
                            doc_id=document.id,
                            text=current_text,
                            chunk_index=chunk_idx,
                            start_char=current_start,
                            end_char=current_end,
                            metadata=dict(document.metadata),
                        )
                    )
                    chunk_idx += 1

                # Start next chunk (optionally with overlap if unit is large)
                current_text = unit_text
                current_start = unit_start
                current_end = unit_end

        # Flush final chunk
        if current_text and (len(current_text) >= self.min_chunk_size or not chunks):
            chunks.append(
                Chunk.create(
                    doc_id=document.id,
                    text=current_text,
                    chunk_index=chunk_idx,
                    start_char=current_start,
                    end_char=current_end,
                    metadata=dict(document.metadata),
                )
            )

        return chunks
