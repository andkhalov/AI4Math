"""Shared pytest fixtures and PDF helpers for AI4Math test suite.

The suite is split into three layers:

- `test_helpers.py` / `test_skills.py` / `test_pdf.py` / `test_lean_mocked.py` —
  pure unit tests. No network, no external services. Fast, deterministic.

- `test_network.py` — integration tests that hit real DuckDuckGo / Loogle /
  LeanSearch / arxiv. Skipped unless `AI4MATH_TEST_NETWORK=1` is set.

- The Lean verification endpoint is never required to be up. Tests that care
  about its behaviour mock `requests.post`/`requests.get` to simulate both
  the happy path and OFFLINE transients.
"""
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _build_minimal_pdf(text: str) -> bytes:
    """Build a minimal single-page PDF 1.4 containing one text string.

    Hand-rolled so the test suite stays stdlib-only (no reportlab/fpdf2).
    Verified to round-trip through pypdf's `extract_text()`.
    """
    parts: list[bytes] = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
    ]
    body = b"BT /F1 12 Tf 72 720 Td (" + text.encode("latin-1", "replace") + b") Tj ET"
    parts.append(b"<</Length " + str(len(body)).encode() + b">>\nstream\n" + body + b"\nendstream")
    parts.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")

    out = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets: list[int] = []
    for i, segment in enumerate(parts, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + segment + b"\nendobj\n"

    xref_start = len(out)
    out += b"xref\n0 " + str(len(parts) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        b"trailer <</Size " + str(len(parts) + 1).encode() + b"/Root 1 0 R>>\n"
        b"startxref\n" + str(xref_start).encode() + b"\n%%EOF\n"
    )
    return out


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Tiny 1-page PDF containing known text. Used by pdf_info/read/search tests."""
    p = tmp_path / "sample.pdf"
    p.write_bytes(_build_minimal_pdf("Hello Goedel machine theorem self-reference"))
    return p


@pytest.fixture
def skills_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated skills directory populated with two fixture skills.

    Monkeypatches ai4math_mcp.SKILLS_DIR so list_skills/load_skill see
    exactly these files, not the repo-level skills/.
    """
    d = tmp_path / "skills"
    d.mkdir()
    (d / "python.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: python
            description: Python execution loop and venv discipline
            triggers: python, .py, pytest
            combines_with: debug-loop, markdown
            ---
            # Python skill body
            Use venvs, write tests, run them.
            """
        ),
        encoding="utf-8",
    )
    (d / "latex.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: latex
            description: LaTeX preamble and compile loop
            triggers: latex, tex, pdflatex
            combines_with: lean, markdown
            ---
            # LaTeX skill body
            """
        ),
        encoding="utf-8",
    )
    # No frontmatter file — must still be listed by stem
    (d / "bare.md").write_text("# bare\nno frontmatter", encoding="utf-8")

    import ai4math_mcp
    monkeypatch.setattr(ai4math_mcp, "SKILLS_DIR", d)
    return d


@pytest.fixture
def m():
    """The ai4math_mcp module, imported once and reused across tests."""
    import ai4math_mcp
    return ai4math_mcp


def pytest_collection_modifyitems(config, items):
    """Skip network-marked tests unless AI4MATH_TEST_NETWORK=1."""
    if os.environ.get("AI4MATH_TEST_NETWORK") == "1":
        return
    skip_network = pytest.mark.skip(reason="set AI4MATH_TEST_NETWORK=1 to run")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
