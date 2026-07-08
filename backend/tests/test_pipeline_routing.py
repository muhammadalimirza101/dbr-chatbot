"""Threshold routing rules from CLAUDE.md, as a pure function."""

from app.services.pipeline import (
    CACHE_THRESHOLD,
    RAG_THRESHOLD,
    Route,
    decide_route,
    normalize_for_repeat_check,
)


def test_high_similarity_english_returns_cache() -> None:
    assert decide_route(0.95, is_sales_moment=False, language="en") is Route.CACHE
    assert decide_route(CACHE_THRESHOLD, False, "en") is Route.CACHE


def test_sales_moment_always_goes_through_model() -> None:
    # pricing/availability/booking NEVER get a flat cached answer
    for similarity in (0.99, 0.85, 0.10):
        assert decide_route(similarity, is_sales_moment=True, language="en") is Route.RAG


def test_mid_band_is_rag() -> None:
    assert decide_route(0.80, False, "en") is Route.RAG
    assert decide_route(RAG_THRESHOLD, False, "en") is Route.RAG
    assert decide_route(0.8999, False, "en") is Route.RAG


def test_below_threshold_is_open() -> None:
    assert decide_route(0.74, False, "en") is Route.OPEN
    assert decide_route(0.0, False, "en") is Route.OPEN


def test_non_english_never_gets_english_cache_answer() -> None:
    # cached KB answers are English text; Roman Urdu/Urdu customers route
    # through the model so the reply-language rule holds
    assert decide_route(0.95, False, "roman_urdu") is Route.RAG
    assert decide_route(0.95, False, "ur") is Route.RAG


def test_repeat_normalization() -> None:
    a = normalize_for_repeat_check("What time is the ferry??")
    b = normalize_for_repeat_check("what time is the FERRY")
    assert a == b
    assert normalize_for_repeat_check("different question") != a
