"""Moss native indexing engine wrapper for LiveBrief."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import moss_core
from moss import DocumentInfo
from livebrief.models.document import Chunk
from livebrief.moss.embedder import BaseEmbedder, DeterministicEmbedder


class MossIndexer:
    """
    High-performance indexing and retrieval runtime built on the native Rust Moss core.
    Provides in-process hybrid indexing, persistence, and sub-10ms search.
    """

    def __init__(
        self,
        index_name: str = "livebrief_index",
        model_id: str = "moss-minilm",
        embedder: Optional[BaseEmbedder] = None,
    ) -> None:
        self.index_name = index_name
        self.model_id = model_id
        self.embedder: BaseEmbedder = embedder or DeterministicEmbedder(dimension=384)
        self._index = moss_core.Index(self.index_name, self.model_id)
        self._chunks_by_id: Dict[str, Chunk] = {}

    @property
    def doc_count(self) -> int:
        """Return the number of items indexed in the Moss engine."""
        return self._index.doc_count

    def add_chunks(self, chunks: List[Chunk]) -> Tuple[int, int]:
        """
        Embed and index chunks in the native Moss index.
        Returns tuple of (added_count, updated_count).
        """
        if not chunks:
            return 0, 0

        moss_docs: List[DocumentInfo] = []
        embeddings: List[List[float]] = []

        for chunk in chunks:
            # Generate embedding if not already cached on chunk
            if chunk.embedding is not None and len(chunk.embedding) == self.embedder.dimension:
                emb = chunk.embedding
            else:
                emb = self.embedder.embed_text(chunk.text)
                chunk.embedding = emb

            embeddings.append(emb)

            # Ensure all metadata values are strings for Moss filter engine compatibility
            clean_meta = {str(k): str(v) for k, v in chunk.metadata.items()}
            doc_info = DocumentInfo(
                id=chunk.id,
                text=chunk.text,
                metadata=clean_meta,
            )
            moss_docs.append(doc_info)
            self._chunks_by_id[chunk.id] = chunk

        added, updated = self._index.add_documents(moss_docs, embeddings)
        return added, updated

    def delete_chunks(self, chunk_ids: List[str]) -> int:
        """Delete chunks from the Moss index by ID."""
        deleted = self._index.delete_documents(chunk_ids)
        for cid in chunk_ids:
            self._chunks_by_id.pop(cid, None)
        return deleted

    def clear(self) -> None:
        """Clear all indexed documents."""
        self._index.clear()
        self._chunks_by_id.clear()

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        alpha: float = 0.8,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> moss_core.SearchResult:
        """
        Execute native Moss hybrid search.
        
        Args:
            query_text: Natural language search string.
            top_k: Number of candidates to retrieve.
            alpha: Hybrid search weight (0.0 = BM25/keyword only, 1.0 = dense vector only).
            filter_dict: Moss condition dict e.g. {"field": "doc_id", "condition": {"$eq": "intro"}}.
        """
        query_embedding = self.embedder.embed_text(query_text)
        return self._index.query(
            query_text,
            top_k,
            query_embedding,
            alpha=alpha,
            filter=filter_dict,
        )

    def get_chunk(self, chunk_id: str) -> Optional[Chunk]:
        """Retrieve chunk model by ID."""
        return self._chunks_by_id.get(chunk_id)

    def get_all_chunks(self) -> List[Chunk]:
        """Retrieve all registered chunks."""
        return list(self._chunks_by_id.values())

    def serialize_to_binary(self) -> bytes:
        """Serialize the native Moss index and chunk metadata to a binary payload."""
        serialized_idx = self._index.serialize()
        binary_index = moss_core.serializeToBinary(serialized_idx)
        
        # Package index bytes and chunk metadata
        meta_payload = {
            "index_name": self.index_name,
            "model_id": self.model_id,
            "chunks": [c.model_dump() for c in self._chunks_by_id.values()],
        }
        meta_bytes = json.dumps(meta_payload).encode("utf-8")
        meta_len = len(meta_bytes).to_bytes(4, byteorder="big")
        
        return meta_len + meta_bytes + binary_index

    def save_to_file(self, file_path: Union[str, Path]) -> None:
        """Save the serialized Moss index to a .moss binary file."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self.serialize_to_binary()
        path.write_bytes(data)

    def load_from_binary(self, binary_data: bytes) -> int:
        """Load index and chunk metadata from binary bytes."""
        meta_len = int.from_bytes(binary_data[:4], byteorder="big")
        meta_bytes = binary_data[4 : 4 + meta_len]
        index_bytes = binary_data[4 + meta_len :]

        meta = json.loads(meta_bytes.decode("utf-8"))
        self.index_name = meta.get("index_name", self.index_name)
        self.model_id = meta.get("model_id", self.model_id)

        chunks_data = meta.get("chunks", [])
        self._chunks_by_id.clear()
        moss_docs: List[DocumentInfo] = []
        for cd in chunks_data:
            c = Chunk(**cd)
            self._chunks_by_id[c.id] = c
            moss_docs.append(DocumentInfo(id=c.id, text=c.text, metadata=c.metadata))

        deserialized_ser = moss_core.deserializeFromBinary(index_bytes)
        self._index = moss_core.Index(self.index_name, self.model_id)
        self._index.deserialize(deserialized_ser, moss_docs)
        return self._index.doc_count

    def load_from_file(self, file_path: Union[str, Path]) -> int:
        """Load index from a .moss file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Moss index file not found: {path}")
        return self.load_from_binary(path.read_bytes())
