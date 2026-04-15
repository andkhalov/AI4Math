"""Integration tests that hit real external services.

Skipped by default. Run with:

    AI4MATH_TEST_NETWORK=1 pytest tests/test_network.py -v

These tests verify that the tools work against live DuckDuckGo, Loogle,
LeanSearch, and arxiv. They are essential for catching regressions in
HTML-scraping code (DDG changes their markup periodically) and for
validating that third-party JSON schemas haven't drifted.

The SciLib Lean verification endpoint is intentionally NOT tested here —
its public Tailscale Funnel is known to be flaky. That flakiness is
covered by OFFLINE-fallback tests in test_lean_mocked.py.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.network


def _skip_if_upstream_error(out: str, name: str) -> None:
    """Network tests should distinguish upstream flakiness from bugs in our
    code. If the tool returned a transport-level ERROR (timeout, DNS,
    connection refused), skip — the live service is down, not our code.
    """
    if out.startswith("ERROR") and any(
        marker in out
        for marker in ("Timeout", "ConnectionError", "SSLError", "NameResolution")
    ):
        pytest.skip(f"{name}: upstream transient failure: {out[:200]}")


def test_web_search_ddg_live(m):
    out = m.web_search("Lean 4 theorem prover", num_results=3)
    _skip_if_upstream_error(out, "duckduckgo")
    assert not out.startswith("ERROR")
    assert "http" in out
    assert "duckduckgo.com/l/" not in out  # redirects unwrapped


def test_web_fetch_live(m):
    out = m.web_fetch("https://example.com", max_chars=1000)
    _skip_if_upstream_error(out, "web_fetch")
    assert not out.startswith("ERROR")
    assert "Example Domain" in out


def test_lean_search_loogle_live(m):
    # Name-based lookup — more stable than pattern queries whose syntax
    # Loogle occasionally tweaks.
    out = m.lean_search_loogle("Nat.add_comm")
    _skip_if_upstream_error(out, "loogle")
    assert not out.startswith("ERROR")
    assert "add_comm" in out.lower()


def test_lean_search_leansearch_live(m):
    out = m.lean_search_leansearch("commutativity of addition on natural numbers", num_results=3)
    _skip_if_upstream_error(out, "leansearch")
    assert not out.startswith("ERROR")
    assert "add_comm" in out.lower() or "commutative" in out.lower()


def test_pdf_download_and_info_live(m, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    url = "https://arxiv.org/pdf/cs/0309048.pdf"
    out1 = m.pdf_download(url, "literature/")
    _skip_if_upstream_error(out1, "arxiv")
    assert out1.startswith("OK"), out1
    # Deterministic filename from URL basename
    saved = tmp_path / "literature" / "0309048.pdf"
    assert saved.exists(), f"expected {saved}, got: {out1}"

    out2 = m.pdf_info(str(saved))
    assert "Страниц:" in out2

    out3 = m.pdf_search(str(saved), "self-referential")
    assert "совпадений" in out3


def test_lean_search_engines_live_reports_status(m):
    out = m.lean_search_engines()
    for engine in ("loogle", "leansearch", "moogle", "scilib"):
        assert engine in out
