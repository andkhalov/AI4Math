"""Tests for lean_check / lean_health / lean_search_scilib with a mocked
HTTP layer. No real Lean checker needed.

Covers:
- SciLib schema happy path (success, sanity_ok)
- SciLib schema error classes (PARSE_ERROR, TACTIC_FAILURE, SANITY_CHECK_FAILED)
- Legacy lean-checker schema (old andkhalov/lean-checker)
- OFFLINE fallback: ConnectionError → retry → OFFLINE: message
- OFFLINE fallback on lean_health
- OFFLINE fallback on lean_search_scilib
- Schema routing based on URL (.../grag → scilib)
- AI4MATH_LEAN_DISABLED
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import requests


class _Resp:
    def __init__(self, payload=None, status: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status
        self.text = text or json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("no payload")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


# ---------------- lean_check: SciLib schema ----------------

def test_lean_check_scilib_success(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "scilib")
    monkeypatch.setattr(
        m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag"
    )

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["body"] = json
        return _Resp({"success": True, "time_ms": 42})

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example : 1 + 1 = 2 := by norm_num")
    assert out.startswith("OK")
    assert "42 ms" in out
    assert captured["url"].endswith("/check")
    assert "lean_code" in captured["body"]
    assert "timeout" in captured["body"]


def test_lean_check_scilib_parse_error(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "scilib")
    monkeypatch.setattr(
        m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag"
    )

    def fake_post(url, json=None, timeout=None):
        return _Resp(
            {
                "success": False,
                "sanity_ok": True,
                "error_class": "PARSE_ERROR",
                "error_message": "expected ':='",
            }
        )

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example : 1 + 1 = 2 by norm_num")  # missing :=
    assert out.startswith("ERROR [PARSE_ERROR]")
    assert "expected" in out


def test_lean_check_scilib_sanity_failed(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "scilib")
    monkeypatch.setattr(
        m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag"
    )

    def fake_post(url, json=None, timeout=None):
        return _Resp(
            {
                "success": False,
                "sanity_ok": False,
                "sanity_reason": "only `sorry` — not a proof",
            }
        )

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example : True := sorry")
    assert "SANITY_CHECK_FAILED" in out
    assert "sorry" in out


def test_lean_check_scilib_tactic_failure(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "scilib")
    monkeypatch.setattr(
        m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag"
    )

    def fake_post(url, json=None, timeout=None):
        return _Resp(
            {
                "success": False,
                "sanity_ok": True,
                "error_class": "TACTIC_FAILURE",
                "error_message": "linarith failed to close goal",
            }
        )

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example (a : ℝ) : a < a + 1 := by linarith")
    assert "TACTIC_FAILURE" in out
    assert "linarith" in out


def test_lean_check_scilib_non_json_body(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "scilib")
    monkeypatch.setattr(
        m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag"
    )

    def fake_post(url, json=None, timeout=None):
        return _Resp(status=200, text="not json")

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example : 1 + 1 = 2 := by norm_num")
    assert out.startswith("ERROR")
    assert "non-JSON" in out


def test_lean_check_scilib_http_500(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "scilib")
    monkeypatch.setattr(
        m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag"
    )

    def fake_post(url, json=None, timeout=None):
        return _Resp({"error": "oops"}, status=500)

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example : 1 + 1 = 2 := by norm_num")
    assert out.startswith("ERROR")
    assert "500" in out


# ---------------- lean_check: Legacy schema ----------------

def test_lean_check_legacy_success(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "lean-checker")
    monkeypatch.setattr(m, "LEAN_CHECKER_URL", "http://localhost:8888")

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["body"] = json
        return _Resp({"ok": True, "messages": []})

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example : 1 + 1 = 2 := by norm_num")
    assert out.startswith("OK")
    assert "code" in captured["body"]
    assert "import_line" in captured["body"]


def test_lean_check_legacy_error_with_diagnostics(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "lean-checker")
    monkeypatch.setattr(m, "LEAN_CHECKER_URL", "http://localhost:8888")

    def fake_post(url, json=None, timeout=None):
        return _Resp(
            {
                "ok": False,
                "messages": [
                    {
                        "severity": "error",
                        "line": 3,
                        "column": 12,
                        "message": "unknown identifier 'foo'",
                    }
                ],
            }
        )

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example : True := foo")
    assert "ERROR" in out
    assert "L3:C12" in out
    assert "unknown identifier" in out


# ---------------- OFFLINE fallback ----------------

def test_lean_check_offline_on_connection_error(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "scilib")
    monkeypatch.setattr(
        m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag"
    )
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example : 1 + 1 = 2 := by norm_num")
    assert out.startswith("OFFLINE")
    assert calls["n"] == 2, "must retry exactly once"
    assert "ConnectionError" in out


def test_lean_check_offline_on_timeout(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "scilib")
    monkeypatch.setattr(
        m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag"
    )

    def fake_post(url, json=None, timeout=None):
        raise requests.Timeout("slow")

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example : 1 + 1 = 2 := by norm_num")
    assert out.startswith("OFFLINE")


def test_lean_check_unexpected_error_is_not_offline(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_SCHEMA", "scilib")
    monkeypatch.setattr(
        m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag"
    )

    def fake_post(url, json=None, timeout=None):
        raise ValueError("unexpected")

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_check("example : 1 + 1 = 2 := by norm_num")
    assert out.startswith("ERROR")
    assert "unexpected" in out
    assert "OFFLINE" not in out


def test_lean_health_offline(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag")

    def fake_get(url, timeout=None):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.lean_health()
    assert out.startswith("OFFLINE")


def test_lean_health_ok(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_CHECKER_URL", "https://scilib.example.ts.net/grag")

    def fake_get(url, timeout=None):
        return _Resp({"status": "healthy", "service": "lean-grag"})

    monkeypatch.setattr(m.requests, "get", fake_get)
    out = m.lean_health()
    assert out.startswith("OK")
    assert "healthy" in out


def test_lean_check_disabled(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_DISABLED", True)
    out = m.lean_check("example : 1 + 1 = 2 := by norm_num")
    assert out.startswith("ERROR")
    assert "disabled" in out


def test_lean_health_disabled(m, monkeypatch):
    monkeypatch.setattr(m, "LEAN_DISABLED", True)
    out = m.lean_health()
    assert "disabled" in out


# ---------------- lean_search_scilib OFFLINE ----------------

def test_lean_search_scilib_offline(m, monkeypatch):
    monkeypatch.setattr(m, "SCILIB", "https://scilib.example.ts.net/grag")

    def fake_post(url, json=None, timeout=None):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_search_scilib("example : 1 + 1 = 2 := sorry")
    assert out.startswith("OFFLINE")
    assert "lean_search_loogle" in out  # suggests fallback


def test_lean_search_scilib_happy(m, monkeypatch):
    monkeypatch.setattr(m, "SCILIB", "https://scilib.example.ts.net/grag")

    def fake_post(url, json=None, timeout=None):
        return _Resp(
            {
                "hints_text": "Try: apply Nat.add_comm\nTry: rw [Nat.zero_add]",
                "hints_list": [
                    {
                        "role": "apply",
                        "name": "Nat.add_comm",
                        "signature": "∀ (a b : ℕ), a + b = b + a",
                    }
                ],
                "processing_time_ms": 17,
            }
        )

    monkeypatch.setattr(m.requests, "post", fake_post)
    out = m.lean_search_scilib("example (a b : ℕ) : a + b = b + a := sorry")
    assert "Nat.add_comm" in out
    assert "apply" in out
