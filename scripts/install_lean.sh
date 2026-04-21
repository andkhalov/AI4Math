#!/usr/bin/env bash
# Установка локального lean-checker — опциональная альтернатива remote
# SciLib endpoint'у, используемому по умолчанию в AI4Math.
#
# Клонирует andkhalov/lean-checker (Lean 4.24 + Mathlib 4.24) в vendor/,
# запускает docker compose up -d. Первая сборка Mathlib занимает
# 1.5-2.5 часа, требует ~8 ГБ RAM, ~10 ГБ свободного места.
#
# После успешной установки измени LEAN_CHECKER_URL в .env с
# https://scilibai.ru/grag  →  http://localhost:8888
# AI4Math MCP автоматически определит старую схему lean-checker и
# будет работать с ним (отдельный tool path).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$REPO/vendor/lean-checker"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
RESET='\033[0m'

say()  { echo -e "${GREEN}[lean]${RESET} $*"; }
warn() { echo -e "${YELLOW}[lean]${RESET} $*"; }
die()  { echo -e "${RED}[lean]${RESET} $*" >&2; exit 1; }

if ! command -v docker >/dev/null 2>&1; then
    die "Docker не найден. Установи Docker + Docker Compose v2."
fi
if ! docker compose version >/dev/null 2>&1; then
    die "Docker Compose v2 не найден (docker compose version)."
fi

mkdir -p "$REPO/vendor"
if [ ! -d "$VENDOR" ]; then
    say "Клонирую andkhalov/lean-checker в $VENDOR ..."
    git clone https://github.com/andkhalov/lean-checker.git "$VENDOR"
fi

cd "$VENDOR"
say "docker compose up --build -d (первая сборка 1.5-2.5 часа)..."
docker compose up --build -d

say "Жду первого прогрева /health (прогрев lake env может занять ~90 секунд)..."
for i in $(seq 1 60); do
    if curl -fsS --max-time 5 "http://localhost:8888/health" 2>/dev/null | grep -q '"lean_ok":true'; then
        say "/health OK — lean-checker готов."
        say "Чтобы переключить AI4Math на локальный checker, поставь в .env:"
        say "    LEAN_CHECKER_URL=http://localhost:8888"
        exit 0
    fi
    sleep 5
done
warn "/health не ответил за 5 минут. Проверь: docker logs lean-checker-lean-server-1"
exit 1
