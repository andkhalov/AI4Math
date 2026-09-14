#!/usr/bin/env python3
"""AI4Science CLI — кроссплатформенная точка входа (Windows, macOS, Linux).

  * находит корень репозитория по расположению этого файла
  * читает `.env` (стандартная библиотека, без зависимостей)
  * собирает окружение Goose: провайдер openai → Yandex AI Studio
  * парсит `recipes/ai4science.yaml`: instructions → временный файл системного
    промпта; extensions → флаги `--with-builtin` / `--with-extension`
  * поднимает локальный token proxy (учёт расхода токенов, суточный лимит)
  * запускает `goose session|run`

Использование:
    ai4science                          интерактивная сессия
    ai4science -m <alias|slug>          другая модель Yandex AI Studio
    ai4science --mode approve           режим подтверждения инструментов
    ai4science run "промпт"             одна задача и выход
    ai4science doctor                   проверка окружения
    ai4science models                   модели и их алиасы
    ai4science --help                   справка
"""
from __future__ import annotations

import atexit
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")


def migrate_legacy_env() -> None:
    """Переменные версии 1.x (AI4MATH_*) принимаются как запасные для AI4SCIENCE_*."""
    for k, v in list(os.environ.items()):
        if k.startswith("AI4MATH_"):
            os.environ.setdefault("AI4SCIENCE_" + k[len("AI4MATH_"):], v)


migrate_legacy_env()


def _use_color() -> bool:
    if os.environ.get("AI4SCIENCE_NOCOLOR") == "1":
        return False
    return sys.stdout.isatty()


if _use_color():
    GREEN, YELLOW, RED, BOLD, RESET = "\033[0;32m", "\033[0;33m", "\033[0;31m", "\033[1m", "\033[0m"
else:
    GREEN = YELLOW = RED = BOLD = RESET = ""


def say(msg: str) -> None:
    print(f"{GREEN}[ai4science]{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[ai4science]{RESET} {msg}")


def die(msg: str, code: int = 1) -> "NoReturn":  # noqa: F821
    print(f"{RED}[ai4science]{RESET} {msg}", file=sys.stderr)
    sys.exit(code)


# ---------- paths and defaults ----------

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO / "src"))
from ai4science_models import (  # noqa: E402  каталог моделей общий с src/token_proxy.py
    CATALOG, COMPACT_AT_TOKENS, DEFAULT_CONTEXT, DEFAULT_MODEL, DEFAULT_PLANNER, MAX_OUTPUT_TOKENS,
    MODEL_ALIASES, MODEL_CONTEXT, context_for, format_context, model_uri, resolve_model,
)
RECIPE_FILE = REPO / "recipes" / "ai4science.yaml"
ENV_FILE = REPO / ".env"
IS_WINDOWS = sys.platform == "win32"
GOOSE_BIN = REPO / ".tools" / ("goose.exe" if IS_WINDOWS else "goose")
VENV_PY = REPO / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")

YANDEX_HOST = "https://llm.api.cloud.yandex.net"
# Данные Goose (сессии, журналы, история ввода) — внутри папки агента:
# удаление папки не оставляет следов, настройки отдельного Goose не затрагиваются.
GOOSE_HOME = REPO / ".goose"
DEFAULT_LEAN_URL = "https://scilibai.ru/grag"
DAILY_TOKEN_LIMIT = int(os.environ.get("AI4SCIENCE_DAILY_TOKEN_LIMIT", "3000000"))
VALID_GOOSE_MODES = {"auto", "smart_approve", "approve", "chat"}
MIN_TOOLS = 10

# ---------- .env ----------

def load_env(path: Path) -> dict[str, str]:
    """KEY=VALUE построчно; пустые строки и # игнорируются; кавычки снимаются.
    Значение может содержать `=`."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        out[k] = v
    return out


def apply_env(env: dict[str, str]) -> None:
    """Значения из .env → os.environ (уже заданные переменные важнее).
    Совместимость с .env версии 1.x: YANDEX_AI_API, AI4MATH_MODEL."""
    for k, v in env.items():
        os.environ.setdefault(k, v)
    migrate_legacy_env()
    if not os.environ.get("YANDEX_CLOUD_API_KEY") and os.environ.get("YANDEX_AI_API"):
        os.environ["YANDEX_CLOUD_API_KEY"] = os.environ["YANDEX_AI_API"]
    if not os.environ.get("YANDEX_CLOUD_MODEL") and os.environ.get("AI4SCIENCE_MODEL"):
        os.environ["YANDEX_CLOUD_MODEL"] = os.environ["AI4SCIENCE_MODEL"]


# ---------- recipe ----------

def parse_recipe() -> tuple[str, list[dict]]:
    try:
        import yaml  # type: ignore
    except ImportError:
        die("PyYAML не установлен. Запусти setup.bat (Windows) или ./setup.sh.")
    with RECIPE_FILE.open(encoding="utf-8") as f:
        r = yaml.safe_load(f)
    return (r.get("instructions", "") or ""), (r.get("extensions", []) or [])


def build_goose_ext_args(extensions: list[dict]) -> list[str]:
    """extensions из recipe → флаги Goose `--with-builtin` / `--with-extension`."""
    args: list[str] = []
    for ext in extensions:
        t, name = ext.get("type"), ext.get("name")
        if t == "builtin":
            args += ["--with-builtin", name]
        elif t == "stdio":
            cmd = ext.get("cmd", "")
            if cmd and not Path(cmd).is_absolute():
                cmd = str(REPO / cmd)
            if IS_WINDOWS and cmd.endswith("ai4science-mcp"):
                cmd += ".bat"
            parts = [cmd] + [str(a) for a in (ext.get("args") or [])]
            args += ["--with-extension", " ".join(shlex.quote(p) for p in parts)]
    return args


# ---------- budget ----------

_BUDGET_FILE = Path.home() / ".ai4science_budget.json"


def _today_token_usage() -> int:
    import json
    from datetime import date
    try:
        d = json.loads(_BUDGET_FILE.read_text())
        if d.get("date") == date.today().isoformat():
            return int(d.get("tokens", 0))
    except Exception:
        pass
    return 0


# ---------- MCP probe ----------

def probe_mcp(env_vars: dict | None = None, timeout: int = 10) -> tuple[list[str] | None, str]:
    """Запустить bin/ai4science-mcp, отправить tools/list, вернуть имена инструментов."""
    import json
    import time
    shim = REPO / "bin" / ("ai4science-mcp.bat" if IS_WINDOWS else "ai4science-mcp")
    if not shim.exists():
        return None, f"shim не найден: {shim}"
    try:
        probe_env = os.environ.copy()
        if env_vars:
            probe_env.update(env_vars)
        proc = subprocess.Popen(
            [str(shim)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=probe_env, text=True, encoding="utf-8",
        )
    except Exception as e:
        return None, f"не удалось запустить: {type(e).__name__}: {e}"
    try:
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "ai4science-preflight", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        for m in msgs:
            proc.stdin.write(json.dumps(m) + "\n")
        proc.stdin.flush()
    except Exception as e:
        proc.terminate()
        return None, f"stdin: {type(e).__name__}: {e}"
    deadline = time.time() + timeout
    tools = None
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if msg.get("id") == 2:
            tools = [t["name"] for t in msg.get("result", {}).get("tools", [])]
            break
    try:
        proc.terminate()
    except Exception:
        pass
    if tools is None:
        err = ""
        try:
            err = proc.stderr.read()[:500]
        except Exception:
            pass
        return None, f"нет ответа на tools/list (stderr: {err!r})"
    if len(tools) < MIN_TOOLS:
        return tools, f"ожидалось ≥{MIN_TOOLS} инструментов, получено {len(tools)}: {tools}"
    return tools, ""


def lean_status(url: str, timeout: float = 2.0) -> str:
    try:
        import urllib.request
        req = urllib.request.Request(f"{url.rstrip('/')}/health", headers={"User-Agent": "ai4science"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return f"подключён ({url})" if resp.status == 200 else f"HTTP {resp.status} ({url})"
    except Exception:
        return f"недоступен ({url}); lean_check вернёт сообщение об ошибке"


# ---------- banner / doctor / help ----------

def banner(model_slug: str, context_limit: int, goose_mode: str, lean: str, tokens_used: int,
           compact_threshold: float = 0.8) -> None:
    if os.environ.get("AI4SCIENCE_QUIET") == "1":
        return
    ctx = format_context(context_limit)
    aliases = " ".join(alias for alias, *_ in CATALOG)
    threshold = compact_threshold
    compact_at_k = int(context_limit * threshold) // 1000
    print(f"""
  ─── AI4Science ───────────────────────────────────────────────
    ИИ-ассистент исследователя
    Инференс  →  Контекст  →  Верификация
  ─────────────────────────────────────────────────────────────
    Модель:    {model_slug} (Yandex AI Studio)
    Контекст:  {ctx} токенов, сжатие истории при {compact_at_k}k
    Режим:     {goose_mode}
    Lean 4:    {lean}
    Бюджет:    {tokens_used:,} / {DAILY_TOKEN_LIMIT:,} токенов сегодня
  ─────────────────────────────────────────────────────────────
    Курс ШАД «ИИ-ассистенты для исследователя. AI4Science»
    Модель:    /model <алиас> — {aliases}
    Команды:   /status  /mode <режим>  /plan <задача>  /compact  /help  /exit
""")


def doctor() -> None:
    print("=== AI4Science doctor ===")
    env = load_env(ENV_FILE)
    print(f".env: {'OK' if ENV_FILE.exists() else 'НЕТ'} ({ENV_FILE})")
    if not ENV_FILE.exists():
        print("Запусти setup.bat / ./setup.sh или скопируй .env.example в .env")
        sys.exit(1)
    api_key = env.get("YANDEX_CLOUD_API_KEY") or env.get("YANDEX_AI_API", "")
    print(f"YANDEX_CLOUD_API_KEY: {'задан' if api_key else 'ПУСТО'} ({len(api_key)} символов)")
    print(f"YANDEX_CLOUD_FOLDER: {env.get('YANDEX_CLOUD_FOLDER') or 'ПУСТО'}")
    model = resolve_model(env.get("YANDEX_CLOUD_MODEL") or env.get("AI4SCIENCE_MODEL") or env.get("AI4MATH_MODEL", ""))
    print(f"модель: {model}")
    print(f"модель для /plan: {resolve_model(env.get('YANDEX_PLANNER_MODEL') or DEFAULT_PLANNER)}")
    print(f"данные Goose (сессии, журналы): {os.environ.get('GOOSE_PATH_ROOT') or GOOSE_HOME}")
    print(f"ОС: {sys.platform}, Python {sys.version.split()[0]}")
    if GOOSE_BIN.exists():
        try:
            out = subprocess.check_output([str(GOOSE_BIN), "--version"], text=True, stderr=subprocess.STDOUT, timeout=15)
            print(f"goose: {out.strip().splitlines()[-1]}")
        except Exception as e:
            print(f"goose: ошибка запуска: {e}")
    else:
        print(f"goose: НЕ НАЙДЕН ({GOOSE_BIN})")
    if VENV_PY.exists():
        try:
            out = subprocess.check_output([str(VENV_PY), "--version"], text=True, stderr=subprocess.STDOUT)
            print(f"python venv: {out.strip()}")
        except Exception as e:
            print(f"python venv: ошибка: {e}")
    else:
        print(f"python venv: НЕ НАЙДЕН ({VENV_PY})")

    lean_url = env.get("LEAN_CHECKER_URL", DEFAULT_LEAN_URL)
    tools, err = probe_mcp(env_vars={"LEAN_CHECKER_URL": lean_url}, timeout=12)
    mcp_ok = tools is not None and not err
    if mcp_ok:
        print(f"MCP ai4science: OK ({len(tools)} инструментов: {', '.join(tools)})")
    else:
        print(f"MCP ai4science: FAIL — {err}")
        if tools is not None:
            print(f"  получено: {tools}")
    print(f"lean-checker: {lean_status(lean_url, timeout=3)}")

    used = _today_token_usage()
    print(f"бюджет: {used:,} / {DAILY_TOKEN_LIMIT:,} (осталось {max(0, DAILY_TOKEN_LIMIT - used):,})")
    # Недоступность Lean-сервиса не считается ошибкой установки.
    sys.exit(0 if mcp_ok else 2)


def print_models(current: str = "") -> None:
    print("Модели Yandex AI Studio: алиас, модель, окно контекста")
    for alias, slug, ctx, note in CATALOG:
        mark = "*" if slug == current else " "
        print(f"  {mark} {alias:<12} {slug:<28} {format_context(ctx):>5}  {note}")
    print(f"""
  * модель по умолчанию из .env (YANDEX_CLOUD_MODEL)

При запуске:  ai4science -m <алиас>      например: ai4science -m alice
В сессии:     /model <алиас>             например: /model qwen235
              /model                     текущая модель;  /status — модель, режим, контекст
Принимаются также slug (aliceai-llm/latest) и полный URI (gpt://<folder>/...).
История сжимается при ~{COMPACT_AT_TOKENS // 1000}k токенов для любой модели списка.""")


def usage() -> None:
    print(f"""AI4Science — консольный агент курса ШАД «ИИ-ассистенты для исследователя. AI4Science».

Использование:
    ai4science [опции]               интерактивная сессия
    ai4science run "<промпт>"        одна задача, вывод в консоль, выход
    ai4science doctor                проверка окружения
    ai4science models                модели и их алиасы
    ai4science --help                эта справка

Опции:
    -m, --model <alias|slug>  модель Yandex AI Studio. По умолчанию из .env
                              (YANDEX_CLOUD_MODEL) или {DEFAULT_MODEL}.
                              Алиасы: {', '.join(MODEL_ALIASES)}
    --mode <name>             режим Goose: smart_approve (по умолчанию в сессии),
                              auto (по умолчанию в run), approve, chat
    --no-lean                 отключить инструменты Lean

Команды в сессии:
    /model [алиас]     показать или сменить модель: /model alice, /model qwen235
    /status            модель, режим, расход токенов, заполнение контекста
    /mode <режим>      auto | smart_approve | approve | chat
    /plan <задача>     план через модель планирования (YANDEX_PLANNER_MODEL)
    /compact           сжать историю; /clear — очистить, /new — новая сессия
    /help              все команды; /exit — выход

Переменные окружения (.env):
    YANDEX_CLOUD_API_KEY, YANDEX_CLOUD_FOLDER, YANDEX_CLOUD_MODEL, YANDEX_PLANNER_MODEL
    LEAN_CHECKER_URL, BRAVE_API_KEY
    AI4SCIENCE_QUIET=1, AI4SCIENCE_NOCOLOR=1, AI4SCIENCE_SKIP_PREFLIGHT=1
    AI4SCIENCE_LEAN_DISABLED=1, AI4SCIENCE_WEB_DISABLED=1, AI4SCIENCE_SKILLS_DIR
    AI4SCIENCE_DAILY_TOKEN_LIMIT (по умолчанию 3 000 000)
    GOOSE_CONTEXT_LIMIT, GOOSE_MAX_TOKENS, GOOSE_AUTO_COMPACT_THRESHOLD
    GOOSE_PATH_ROOT (данные Goose; по умолчанию <папка агента>/.goose)
Переменные версии 1.x (AI4MATH_*, YANDEX_AI_API) принимаются как запасные.
""")


# ---------- main ----------

def main(argv: list[str]) -> int:
    args = argv[1:]
    model_arg = ""
    mode = "session"
    use_lean = True
    goose_mode = os.environ.get("GOOSE_MODE", "")
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
            model_arg = args[i + 1]
            i += 2
            continue
        if a in ("--mode", "--goose-mode"):
            if i + 1 >= len(args):
                die("--mode: нужен аргумент (auto|smart_approve|approve|chat)")
            goose_mode = args[i + 1]
            if goose_mode not in VALID_GOOSE_MODES:
                die(f"--mode: неизвестный режим '{goose_mode}'. Допустимо: {', '.join(sorted(VALID_GOOSE_MODES))}")
            i += 2
            continue
        if a == "--no-lean":
            use_lean = False
            i += 1
            continue
        if a == "doctor":
            doctor()
            return 0
        if a == "models":
            env = load_env(ENV_FILE)
            print_models(resolve_model(env.get("YANDEX_CLOUD_MODEL") or env.get("AI4SCIENCE_MODEL", "")))
            return 0
        if a == "run":
            mode = "run"
            i += 1
            continue
        if a == "--":
            positional += args[i + 1:]
            break
        positional.append(a)
        i += 1

    if not goose_mode:
        goose_mode = "auto" if mode == "run" else "smart_approve"

    if not ENV_FILE.exists():
        die(f"нет файла {ENV_FILE} — запусти setup.bat / ./setup.sh или скопируй .env.example")
    apply_env(load_env(ENV_FILE))

    folder = os.environ.get("YANDEX_CLOUD_FOLDER", "")
    api_key = os.environ.get("YANDEX_CLOUD_API_KEY", "")
    if not folder or not api_key:
        die("YANDEX_CLOUD_API_KEY или YANDEX_CLOUD_FOLDER не заданы в .env")
    model_slug = resolve_model(model_arg or os.environ.get("YANDEX_CLOUD_MODEL", ""))
    context_limit = int(os.environ.get("GOOSE_CONTEXT_LIMIT", str(context_for(model_slug))))

    goose_env = os.environ.copy()
    goose_env["GOOSE_PROVIDER"] = "openai"
    goose_env["OPENAI_HOST"] = YANDEX_HOST
    goose_env["OPENAI_BASE_PATH"] = "/v1/chat/completions"
    goose_env["OPENAI_API_KEY"] = api_key
    goose_env["GOOSE_MODEL"] = f"gpt://{folder}/{model_slug}"
    planner = os.environ.get("YANDEX_PLANNER_MODEL", DEFAULT_PLANNER)
    if planner and planner.lower() != "off":
        goose_env.setdefault("GOOSE_PLANNER_PROVIDER", "openai")
        goose_env.setdefault("GOOSE_PLANNER_MODEL", f"gpt://{folder}/{resolve_model(planner)}")
    goose_env["GOOSE_CONTEXT_LIMIT"] = str(context_limit)
    # Одна точка сжатия для всех моделей каталога: после /model окно не пересчитывается.
    goose_env.setdefault("GOOSE_AUTO_COMPACT_THRESHOLD", f"{min(0.8, COMPACT_AT_TOKENS / context_limit):.3f}")
    goose_env.setdefault("GOOSE_MAX_TOKENS", str(MAX_OUTPUT_TOKENS))
    goose_env.setdefault("GOOSE_PATH_ROOT", str(GOOSE_HOME))
    goose_env.setdefault("GOOSE_TELEMETRY_ENABLED", "false")
    goose_env.setdefault("GOOSE_TEMPERATURE", "0.2")
    goose_env["GOOSE_MODE"] = goose_mode
    goose_env.setdefault("LEAN_CHECKER_URL", DEFAULT_LEAN_URL)
    if not use_lean:
        goose_env["AI4SCIENCE_LEAN_DISABLED"] = "1"
    lean = "отключён" if not use_lean else lean_status(goose_env["LEAN_CHECKER_URL"])

    instructions, extensions = parse_recipe()
    fd, sysprompt_path = tempfile.mkstemp(suffix=".md", prefix="ai4science-sysprompt-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(instructions)
    atexit.register(lambda p=sysprompt_path: Path(p).unlink(missing_ok=True))
    goose_env["GOOSE_SYSTEM_PROMPT_FILE_PATH"] = sysprompt_path
    ext_args = build_goose_ext_args(extensions)

    if os.environ.get("AI4SCIENCE_SKIP_PREFLIGHT") != "1":
        tools, perr = probe_mcp(env_vars={"LEAN_CHECKER_URL": goose_env["LEAN_CHECKER_URL"]}, timeout=12)
        if tools is None or perr:
            print(
                f"{RED}[ai4science]{RESET} MCP pre-flight FAIL: {perr}\n"
                f"{RED}[ai4science]{RESET} Goose не загрузит расширение ai4science — инструменты вернут -32002.\n"
                f"{RED}[ai4science]{RESET} Диагностика: ai4science doctor. Переустановка: удалить .venv и .tools, запустить setup.\n"
                f"{RED}[ai4science]{RESET} Пропустить проверку: AI4SCIENCE_SKIP_PREFLIGHT=1",
                file=sys.stderr,
            )
            return 3

    used = _today_token_usage()
    if used >= DAILY_TOKEN_LIMIT:
        print(
            f"{RED}[ai4science]{RESET} Суточный лимит токенов исчерпан: {used:,} из {DAILY_TOKEN_LIMIT:,}. "
            f"Сброс в полночь по локальному времени.",
            file=sys.stderr,
        )
        return 4

    proxy_py = REPO / "src" / "token_proxy.py"
    py_for_proxy = str(VENV_PY) if VENV_PY.exists() else sys.executable
    proxy_proc = subprocess.Popen(
        [py_for_proxy, str(proxy_py), "--upstream", YANDEX_HOST, "--limit", str(DAILY_TOKEN_LIMIT),
         "--folder", folder],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    proxy_port_line = ""
    try:
        proxy_port_line = proxy_proc.stdout.readline().strip()
        proxy_port = int(proxy_port_line)
    except (ValueError, TypeError):
        proxy_proc.terminate()
        die(f"token proxy не стартовал (stdout: {proxy_port_line!r})")
    atexit.register(lambda: proxy_proc.terminate())
    goose_env["OPENAI_HOST"] = f"http://127.0.0.1:{proxy_port}"

    banner(model_slug, context_limit, goose_mode, lean, used, float(goose_env["GOOSE_AUTO_COMPACT_THRESHOLD"]))

    if not GOOSE_BIN.exists():
        die(f"goose не найден: {GOOSE_BIN}. Запусти setup заново.")

    cmd = [str(GOOSE_BIN)]
    if mode == "session":
        cmd += ["session", "--no-profile"] + ext_args
    else:
        if not positional:
            die("ai4science run: нужен текст промпта")
        # --no-session: одноразовый запуск без записи в базу сессий Goose
        # (автоматизация, CI; исключает конфликт схемы с сессиями старых версий).
        cmd += ["run", "--no-profile", "--no-session"] + ext_args + ["-t", " ".join(positional)]

    proc = subprocess.run(cmd, env=goose_env)
    proxy_proc.terminate()
    return proc.returncode


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except KeyboardInterrupt:
        print()
        sys.exit(130)
