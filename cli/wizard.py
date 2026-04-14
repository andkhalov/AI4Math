#!/usr/bin/env python3
"""AI4Math wizard — интерактивная настройка .env при первом запуске.

Спрашивает у пользователя API-ключ Yandex AI Studio и folder id, предлагает
выбрать модель по умолчанию и пишет .env в корне репозитория.

Без внешних зависимостей — использует только стандартную библиотеку.

Запускается из setup.sh. Для повторной настройки: удалить .env и перезапустить
setup.sh.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENV_FILE = REPO / ".env"
ENV_EXAMPLE = REPO / ".env.example"

GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
BOLD = "\033[1m"
RESET = "\033[0m"


def banner() -> None:
    print(f"""
  ─── AI4Math wizard ──────────────────────────────────────────
    Настройка .env для работы с Yandex AI Studio
    (open-source CLI-агент для курса ШАД AI4Math Intensive)
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
    if not val and default is not None:
        return default
    return val


def ask_choice(label: str, options: list[tuple[str, str]], default: int = 0) -> str:
    print(f"\n  {BOLD}{label}{RESET}")
    for i, (key, desc) in enumerate(options, 1):
        marker = " (default)" if i - 1 == default else ""
        print(f"    [{i}] {key}{marker}")
        print(f"        {desc}")
    while True:
        raw = ask("Номер", default=str(default + 1))
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print(f"  {YELLOW}Введи число от 1 до {len(options)}.{RESET}")


def main() -> int:
    banner()

    if ENV_FILE.exists():
        print(f"  {YELLOW}[warn]{RESET} {ENV_FILE} уже существует.")
        ans = ask("Перезаписать? (y/N)", default="N")
        if ans.lower() not in ("y", "yes", "д", "да"):
            print("  Оставляю существующий .env без изменений.")
            return 0

    print("  Провайдер: Yandex AI Studio (единственный поддерживаемый сейчас).")
    print("  Получить ключ и folder id: https://yandex.cloud/ru/docs/ai-studio/quickstart")
    print()

    api_key = ask("YANDEX_AI_API (API ключ)", secret=True)
    if not api_key or len(api_key) < 20:
        print(f"  {YELLOW}Ключ выглядит пустым или коротким. Продолжаю, но doctor это покажет.{RESET}")

    folder = ask("YANDEX_CLOUD_FOLDER (folder id, вида b1gi39jvrih75di87rqs)")
    if not folder or not folder.startswith("b1"):
        print(f"  {YELLOW}Folder id обычно начинается с 'b1'. Продолжаю.{RESET}")

    # Модель по умолчанию (исходя из benchmark Phase 3 — qwen > deepseek > gpt-oss)
    model = ask_choice(
        "Модель по умолчанию",
        [
            (
                "qwen",
                "Qwen3-235B-A22B-FP8 — быстрая (10-25 с), 96.7% success в Phase 3 benchmark, контекст 256k. Рекомендуется.",
            ),
            (
                "deepseek",
                "DeepSeek-V3.2 — thinking-модель, точнее на сложной математике, но в 2 раза медленнее. Контекст 128k.",
            ),
        ],
        default=0,
    )

    # Слоги моделей — фиксированы для Yandex AI Studio
    YANDEX_QWEN = "qwen3-235b-a22b-fp8/latest"
    YANDEX_DEEPSEEK = "deepseek-v32/latest"
    YANDEX_GPTOOS = "gpt-oss-120b/latest"  # хранится для совместимости, но не рекомендуется

    # Опционально: BRAVE_API_KEY
    print()
    brave = ask("BRAVE_API_KEY (опционально, Enter чтобы пропустить — будет DuckDuckGo)", default="")

    # Lean checker URL
    print()
    lean_url = ask("LEAN_CHECKER_URL", default="http://localhost:8888")

    # Запись
    lines = [
        "# AI4Math .env — сгенерировано wizard.py",
        "# Не коммить в git.",
        "",
        "# === Yandex AI Studio ===",
        f"YANDEX_AI_API={api_key}",
        f"YANDEX_CLOUD_FOLDER={folder}",
        "",
        "# Идентификаторы моделей (не трогай, если Yandex их не поменял)",
        f"YANDEX_QWEN={YANDEX_QWEN}",
        f"YANDEX_DEEPSEEK={YANDEX_DEEPSEEK}",
        f"YANDEX_GPTOOS={YANDEX_GPTOOS}",
        "",
        "# === Модель по умолчанию ===",
        f"AI4MATH_MODEL={model}",
        "",
        "# === Lean checker ===",
        f"LEAN_CHECKER_URL={lean_url}",
        "",
        "# === Опционально: Brave Search API (иначе DuckDuckGo) ===",
        f"BRAVE_API_KEY={brave}" if brave else "# BRAVE_API_KEY=",
        "",
    ]

    ENV_FILE.write_text("\n".join(lines))
    print()
    print(f"  {GREEN}[ok]{RESET} .env записан: {ENV_FILE}")
    print(f"  Модель по умолчанию: {BOLD}{model}{RESET}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
