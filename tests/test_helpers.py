"""Pure unit tests for helper functions that don't touch network/filesystem."""
from __future__ import annotations

import pytest
import requests


def test_truncate_short(m):
    assert m._truncate("hello", 100) == "hello"


def test_truncate_long(m):
    out = m._truncate("x" * 200, 50)
    assert len(out) == 50
    assert out.endswith("...")


def test_truncate_none(m):
    assert m._truncate(None, 10) == ""


def test_fmt_err(m):
    out = m._fmt_err("mytool", ValueError("boom"))
    assert out.startswith("ERROR [mytool]:")
    assert "ValueError" in out
    assert "boom" in out


def test_strip_html_basic(m):
    html = "<p>hello <b>world</b></p>"
    assert m._strip_html(html) == "hello world"


def test_strip_html_entities(m):
    html = "<p>a&nbsp;&amp;&lt;b&gt;&quot;</p>"
    assert m._strip_html(html) == 'a &<b>"'


def test_strip_html_scripts_removed(m):
    html = "<p>keep</p><script>alert('x')</script><p>more</p>"
    out = m._strip_html(html)
    assert "alert" not in out
    assert "keep" in out
    assert "more" in out


def test_strip_html_nested_whitespace(m):
    html = "<div>  a   \n\n b  </div>"
    assert m._strip_html(html) == "a b"


def test_parse_skill_frontmatter(tmp_path, m):
    f = tmp_path / "s.md"
    f.write_text(
        "---\nname: test\ndescription: a short one\ntriggers: foo, bar\n---\nbody",
        encoding="utf-8",
    )
    fm = m._parse_skill_frontmatter(f)
    assert fm == {"name": "test", "description": "a short one", "triggers": "foo, bar"}


def test_parse_skill_frontmatter_missing(tmp_path, m):
    f = tmp_path / "no.md"
    f.write_text("just body, no frontmatter", encoding="utf-8")
    assert m._parse_skill_frontmatter(f) == {}


def test_parse_skill_frontmatter_unclosed(tmp_path, m):
    f = tmp_path / "bad.md"
    f.write_text("---\nname: x\nno_close", encoding="utf-8")
    assert m._parse_skill_frontmatter(f) == {}


def test_pdf_parse_pages_range(m):
    assert m._pdf_parse_pages("1-3", 10) == [0, 1, 2]


def test_pdf_parse_pages_list(m):
    assert m._pdf_parse_pages("1,3,5", 10) == [0, 2, 4]


def test_pdf_parse_pages_mixed(m):
    assert m._pdf_parse_pages("1-2,5", 10) == [0, 1, 4]


def test_pdf_parse_pages_out_of_range(m):
    assert m._pdf_parse_pages("1-20", 5) == [0, 1, 2, 3, 4]


def test_pdf_parse_pages_empty(m):
    assert m._pdf_parse_pages("", 5) == []
    assert m._pdf_parse_pages("  ", 5) == []


def test_pdf_resolve_relative(m, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = m._pdf_resolve("foo.pdf")
    assert p == tmp_path / "foo.pdf"
    assert p.is_absolute()


def test_pdf_resolve_absolute(m, tmp_path):
    p = m._pdf_resolve(str(tmp_path / "bar.pdf"))
    assert p == tmp_path / "bar.pdf"


def test_pdf_resolve_tilde(m):
    p = m._pdf_resolve("~/x.pdf")
    assert "~" not in str(p)


def test_is_remote_unavailable_connection(m):
    assert m._is_remote_unavailable(requests.ConnectionError("refused"))


def test_is_remote_unavailable_timeout(m):
    assert m._is_remote_unavailable(requests.Timeout("slow"))


def test_is_remote_unavailable_ssl(m):
    import ssl
    assert m._is_remote_unavailable(ssl.SSLError("handshake"))


def test_is_remote_unavailable_not_network(m):
    assert not m._is_remote_unavailable(ValueError("bad json"))
    assert not m._is_remote_unavailable(KeyError("missing"))
