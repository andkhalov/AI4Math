"""bin/ai4science.py и cli/wizard.py: .env, алиасы моделей, совместимость с 1.x,
флаги расширений, recipe, doctor без .env, MCP probe, неинтерактивный wizard."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def cli():
    return _load("ai4science_cli", REPO / "bin" / "ai4science.py")


@pytest.fixture
def wizard():
    return _load("ai4science_wizard", REPO / "cli" / "wizard.py")


def test_load_env_handles_quotes_and_comments(cli, tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "# comment\n\nYANDEX_CLOUD_API_KEY=abc\nTOKEN=\"id|hash=with=equals\"\n"
        "SINGLE='q'\nNOEQ\nSPACED = v \n",
        encoding="utf-8",
    )
    env = cli.load_env(p)
    assert env["YANDEX_CLOUD_API_KEY"] == "abc"
    assert env["TOKEN"] == "id|hash=with=equals"
    assert env["SINGLE"] == "q"
    assert env["SPACED"] == "v"
    assert "NOEQ" not in env


def test_load_env_missing_file(cli, tmp_path):
    assert cli.load_env(tmp_path / "nope") == {}


def test_resolve_model_aliases(cli):
    assert cli.resolve_model("") == cli.DEFAULT_MODEL
    assert cli.resolve_model("qwen") == "qwen3.6-35b-a3b/latest"
    assert cli.resolve_model("qwen235") == "qwen3-235b-a22b-fp8/latest"
    assert cli.resolve_model("deepseek") == "deepseek-v4-flash/latest"
    assert cli.resolve_model("gpt-oss") == "gpt-oss-120b/latest"
    assert cli.resolve_model("yandexgpt-5.1") == "yandexgpt-5.1/latest"
    assert cli.resolve_model("deepseek-v4-flash/latest") == "deepseek-v4-flash/latest"


def test_context_for(cli):
    assert cli.context_for("qwen3-235b-a22b-fp8/latest") == 262_144
    assert cli.context_for("aliceai-llm-flash/latest") == 65_536
    assert cli.context_for("unknown-model/latest") == cli.DEFAULT_CONTEXT
    assert cli.format_context(262_144) == "256k" and cli.format_context(1_048_576) == "1M"


def test_model_aliases_and_uri(cli):
    assert cli.resolve_model("alice") == "aliceai-llm/latest"
    assert cli.resolve_model("alice-flash") == "aliceai-llm-flash/latest"
    assert cli.model_uri("b1f", "alice") == "gpt://b1f/aliceai-llm/latest"
    assert cli.model_uri("b1f", "aliceai-llm-flash/latest") == "gpt://b1f/aliceai-llm-flash/latest"
    assert cli.model_uri("b1f", "gpt://b1x/qwen3.6-35b-a3b/latest") == "gpt://b1x/qwen3.6-35b-a3b/latest"
    for alias, slug, _, _ in cli.CATALOG:
        assert cli.resolve_model(alias) == slug


def test_compaction_fits_smallest_window(cli):
    """После /model окно не пересчитывается: история + ответ помещаются в любое окно каталога."""
    assert cli.COMPACT_AT_TOKENS + cli.MAX_OUTPUT_TOKENS < min(cli.MODEL_CONTEXT.values())
    assert cli.COMPACT_AT_TOKENS >= 30_000


def test_models_command_lists_aliases():
    rc = subprocess.run([sys.executable, str(REPO / "bin" / "ai4science.py"), "models"],
                        capture_output=True, text=True, encoding="utf-8")
    assert rc.returncode == 0
    for alias in ("qwen", "qwen235", "deepseek", "gptoss", "junior", "alice", "alice-flash"):
        assert alias in rc.stdout
    assert "/model" in rc.stdout


def test_apply_env_legacy_names(cli, monkeypatch):
    for k in ("YANDEX_CLOUD_API_KEY", "YANDEX_AI_API", "YANDEX_CLOUD_MODEL",
              "AI4SCIENCE_MODEL", "AI4MATH_MODEL", "AI4SCIENCE_QUIET", "AI4MATH_QUIET"):
        monkeypatch.delenv(k, raising=False)
    cli.apply_env({"YANDEX_AI_API": "legacy-key", "AI4MATH_MODEL": "qwen235", "AI4MATH_QUIET": "1"})
    import os
    assert os.environ["YANDEX_CLOUD_API_KEY"] == "legacy-key"
    assert os.environ["AI4SCIENCE_QUIET"] == "1"
    assert cli.resolve_model(os.environ["YANDEX_CLOUD_MODEL"]) == "qwen3-235b-a22b-fp8/latest"


def test_apply_env_new_names_win(cli, monkeypatch):
    monkeypatch.setenv("YANDEX_CLOUD_API_KEY", "from-shell")
    cli.apply_env({"YANDEX_CLOUD_API_KEY": "from-env-file", "YANDEX_AI_API": "legacy"})
    import os
    assert os.environ["YANDEX_CLOUD_API_KEY"] == "from-shell"


def test_build_goose_ext_args(cli):
    exts = [
        {"type": "builtin", "name": "developer"},
        {"type": "stdio", "name": "ai4science", "cmd": "bin/ai4science-mcp", "args": []},
        {"type": "stdio", "name": "my", "cmd": "/abs/python", "args": ["/abs/tool.py"]},
    ]
    args = cli.build_goose_ext_args(exts)
    assert args[:2] == ["--with-builtin", "developer"]
    assert args[2] == "--with-extension"
    assert str(REPO / "bin" / "ai4science-mcp") in args[3]
    if cli.IS_WINDOWS:
        assert args[3].rstrip("'").endswith(".bat")
    else:
        assert not args[3].rstrip("'").endswith(".bat")
    assert "/abs/tool.py" in args[5]


def test_recipe_parses(cli):
    instructions, extensions = cli.parse_recipe()
    assert "AI4Science" in instructions
    assert "AGENT.md" in instructions
    names = [e["name"] for e in extensions]
    assert "developer" in names and "ai4science" in names
    for e in extensions:
        if e.get("type") == "stdio":
            shim = REPO / e["cmd"]
            assert shim.exists(), f"shim из recipe не найден: {shim}"
            assert (REPO / (e["cmd"] + ".bat")).exists(), "нет Windows-шима"


def test_help_runs():
    rc = subprocess.run([sys.executable, str(REPO / "bin" / "ai4science.py"), "--help"],
                        capture_output=True, text=True, encoding="utf-8")
    assert rc.returncode == 0
    assert "AI4Science" in rc.stdout
    assert "ai4science run" in rc.stdout
    assert "/model" in rc.stdout and "ai4science models" in rc.stdout


def test_doctor_without_env_exits_1(cli, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ENV_FILE", tmp_path / ".env")
    with pytest.raises(SystemExit) as ei:
        cli.doctor()
    assert ei.value.code == 1


def test_probe_mcp_lists_tools(cli):
    """Реальный запуск MCP-сервера через shim: ≥10 инструментов, без сети."""
    tools, err = cli.probe_mcp(env_vars={"AI4SCIENCE_LEAN_DISABLED": "1"}, timeout=30)
    assert err == "", err
    assert tools is not None and len(tools) >= cli.MIN_TOOLS
    for name in ("lean_check", "web_search", "pdf_read", "load_skill", "token_budget"):
        assert name in tools


def test_wizard_non_interactive(wizard, tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    monkeypatch.setattr(wizard, "ENV_FILE", env_file)
    monkeypatch.setenv("YANDEX_CLOUD_API_KEY", "k" * 40)
    monkeypatch.setenv("YANDEX_CLOUD_FOLDER", "b1test")
    monkeypatch.setenv("AI4SCIENCE_WIZARD_NONINTERACTIVE", "1")
    monkeypatch.delenv("YANDEX_CLOUD_MODEL", raising=False)
    assert wizard.main() == 0
    text = env_file.read_text(encoding="utf-8")
    assert "YANDEX_CLOUD_API_KEY=" + "k" * 40 in text
    assert "YANDEX_CLOUD_FOLDER=b1test" in text
    assert f"YANDEX_CLOUD_MODEL={wizard.DEFAULT_MODEL}" in text
    assert "LEAN_CHECKER_URL=" in text
