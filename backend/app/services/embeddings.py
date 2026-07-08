"""KB embedding generation and in-memory cosine-similarity search.

Embeddings live in a plain FLOAT8[] column; similarity search happens here,
not in Postgres: all active KB vectors are held L2-normalized in a numpy
matrix, so a query is one vectorized dot product. Correct and fast for a KB
of up to a few thousand entries — no pgvector required.
"""

import asyncio
import logging

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBase
from app.services.ai import EMBEDDING_DIMS, EMBEDDING_MODEL, get_openai

logger = logging.getLogger(__name__)

# text-embedding-3-small caps input at 8192 tokens; cap characters well below
# that so a runaway input can't fail the call or waste spend
MAX_EMBED_CHARS = 6000


async def embed_text(text: str) -> list[float]:
    """Embed one text with text-embedding-3-small (1536 dims).

    Retry/backoff and timeout come from the shared client config.
    """
    cleaned = text.strip()[:MAX_EMBED_CHARS]
    if not cleaned:
        raise ValueError("cannot embed empty text")
    response = await get_openai().embeddings.create(
        model=EMBEDDING_MODEL, input=cleaned
    )
    embedding = response.data[0].embedding
    if len(embedding) != EMBEDDING_DIMS:
        raise ValueError(f"unexpected embedding dims: {len(embedding)}")
    return embedding


def normalize(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        raise ValueError("cannot normalize zero vector")
    return vector / norm


class EmbeddingCache:
    """All active KB embeddings as one L2-normalized numpy matrix."""

    def __init__(self) -> None:
        self._ids: list[int] = []
        self._matrix: np.ndarray = np.empty((0, EMBEDDING_DIMS))
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._ids)

    def _set(self, ids: list[int], vectors: np.ndarray) -> None:
        """Install a new matrix (rows already normalized, parallel to ids)."""
        self._ids = ids
        self._matrix = vectors

    async def load(self, session: AsyncSession) -> None:
        """Full reload from DB. Called on startup and by refresh()."""
        async with self._lock:
            rows = (
                await session.execute(
                    select(KnowledgeBase.id, KnowledgeBase.embedding).where(
                        KnowledgeBase.is_active.is_(True),
                        KnowledgeBase.embedding.is_not(None),
                    )
                )
            ).all()
            if rows:
                ids = [row.id for row in rows]
                matrix = np.array([row.embedding for row in rows], dtype=np.float64)
                norms = np.linalg.norm(matrix, axis=1, keepdims=True)
                norms[norms == 0] = 1.0  # guard: never divide by zero
                self._set(ids, matrix / norms)
            else:
                self._set([], np.empty((0, EMBEDDING_DIMS)))
            logger.info("KB embedding cache loaded: %d entries", self.size)

    async def refresh(self, session: AsyncSession) -> None:
        """Reload after any KB create/update/delete/toggle."""
        await self.load(session)

    def search(
        self, query_embedding: list[float], top_k: int = 3
    ) -> list[tuple[int, float]]:
        """Return up to top_k (kb_id, cosine similarity) pairs, best first."""
        if not self._ids:
            return []
        query = normalize(np.asarray(query_embedding, dtype=np.float64))
        similarities = self._matrix @ query  # rows are normalized -> cosine
        k = min(top_k, len(self._ids))
        top_indices = np.argpartition(similarities, -k)[-k:]
        top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]
        return [(self._ids[i], float(similarities[i])) for i in top_indices]


# process-wide singleton, loaded in the FastAPI lifespan
embedding_cache = EmbeddingCache()
