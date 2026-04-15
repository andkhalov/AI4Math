"""Tests for lean_search_loogle / lean_search_leansearch / lean_search_moogle
and web_search / web_fetch with a mocked HTTP layer.
"""
from __future__ import annotations

import json

import pytest
import requests


class _Resp:
    def __init__(self, payload=None, text: str = "", status: int = 200,
                 headers: dict | None = None):
        self._payload = payload
        self.status_code = status
        self.text = text or (json.dumps(payload) if payload is not None else "")
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no payload")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def test_lean_search_loogle_ok(m, monkeypatch):
    def fake_get(url, params=None, timeout=None):
        assert "loogle" in url
        assert params["q"] == "Nat.add_comm"
        return _Resp(
            {
                "count": 2,
                "header": "results for Nat.add_comm",
                "hits": [
                    {
                        "name": "Nat.add_comm",
                        "type": "∀ (a b : ℕ), a + b = b + a",
                        "module": "Mathlib.Data.Nat.Basic",
                        "doc": "Addition on ℕ is commutative.",
                    },
                    {
                        "name": "AddCommMonoid.add_comm",
                        "type": "∀ (a b : α), a + b = b + a",
                        "module": "Mathlib.Algebra",
                    },
                ],
            }
        )

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.lean_search_loogle("Nat.add_comm")
    assert "Nat.add_comm" in out
    assert "Mathlib.Data.Nat.Basic" in out


def test_lean_search_loogle_empty(m, monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _Resp({"count": 0, "header": "no results", "hits": []})

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.lean_search_loogle("nonexistent_xyz")
    assert "нет результатов" in out or "no results" in out


def test_lean_search_loogle_error(m, monkeypatch):
    def fake_get(url, params=None, timeout=None):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.lean_search_loogle("x")
    assert out.startswith("ERROR")


def test_lean_search_leansearch_ok(m, monkeypatch):
    def fake_post(url, json=None, timeout=None):
        assert "leansearch" in url
        return _Resp(
            [
                [
                    {
                        "result": {
                            "name": ["Nat", "add_comm"],
                            "module_name": ["Mathlib", "Data", "Nat", "Basic"],
                            "type": "∀ (a b : ℕ), a + b = b + a",
                            "informal_description": "Addition is commutative.",
                        },
                        "distance": 0.123,
                    }
                ]
            ]
        )

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_search_leansearch("commutativity of addition")
    assert "Nat.add_comm" in out
    assert "Addition is commutative" in out


def test_lean_search_leansearch_empty(m, monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return _Resp([[]])

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_search_leansearch("nonsense")
    assert "пусто" in out


def test_lean_search_moogle_ok(m, monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return _Resp({"results": [{"name": "foo"}]})

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_search_moogle("x")
    assert "Moogle" in out


def test_lean_search_engines_status(m, monkeypatch):
    """lean_search_engines pings 4 endpoints. Mock them with a mix of
    OK and DOWN statuses and check the output lists all four.
    """
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        if "moogle" in url:
            raise requests.ConnectionError("down")
        return _Resp(text="ok", status=200)

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.lean_search_engines()
    assert "loogle" in out
    assert "leansearch" in out
    assert "moogle" in out
    assert "scilib" in out
    assert "DOWN" in out  # moogle
    # 4 engines probed
    assert len(calls) == 4


# ---------------- web_search / web_fetch ----------------

_DDG_HTML_FIXTURE = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Farxiv.org%2Fabs%2Fcs%2F0309048">Gödel Machines</a>
  <a class="result__snippet" href="#">Schmidhuber's self-referential universal problem solver.</a>
</div>
<div class="result">
  <a class="result__a" href="https://en.wikipedia.org/wiki/G%C3%B6del_machine">Wikipedia entry</a>
  <a class="result__snippet" href="#">A Gödel machine is a self-improving system...</a>
</div>
</body></html>
"""


def test_web_search_ddg_parses_results(m, monkeypatch):
    def fake_post(url, data=None, headers=None, timeout=None):
        assert "duckduckgo" in url
        return _Resp(text=_DDG_HTML_FIXTURE, status=200)

    monkeypatch.setattr(m.requests, "post", fake_post)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)

    out = m.web_search("Gödel machine", 5)
    assert "arxiv.org" in out
    assert "Wikipedia" in out
    assert "Schmidhuber" in out
    # uddg redirect must be unwrapped
    assert "duckduckgo.com/l/" not in out


def test_web_search_brave_used_when_key_set(m, monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        assert "brave" in url
        return _Resp(
            {
                "web": {
                    "results": [
                        {"url": "https://x", "title": "X", "description": "snip"}
                    ]
                }
            }
        )

    monkeypatch.setattr(m.requests, "get", fake_get)
    monkeypatch.setenv("BRAVE_API_KEY", "dummy")

    out = m.web_search("query", 3)
    assert "brave" in out
    assert "https://x" in out


def test_web_search_disabled(m, monkeypatch):
    monkeypatch.setattr(m, "WEB_DISABLED", True)
    out = m.web_search("x")
    assert "disabled" in out


def test_web_fetch_html(m, monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        return _Resp(
            text="<html><body><p>Hello <b>world</b></p></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.web_fetch("https://example.com")
    assert "Hello world" in out
    assert "<b>" not in out


def test_web_fetch_truncation(m, monkeypatch):
    big = "abc" * 2000

    def fake_get(url, headers=None, timeout=None):
        return _Resp(text=big, headers={"Content-Type": "text/plain"})

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.web_fetch("https://example.com", max_chars=500)
    assert "truncated" in out
    assert len(out) < 1500


def test_web_fetch_error(m, monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        raise requests.ConnectionError("nope")

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.web_fetch("https://example.com")
    assert out.startswith("ERROR")
