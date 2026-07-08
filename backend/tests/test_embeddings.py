"""Unit tests for the cosine-similarity math in EmbeddingCache.

Pure numpy — no database or OpenAI calls. Vectors are installed directly
via the cache's internal _set hook.
"""

import numpy as np
import pytest

from app.services.embeddings import EMBEDDING_DIMS, EmbeddingCache, normalize


def make_cache(vectors: dict[int, np.ndarray]) -> EmbeddingCache:
    cache = EmbeddingCache()
    ids = list(vectors)
    matrix = np.array([normalize(vectors[i]) for i in ids])
    cache._set(ids, matrix)
    return cache


def random_unit(rng: np.random.Generator) -> np.ndarray:
    return normalize(rng.standard_normal(EMBEDDING_DIMS))


def test_identical_vector_similarity_is_one() -> None:
    rng = np.random.default_rng(42)
    vec = random_unit(rng)
    cache = make_cache({1: vec})
    [(kb_id, score)] = cache.search(vec.tolist(), top_k=1)
    assert kb_id == 1
    assert score == pytest.approx(1.0, abs=1e-9)


def test_unrelated_vector_similarity_is_noticeably_lower() -> None:
    # random high-dimensional vectors are near-orthogonal: similarity ~ 0
    rng = np.random.default_rng(7)
    target, unrelated = random_unit(rng), random_unit(rng)
    cache = make_cache({1: target})
    [(_, score)] = cache.search(unrelated.tolist(), top_k=1)
    assert abs(score) < 0.2
    [(_, self_score)] = cache.search(target.tolist(), top_k=1)
    assert self_score - score > 0.8


def test_search_ranks_by_similarity_and_respects_top_k() -> None:
    rng = np.random.default_rng(3)
    query = random_unit(rng)
    noise = random_unit(rng)
    # entries at decreasing similarity to the query
    vectors = {
        10: query,
        20: normalize(0.8 * query + 0.2 * noise),
        30: normalize(0.5 * query + 0.5 * noise),
        40: noise,
    }
    cache = make_cache(vectors)

    results = cache.search(query.tolist(), top_k=3)
    assert [kb_id for kb_id, _ in results] == [10, 20, 30]
    scores = [score for _, score in results]
    assert scores == sorted(scores, reverse=True)
    assert all(-1.0 - 1e-9 <= s <= 1.0 + 1e-9 for s in scores)


def test_search_scales_are_irrelevant() -> None:
    # cosine similarity must ignore magnitude — only direction matters
    rng = np.random.default_rng(11)
    vec = random_unit(rng)
    cache = make_cache({1: vec * 5.0})
    [(_, score)] = cache.search((vec * 0.001).tolist(), top_k=1)
    assert score == pytest.approx(1.0, abs=1e-9)


def test_empty_cache_returns_no_results() -> None:
    cache = EmbeddingCache()
    assert cache.search([1.0] * EMBEDDING_DIMS) == []
    assert cache.size == 0


def test_top_k_larger_than_cache_returns_all() -> None:
    rng = np.random.default_rng(5)
    cache = make_cache({1: random_unit(rng), 2: random_unit(rng)})
    assert len(cache.search(random_unit(rng).tolist(), top_k=10)) == 2


def test_zero_query_vector_raises() -> None:
    rng = np.random.default_rng(9)
    cache = make_cache({1: random_unit(rng)})
    with pytest.raises(ValueError):
        cache.search([0.0] * EMBEDDING_DIMS)
