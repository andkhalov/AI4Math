#!/usr/bin/env python3
"""AI4Science wizard — настройка .env при первой установке.

Спрашивает ключ Yandex AI Studio, folder id и модель по умолчанию,
записывает .env в корень репозитория. Только стандартная библиотека.

Неинтерактивный режим (CI, скрипты): заданы переменные окружения
YANDEX_CLOUD_API_KEY и YANDEX_CLOUD_FOLDER, а stdin не терминал или
AI4SCIENCE_WIZARD_NONINTERACTIVE=1 → .env пишется без вопросов.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

REPO = Path(__file__).resolve().parent.parent
ENV_FILE = REPO / ".env"

GREEN, YELLOW, BOLD, RESET = "\033[0;32m", "\033[0;33m", "\033[1m", "\033[0m"
DEFAULT_MODEL = "qwen3.6-35b-a3b/latest"
DEFAULT_PLANNER = "qwen3-235b-a22b-fp8/latest"
DEFAULT_LEAN_URL = "https://scilibai.ru/grag"

MODELS = [
    ("qwen3.6-35b-a3b/latest", "Qwen 3.6 35B A3B — быстрая, модель курса. Рекомендуется."),
    ("qwen3-235b-a22b-fp8/latest", "Qwen 3 235B — точнее, медленнее и дороже."),
    ("deepseek-v4-flash/latest", "DeepSeek V4 Flash — альтернатива для сравнения."),
    ("aliceai-llm/latest", "Alice AI LLM — модель Яндекса."),
    ("aliceai-llm-flash/latest", "Alice AI LLM Flash — быстрая, окно 64k."),
]


def banner() -> None:
    print(f"""
  ─── AI4Science wizard ───────────────────────────────────────
    Настройка .env: Yandex AI Studio, модель, Lean checker
  ─────────────────────────────────────────────────────────────
""")


def ask(label: str, default: str | None = None, secret: bool = False) -> str:
    hint = f" [{default}]" if default and not secret else ""
    prompt = f"  {label}{hint}: "
    try:
        if secret:
            import getpass
            val = getpass.getpass(prompt)
        else:
            val = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print("\nОтменено.")
        sys.exit(1)
    val = val.strip()
    return default if (not val and default is not None) else val


def ask_choice(label: str, options: list[tuple[str, str]], default: int = 0) -> str:
    print(f"\n  {BOLD}{label}{RESET}")
    for i, (key, desc) in enumerate(options, 1):
        marker = " (по умолчанию)" if i - 1 == default else ""
        print(f"    [{i}] {key}{marker}\n        {desc}")
    while True:
        raw = ask("Номер", default=str(default + 1))
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print(f"  {YELLOW}Введи число от 1 до {len(options)}.{RESET}")


def write_env(api_key: str, folder: str, model: str, lean_url: str = DEFAULT_LEAN_URL, brave: str = "") -> None:
    lines = [
        "# AI4Science .env — сгенерировано cli/wizard.py. Не коммитить.",
        "",
        "# === Yandex AI Studio ===",
        f"YANDEX_CLOUD_API_KEY={api_key}",
        f"YANDEX_CLOUD_FOLDER={folder}",
        f"YANDEX_CLOUD_MODEL={model}",
        f"YANDEX_PLANNER_MODEL={DEFAULT_PLANNER}",
        "",
        "# === Lean checker ===",
        f"LEAN_CHECKER_URL={lean_url}",
        "",
        "# === Необязательные настройки ===",
        f"BRAVE_API_KEY={brave}" if brave else "# BRAVE_API_KEY=            # поиск через Brave вместо DuckDuckGo",
        "# GOOSE_CONTEXT_LIMIT=128000",
        "",
    ]
    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    env_key = os.environ.get("YANDEX_CLOUD_API_KEY") or os.environ.get("YANDEX_AI_API", "")
    env_folder = os.environ.get("YANDEX_CLOUD_FOLDER", "")
    non_interactive = bool(env_key and env_folder) and (
        os.environ.get("AI4SCIENCE_WIZARD_NONINTERACTIVE") == "1" or not sys.stdin.isatty()
    )
    if non_interactive:
        write_env(env_key, env_folder,
                  os.environ.get("YANDEX_CLOUD_MODEL", DEFAULT_MODEL),
                  os.environ.get("LEAN_CHECKER_URL", DEFAULT_LEAN_URL),
                  os.environ.get("BRAVE_API_KEY", ""))
        print(f"[ok] .env записан из переменных окружения: {ENV_FILE}")
        return 0

    banner()
    if ENV_FILE.exists():
        print(f"  {YELLOW}[warn]{RESET} {ENV_FILE} уже существует.")
        if ask("Перезаписать? (y/N)", default="N").lower() not in ("y", "yes", "д", "да"):
            print("  Оставляю существующий .env без изменений.")
            return 0

    print("  Ключ и folder id Yandex AI Studio выдаются на курсе.")
    print("  Самостоятельно: https://yandex.cloud/ru/docs/ai-studio/quickstart")
    print()
    api_key = ask("YANDEX_CLOUD_API_KEY", secret=True)
    if len(api_key) < 20:
        print(f"  {YELLOW}Ключ выглядит коротким. Продолжаю; doctor это покажет.{RESET}")
    folder = ask("YANDEX_CLOUD_FOLDER (вида b1g...)")
    if folder and not folder.startswith("b1"):
        print(f"  {YELLOW}Folder id обычно начинается с 'b1'. Продолжаю.{RESET}")
    model = ask_choice("Модель по умолчанию", MODELS, default=0)
    print()
    print("  Lean checker: по умолчанию используется удалённый сервис курса.")
    print("  Для локального варианта: http://localhost:8888 и ./setup.sh --with-lean-local.")
    lean_url = ask("LEAN_CHECKER_URL", default=DEFAULT_LEAN_URL)
    brave = ask("BRAVE_API_KEY (Enter — пропустить, будет DuckDuckGo)", default="")
    write_env(api_key, folder, model, lean_url, brave)
    print()
    print(f"  {GREEN}[ok]{RESET} .env записан: {ENV_FILE}")
    print(f"  Модель: {BOLD}{model}{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
