"""Tests for modular skill loading (list_skills, load_skill).

Uses an isolated skills_dir fixture so we don't depend on the repo-level
skills/ folder. The real skills/ folder is covered by test_real_skills.py.
"""
from __future__ import annotations

from pathlib import Path


def test_list_skills_shows_all_files(m, skills_dir):
    out = m.list_skills()
    assert "python" in out
    assert "latex" in out
    assert "bare" in out  # even without frontmatter


def test_list_skills_shows_descriptions(m, skills_dir):
    out = m.list_skills()
    assert "Python execution loop" in out
    assert "LaTeX preamble" in out


def test_list_skills_shows_triggers_and_combines(m, skills_dir):
    out = m.list_skills()
    assert "triggers:" in out
    assert "pytest" in out
    assert "combines with:" in out
    assert "debug-loop" in out


def test_list_skills_empty_dir(m, tmp_path, monkeypatch):
    empty = tmp_path / "empty_skills"
    empty.mkdir()
    monkeypatch.setattr(m, "SKILLS_DIR", empty)
    out = m.list_skills()
    assert "пусто" in out


def test_list_skills_missing_dir(m, tmp_path, monkeypatch):
    missing = tmp_path / "does_not_exist"
    monkeypatch.setattr(m, "SKILLS_DIR", missing)
    out = m.list_skills()
    assert out.startswith("ERROR")


def test_load_skill_happy_path(m, skills_dir):
    out = m.load_skill("python")
    assert "# Skill: python" in out
    assert "Python skill body" in out
    assert "Use venvs" in out


def test_load_skill_missing_returns_available_list(m, skills_dir):
    out = m.load_skill("nonexistent")
    assert out.startswith("ERROR")
    assert "python" in out
    assert "latex" in out


def test_load_skill_traversal_guard(m, skills_dir):
    """`load_skill('../../etc/passwd')` must not escape SKILLS_DIR."""
    out = m.load_skill("../../../etc/passwd")
    assert out.startswith("ERROR")
    # Specifically: it must not contain any content from /etc/passwd
    assert "root:" not in out


def test_load_skill_strips_md_suffix(m, skills_dir):
    out = m.load_skill("python.md")
    assert "# Skill: python" in out


def test_real_repo_skills_parseable(m):
    """Every skill file in the real repo must have valid frontmatter and load."""
    repo_skills = Path(__file__).resolve().parent.parent / "skills"
    assert repo_skills.exists(), f"repo skills dir missing: {repo_skills}"
    files = list(repo_skills.glob("*.md"))
    assert len(files) >= 5, f"expected at least 5 skills, got {len(files)}"
    for f in files:
        fm = m._parse_skill_frontmatter(f)
        assert fm.get("name"), f"{f.name}: missing `name` in frontmatter"
        assert fm.get("description"), f"{f.name}: missing `description`"
