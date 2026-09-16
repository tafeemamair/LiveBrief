"""Pluggable embedding providers for Moss indexing and retrieval."""

from __future__ import annotations

import abc
import hashlib
import math
from typing import List, Optional
import numpy as np


class BaseEmbedder(abc.ABC):
    """Abstract base class for vector embedding generators."""

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """Vector dimensionality."""
        pass

    @abc.abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding vector for a single query or text chunk."""
        pass

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        return [self.embed_text(t) for t in texts]


class DeterministicEmbedder(BaseEmbedder):
    """
    Fast, deterministic semantic projection embedder.
    Generates consistent, unit-normalized vectors using character/word n-gram hashing.
    Zero external dependencies, ideal for hot-path retrieval and reproducible testing.
    """

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self._dimension

        vec = np.zeros(self._dimension, dtype=np.float32)
        tokens = text.lower().split()
        
        # Word-level features
        for token in tokens:
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % self._dimension
            sign = 1.0 if ((h >> 16) & 1) == 0 else -1.0
            vec[idx] += sign

        # Subword n-grams (3 to 5 chars)
        clean_text = "".join(c for c in text.lower() if c.isalnum() or c.isspace())
        for n in (3, 4, 5):
            for i in range(len(clean_text) - n + 1):
                gram = clean_text[i : i + n]
                h = int(hashlib.md5(gram.encode("utf-8")).hexdigest()[:8], 16)
                idx = h % self._dimension
                sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
                vec[idx] += 0.5 * sign

        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm
        else:
            vec[0] = 1.0

        return vec.tolist()


class CustomVectorEmbedder(BaseEmbedder):
    """Wraps an external embedding function or model."""

    def __init__(self, embed_fn, dimension: int) -> None:
        self._embed_fn = embed_fn
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> List[float]:
        vec = self._embed_fn(text)
        if len(vec) != self._dimension:
            raise ValueError(f"Expected embedding dim {self._dimension}, got {len(vec)}")
        return list(vec)
