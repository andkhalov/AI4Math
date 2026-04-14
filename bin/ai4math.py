#!/usr/bin/env python3
"""AI4Math CLI — cross-platform Python entrypoint.

Заменяет старый bash-скрипт `bin/ai4math` — тот остался в `bin/_legacy/` как
референс. Делает ровно то же самое, но работает на Linux, macOS и Windows:

  * Находит корень репозитория по расположению этого файла
  * Читает `.env` через python-dotenv
  * Выставляет per-model GOOSE_CONTEXT_LIMIT и прочие тюнинги
  * Парсит `recipes/ai4math.yaml` — extracts `instructions` в tempfile и
    устанавливает GOOSE_SYSTEM_PROMPT_FILE_PATH; переводит `extensions`
    в `--with-builtin` / `--with-extension` флаги
  * Печатает ASCII-баннер (если AI4MATH_QUIET != 1)
  * Вызывает `goose session|run` через os.execvp (process replace)

Использование:
    ai4math                           интерактивная сессия (qwen по умолчанию)
    ai4math -m deepseek               выбор модели
    ai4math run "промпт"              одна задача и выход
    ai4math doctor                    проверка окружения
    ai4math --help                    справка
"""
from __future__ import annotations

import atexit
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

# Force UTF-8 on stdout/stderr for Windows — default cp1252 can't encode Cyrillic.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

# Цвета ANSI работают на Linux/macOS/Windows 10+; старые cmd.exe могут не поддерживать.
# Выключаем если stdout не tty или AI4MATH_NOCOLOR=1.
def _use_color() -> bool:
    if os.environ.get("AI4MATH_NOCOLOR") == "1":
        return False
    if not sys.stdout.isatty():
        return False
    return True

if _use_color():
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    RED = "\033[0;31m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
else:
    GREEN = YELLOW = RED = BOLD = RESET = ""


def say(msg: str) -> None:
    print(f"{GREEN}[ai4math]{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[ai4math]{RESET} {msg}")


def die(msg: str, code: int = 1) -> "NoReturn":  # noqa: F821
    print(f"{RED}[ai4math]{RESET} {msg}", file=sys.stderr)
    sys.exit(code)


# ---------- paths ----------

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
RECIPE_FILE = REPO / "recipes" / "ai4math.yaml"
ENV_FILE = REPO / ".env"
IS_WINDOWS = sys.platform == "win32"
GOOSE_BIN = REPO / ".tools" / ("goose.exe" if IS_WINDOWS else "goose")


# ---------- .env loader (stdlib only, no dotenv dep for Windows bootstrap) ----------

def load_env(path: Path) -> dict[str, str]:
    """Minimal .env parser: KEY=VALUE lines, ignores blanks and #-comments."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        # strip matching quotes if any
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        out[k] = v
    return out


# ---------- recipe parser ----------

def parse_recipe() -> tuple[str, list[dict]]:
    """Return (instructions_text, extensions_list) from the recipe."""
    try:
        import yaml  # type: ignore
    except ImportError:
        die("PyYAML не установлен. Запусти setup.sh или setup.bat для инициализации окружения.")
    with RECIPE_FILE.open(encoding="utf-8") as f:
        r = yaml.safe_load(f)
    instructions = r.get("instructions", "") or ""
    extensions = r.get("extensions", []) or []
    return instructions, extensions


def build_goose_ext_args(extensions: list[dict], use_lean: bool) -> list[str]:
    """Translate recipe `extensions` block into --with-* CLI flags."""
    args: list[str] = []
    for ext in extensions:
        t = ext.get("type")
        name = ext.get("name")
        if t == "builtin":
            args += ["--with-builtin", name]
        elif t == "stdio":
            # lean_check lives inside the unified ai4math MCP — we keep stdio=ai4math
            # always; AI4MATH_LEAN_DISABLED env var toggles just the lean tools.
            cmd = ext.get("cmd", "")
            if cmd and not Path(cmd).is_absolute():
                cmd = str(REPO / cmd)
            parts = [cmd] + [str(a) for a in (ext.get("args") or [])]
            env_prefix_keys = ext.get("env_keys") or []
            env_parts = []
            for k in env_prefix_keys:
                v = os.environ.get(k)
                if v:
                    env_parts.append(f"{k}={v}")
            full = " ".join(env_parts + [shlex.quote(p) for p in parts])
            args += ["--with-extension", full]
    return args


# ---------- banner ----------

def banner(model_nick: str, context_limit: int, lean_status: str) -> None:
    if os.environ.get("AI4MATH_QUIET") == "1":
        return
    model_labels = {
        "qwen": "Qwen3-235B A22B FP8 (Yandex AI Studio)",
        "deepseek": "DeepSeek-V3.2 (Yandex AI Studio)",
        "gptoss": "gpt-oss-120b (Yandex AI Studio)",
    }
    label = model_labels.get(model_nick, model_nick)
    ctx_k = context_limit // 1000
    threshold = os.environ.get("GOOSE_AUTO_COMPACT_THRESHOLD", "0.8")
    print(f"""
  ─── AI4Math ──────────────────────────────────────────────────
    научный code-агент
    Инференс  →  Контекст  →  Верификация
  ─────────────────────────────────────────────────────────────
    Модель:    {label}
    Контекст:  {ctx_k}k токенов, auto-compact при {threshold}
    Lean 4:    {lean_status}
  ─────────────────────────────────────────────────────────────
    Интенсив ШАД «AI4Math Intensive» — А. П. Халов
    Команды:  /exit — выйти,  /help — помощь Goose
""")


# ---------- doctor ----------

def doctor() -> None:
    print("=== AI4Math doctor ===")
    env = load_env(ENV_FILE)
    print(f".env: {'OK' if ENV_FILE.exists() else 'НЕТ'}")
    if not ENV_FILE.exists():
        sys.exit(1)
    api_key = env.get("YANDEX_AI_API", "")
    print(f"YANDEX_AI_API: {'установлен' if api_key else 'ПУСТО'} ({len(api_key)} символов)")
    print(f"YANDEX_CLOUD_FOLDER: {env.get('YANDEX_CLOUD_FOLDER', 'ПУСТО')}")
    print(f"ОС: {sys.platform}")
    if GOOSE_BIN.exists():
        try:
            out = subprocess.check_output([str(GOOSE_BIN), "--version"], text=True, stderr=subprocess.STDOUT)
            print(f"goose binary: {out.strip()}")
        except Exception as e:
            print(f"goose binary: ошибка запуска: {e}")
    else:
        print(f"goose binary: НЕ НАЙДЕН ({GOOSE_BIN})")
    venv_py = REPO / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")
    if venv_py.exists():
        try:
            out = subprocess.check_output([str(venv_py), "--version"], text=True, stderr=subprocess.STDOUT)
            print(f"python venv: {out.strip()}")
        except Exception as e:
            print(f"python venv: ошибка: {e}")
    else:
        print(f"python venv: НЕ НАЙДЕН ({venv_py})")
    lean_url = env.get("LEAN_CHECKER_URL", "http://localhost:8888")
    try:
        import urllib.request
        req = urllib.request.Request(f"{lean_url}/health", headers={"User-Agent": "ai4math-doctor"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                print(f"lean-checker ({lean_url}): UP")
            else:
                print(f"lean-checker ({lean_url}): HTTP {resp.status}")
    except Exception:
        print(f"lean-checker ({lean_url}): DOWN (lean_check вернёт graceful failure)")
    sys.exit(0)


# ---------- help ----------

def usage() -> None:
    print("""AI4Math — научный code-агент для курса ШАД AI4Math Intensive.

Использование:
    ai4math [опции]              интерактивная сессия (по умолчанию)
    ai4math run "<промпт>"       одна задача, вывод в консоль, выход
    ai4math doctor               проверка окружения (API-ключ, lean-checker)
    ai4math --help               эта справка

Опции:
    -m, --model <name>    выбор модели: qwen (default), deepseek, gptoss
    --no-lean             отключить lean_check (агент всё равно видит, graceful)

Переменные окружения:
    YANDEX_AI_API, YANDEX_CLOUD_FOLDER     — из .env
    AI4MATH_MODEL                          — модель по умолчанию
    AI4MATH_QUIET=1                        — не печатать баннер
    AI4MATH_NOCOLOR=1                      — ANSI цвета off
    LEAN_CHECKER_URL                       — shared lean-checker (default: localhost:8888)
    GOOSE_CONTEXT_LIMIT, GOOSE_MAX_TOKENS  — тюнинг Goose
    GOOSE_AUTO_COMPACT_THRESHOLD           — порог авто-компакции (0.8)

Продукт разработан в рамках интенсива ШАД «AI4Math Intensive» —
А. П. Халов | ФИЦ ИУ РАН | МФТИ | ШАД Яндекса.
""")


# ---------- main ----------

MODEL_DEFAULTS = {
    # nick: (env-key-for-slug, context_limit)
    "qwen": ("YANDEX_QWEN", 256_000),
    "deepseek": ("YANDEX_DEEPSEEK", 128_000),
    "gptoss": ("YANDEX_GPTOOS", 128_000),
}


def main(argv: list[str]) -> int:
    # Parse args — simple hand-rolled parser to keep stdlib-only
    args = argv[1:]
    model_nick = os.environ.get("AI4MATH_MODEL", "qwen")
    use_lean = True
    mode = "session"
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-h", "--help"):
            usage()
            return 0
        if a in ("-m", "--model"):
            if i + 1 >= len(args):
                die("--model: нужен аргумент")
            model_nick = args[i + 1]
            i += 2
            continue
        if a == "--no-lean":
            use_lean = False
            i += 1
            continue
        if a == "doctor":
            doctor()
            return 0  # unreachable
        if a == "run":
            mode = "run"
            i += 1
            continue
        if a == "--":
            positional += args[i + 1 :]
            break
        positional.append(a)
        i += 1

    # Normalize gpt-oss → gptoss
    if model_nick == "gpt-oss":
        model_nick = "gptoss"

    if model_nick not in MODEL_DEFAULTS:
        die(f"Неизвестная модель: {model_nick} (qwen|deepseek|gptoss)")

    if not ENV_FILE.exists():
        die(f"нет файла {ENV_FILE} — запусти setup.sh или setup.bat сначала")

    env_vars = load_env(ENV_FILE)
    # .env overlays existing os.environ (but os.environ wins if .env lacks it)
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)

    slug_key, model_ctx = MODEL_DEFAULTS[model_nick]
    slug = os.environ.get(slug_key)
    if not slug:
        die(f"{slug_key} не задан в .env")

    folder = os.environ.get("YANDEX_CLOUD_FOLDER")
    api_key = os.environ.get("YANDEX_AI_API")
    if not folder or not api_key:
        die("YANDEX_AI_API или YANDEX_CLOUD_FOLDER не заданы в .env")

    # --- Goose env ---
    goose_env = os.environ.copy()
    goose_env["GOOSE_PROVIDER"] = "openai"
    goose_env["OPENAI_HOST"] = "https://llm.api.cloud.yandex.net"
    goose_env["OPENAI_BASE_PATH"] = "/v1/chat/completions"
    goose_env["OPENAI_API_KEY"] = api_key
    goose_env["GOOSE_MODEL"] = f"gpt://{folder}/{slug}"
    goose_env.setdefault("GOOSE_CONTEXT_LIMIT", str(model_ctx))
    goose_env.setdefault("GOOSE_AUTO_COMPACT_THRESHOLD", "0.8")
    goose_env.setdefault("GOOSE_MAX_TOKENS", "16000")
    goose_env.setdefault("GOOSE_TEMPERATURE", "0.2")
    goose_env.setdefault("LEAN_CHECKER_URL", "http://localhost:8888")
    if not use_lean:
        goose_env["AI4MATH_LEAN_DISABLED"] = "1"

    # --- lean status for banner ---
    lean_url = goose_env["LEAN_CHECKER_URL"]
    lean_status = "отключён" if not use_lean else _probe_lean(lean_url)

    # --- parse recipe → tempfile + extension flags ---
    instructions, extensions = parse_recipe()
    sysprompt_fd, sysprompt_path = tempfile.mkstemp(suffix=".md", prefix="ai4math-sysprompt-")
    with os.fdopen(sysprompt_fd, "w", encoding="utf-8") as f:
        f.write(instructions)
    atexit.register(lambda p=sysprompt_path: Path(p).unlink(missing_ok=True))
    goose_env["GOOSE_SYSTEM_PROMPT_FILE_PATH"] = sysprompt_path

    ext_args = build_goose_ext_args(extensions, use_lean)

    banner(model_nick, int(goose_env["GOOSE_CONTEXT_LIMIT"]), lean_status)

    if not GOOSE_BIN.exists():
        die(f"goose binary не найден по пути {GOOSE_BIN}. Запусти setup заново.")

    cmd = [str(GOOSE_BIN)]
    if mode == "session":
        cmd += ["session", "--no-profile"] + ext_args
    elif mode == "run":
        if not positional:
            die("ai4math run: нужен текст промпта")
        prompt = " ".join(positional)
        cmd += ["run", "--no-profile"] + ext_args + ["-t", prompt]
    else:
        die(f"Неизвестный режим: {mode}")

    # Replace process on POSIX; fall back to subprocess on Windows where execvp is emulated
    os.environ.update(goose_env)
    if IS_WINDOWS:
        proc = subprocess.run(cmd, env=goose_env)
        return proc.returncode
    os.execvp(cmd[0], cmd)
    return 0  # unreachable


def _probe_lean(url: str) -> str:
    try:
        import urllib.request
        req = urllib.request.Request(f"{url}/health", headers={"User-Agent": "ai4math"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                return f"подключён ({url})"
            return f"HTTP {resp.status}"
    except Exception:
        return "тул доступен, сервис DOWN"


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        print()
        sys.exit(130)
