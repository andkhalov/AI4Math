#!/usr/bin/env bash
# AI4Math setup — ставит Goose + Python venv + MCP зависимости + wizard.
#
# Usage:
#   ./setup.sh                установка без Lean
#   ./setup.sh --with-lean    + попытка поднять lean-checker Docker-контейнер

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

say()  { echo -e "${GREEN}[AI4Math]${RESET} $*"; }
warn() { echo -e "${YELLOW}[AI4Math]${RESET} $*"; }
die()  { echo -e "${RED}[AI4Math]${RESET} $*" >&2; exit 1; }

WITH_LEAN_LOCAL=0
for arg in "$@"; do
    case "$arg" in
        --with-lean-local|--with-lean) WITH_LEAN_LOCAL=1 ;;
        -h|--help)
            cat <<EOF
AI4Math setup.

Usage:
  ./setup.sh                     установка с remote Lean checker (default)
                                 — ничего локально поднимать не надо
  ./setup.sh --with-lean-local   + поднять локальный Docker lean-checker
                                 (Mathlib 4.24, первая сборка 1.5-2.5 ч)

Шаги:
  1. Проверка Python 3.10+ и системных зависимостей
  2. Создание .venv и установка Python-пакетов из requirements.txt
  3. Установка Goose CLI в .tools/ (локально, без root)
  4. Запуск cli/wizard.py для настройки .env (если .env ещё нет)
  5. (опционально) docker compose up -d в vendor/lean-checker
  6. symlink в \$HOME/.local/bin/ai4math для глобальной команды

По умолчанию Lean верификация идёт через публичный SciLib-GRC21
endpoint (https://scilib.tailb97193.ts.net/grag) — работает сразу,
Docker не нужен.
EOF
            exit 0
            ;;
    esac
done

say "=== AI4Math setup ==="

# --- 0) System dependencies ---
MISSING=()
for cmd in python3 curl git tar; do
    command -v "$cmd" >/dev/null 2>&1 || MISSING+=("$cmd")
done
command -v bzip2 >/dev/null 2>&1 || MISSING+=("bzip2")
# Goose binary (Rust) needs libgomp1 at runtime on Linux
if [ "$(uname -s)" = "Linux" ]; then
    if ! ldconfig -p 2>/dev/null | grep -q "libgomp.so.1"; then
        MISSING+=("libgomp1")
    fi
fi
if [ ${#MISSING[@]} -gt 0 ]; then
    warn "Не хватает системных зависимостей: ${MISSING[*]}"
    if command -v apt-get >/dev/null 2>&1; then
        echo "    Debian/Ubuntu: sudo apt-get install -y ${MISSING[*]}"
    elif command -v dnf >/dev/null 2>&1; then
        echo "    Fedora/RHEL: sudo dnf install -y ${MISSING[*]} (libgomp может быть как libgomp)"
    elif command -v brew >/dev/null 2>&1; then
        echo "    macOS: libgomp приходит с gcc — brew install gcc git curl"
    fi
    die "Доставь зависимости и запусти setup.sh заново."
fi

# --- 1) Python 3.10+ ---
PY_OK=$(python3 -c "import sys; print(1 if sys.version_info >= (3,10) else 0)" 2>/dev/null || echo 0)
[ "$PY_OK" = "1" ] || die "Нужен Python 3.10+ (сейчас: $(python3 --version))"
say "Python: $(python3 --version)"

# --- 2) venv + requirements ---
if [ ! -d ".venv" ]; then
    say "Создаю .venv ..."
    python3 -m venv .venv
fi
say "Устанавливаю зависимости из requirements.txt ..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt
say "Зависимости установлены."

# --- 3) Goose CLI ---
if [ ! -x ".tools/goose" ]; then
    say "Устанавливаю Goose CLI в .tools/ ..."
    if ! command -v curl >/dev/null 2>&1; then
        die "curl требуется для установки Goose."
    fi
    GOOSE_BIN_DIR="$REPO/.tools" CONFIGURE=false bash -c "
        curl -fsSL https://github.com/aaif-goose/goose/releases/download/stable/download_cli.sh | bash
    " >/dev/null 2>&1 || warn "Goose installer упал — проверь сеть."
fi
if [ -x ".tools/goose" ]; then
    GOOSE_VERSION=$(.tools/goose --version 2>&1 | tail -1 || echo "?")
    say "Goose: $GOOSE_VERSION"
else
    die "Goose не установлен. Проверь .tools/ и запусти setup.sh заново."
fi

# --- 4) Wizard ---
if [ -f ".env" ]; then
    warn ".env уже существует — пропускаю wizard. Удали .env и перезапусти setup.sh чтобы переконфигурировать."
else
    say "Запускаю cli/wizard.py ..."
    .venv/bin/python cli/wizard.py
fi

# --- 5) Optional local Lean ---
if [ "$WITH_LEAN_LOCAL" = "1" ]; then
    say "Поднимаю локальный lean-checker (Docker) ..."
    bash scripts/install_lean.sh || warn "lean-checker не поднялся. Детали выше."
else
    warn "Локальный Lean checker не устанавливался (используется remote SciLib)."
    warn "Чтобы добавить позже: ./scripts/install_lean.sh"
fi

# --- 6) symlink helper ---
if [ ! -e "$HOME/.local/bin/ai4math" ]; then
    mkdir -p "$HOME/.local/bin"
    ln -sf "$REPO/bin/ai4math" "$HOME/.local/bin/ai4math"
    say "Создан symlink: ~/.local/bin/ai4math → $REPO/bin/ai4math"
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) : ;;
        *) warn "\$HOME/.local/bin отсутствует в PATH. Добавь в ~/.bashrc или ~/.zshrc:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
    esac
fi

cat <<EOF

${GREEN}Готово.${RESET} Запуск:
  ai4math                       интерактивная сессия
  ai4math -m deepseek           выбор модели
  ai4math run "промпт"          одна задача
  ai4math doctor                проверка окружения

Документация: README.md, docs/ARCHITECTURE.md, report/EXPERIMENT_REPORT.md
EOF
