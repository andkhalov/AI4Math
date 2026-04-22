"""Tests for the in-process artifact cache.

The cache trims heavy tool outputs so they don't balloon the conversation
history. Each heavy tool wraps its result in `_maybe_trim()`: short
outputs pass through unchanged, long ones return preview + artifact_id.
The agent can call `load_artifact(id)` to retrieve full content later.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clean_artifacts(m):
    """Reset the artifact cache before each test."""
    m._ARTIFACTS.clear()
    m._ARTIFACT_COUNTER = 0
    yield


def test_maybe_trim_short_passes_through(m):
    content = "short result"
    assert m._maybe_trim("test", content) == content
    assert len(m._ARTIFACTS) == 0


def test_maybe_trim_at_threshold(m):
    # Exactly at threshold — still short enough
    content = "a" * m.ARTIFACT_THRESHOLD
    assert m._maybe_trim("test", content) == content
    assert len(m._ARTIFACTS) == 0


def test_maybe_trim_long_is_trimmed(m):
    content = "x" * (m.ARTIFACT_THRESHOLD + 500)
    out = m._maybe_trim("test", content)
    assert len(out) < len(content)
    assert "artifact_id" in out
    assert "load_artifact" in out
    assert len(m._ARTIFACTS) == 1


def test_artifact_id_format(m):
    content = "y" * 2000
    out = m._maybe_trim("web_search", content)
    # id format: tool_0001
    assert "web_search_0001" in out


def test_artifact_counter_increments(m):
    m._maybe_trim("a", "x" * 2000)
    m._maybe_trim("b", "x" * 2000)
    m._maybe_trim("c", "x" * 2000)
    assert m._ARTIFACT_COUNTER == 3
    assert set(m._ARTIFACTS.keys()) == {"a_0001", "b_0002", "c_0003"}


def test_load_artifact_returns_full(m):
    content = "z" * 3000
    trimmed = m._maybe_trim("pdf_read", content)
    assert "pdf_read_0001" in trimmed
    full = m.load_artifact("pdf_read_0001")
    assert full == content


def test_load_artifact_missing_returns_error(m):
    out = m.load_artifact("nonexistent_9999")
    assert out.startswith("ERROR")
    assert "не найден" in out


def test_load_artifact_lists_available_on_miss(m):
    m._maybe_trim("web_search", "a" * 2000)
    m._maybe_trim("pdf_read", "b" * 2000)
    out = m.load_artifact("bogus")
    assert "web_search_0001" in out
    assert "pdf_read_0002" in out


def test_preview_contains_content_start(m):
    content = "BEGIN_MARKER " + "x" * 2000
    out = m._maybe_trim("test", content)
    assert "BEGIN_MARKER" in out


def test_preview_shows_original_size(m):
    content = "x" * 4567
    out = m._maybe_trim("test", content)
    assert "4,567" in out  # formatted size


def test_web_search_trims_large_output(m, monkeypatch):
    """web_search returning many results should trigger the artifact cache."""
    import json
    big_results = [
        {"url": f"https://example.com/{i}", "title": f"Result {i}",
         "snippet": "A" * 150}
        for i in range(10)
    ]
    def fake_ddg(query, num):
        return big_results[:num]
    monkeypatch.setattr(m, "_ddg_search", fake_ddg)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)

    out = m.web_search("test", 10)
    assert "artifact_id" in out
    assert len(m._ARTIFACTS) == 1

    # Full content recoverable
    aid = [k for k in m._ARTIFACTS.keys()][0]
    full = m.load_artifact(aid)
    assert "Result 9" in full  # last one


def test_pdf_read_trims_large_extract(m, sample_pdf, tmp_path):
    """Synthetic PDF is short — just confirm the wrapper doesn't break it."""
    out = m.pdf_read(str(sample_pdf), pages="1")
    # Sample PDF is tiny, should pass through untouched
    assert "Goedel" in out
    # No artifact created for short output
    assert len(m._ARTIFACTS) == 0


def test_lean_search_loogle_trims_when_large(m, monkeypatch):
    def fake_get(url, params=None, timeout=None):
        import json
        class R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {
                    "count": 20, "header": "many results",
                    "hits": [
                        {"name": f"Foo.bar_{i}",
                         "type": "a very long type signature that goes on and on " * 3,
                         "module": "Mathlib.Long.Module.Path",
                         "doc": "description " * 20}
                        for i in range(20)
                    ],
                }
        return R()
    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.lean_search_loogle("pattern")
    assert "artifact_id" in out
