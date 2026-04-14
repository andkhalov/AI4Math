#!/usr/bin/env bash
# AI4Math clean-room test. Запускает репо в свежем Docker-контейнере
# `python:3.12-slim` — симулирует установку с нуля у студента.
#
# Требует: docker, локально склонированный репо, заполненный .env в корне
# этого репо (для API-ключа Yandex — тест не мокает сеть).
#
# Запускается ИЗ корня репо:
#   ./scripts/clean_room_test.sh
#
# Что проверяет:
#   [1] Чистый контейнер без git/curl/bzip2/libgomp1 — setup.sh сам сообщает
#       чего не хватает (pre-flight check).
#   [2] После apt install системных зависимостей: git clone из локального
#       git-объекта → setup.sh отрабатывает за ~30 секунд → ai4math doctor
#       показывает зелёный статус → ai4math run с Task A (fibonacci) → файл
#       создан, вывод корректный.
#
# Выход 0 если всё прошло, ненулевой с деталями если что-то сломано.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -f "$REPO/.env" ]; then
    echo "Нужен $REPO/.env с YANDEX_AI_API / YANDEX_CLOUD_FOLDER для теста."
    echo "Запусти ./cli/wizard.py или скопируй .env.example и заполни."
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Нужен docker для этого теста."
    exit 1
fi

set -a; source "$REPO/.env"; set +a

TEST_SCRIPT="$(mktemp)"
trap 'rm -f "$TEST_SCRIPT"' EXIT

cat > "$TEST_SCRIPT" <<'INNER'
#!/bin/bash
set -e

echo "=== [1] Install system deps (git + curl + bzip2 + tar + libgomp1) ==="
apt-get update -qq
apt-get install -qq -y git curl bzip2 tar libgomp1 >/dev/null 2>&1
git --version
curl --version | head -1

echo
echo "=== [2] Clone AI4Math from mounted local repo ==="
git config --global --add safe.directory /git_source
git config --global --add safe.directory /git_source/.git
git clone /git_source /app
cd /app
git log --oneline -1

echo
echo "=== [3] Pre-populate .env (skips interactive wizard) ==="
cat > /app/.env <<ENV
YANDEX_AI_API=$YANDEX_AI_API
YANDEX_CLOUD_FOLDER=$YANDEX_CLOUD_FOLDER
YANDEX_QWEN=qwen3-235b-a22b-fp8/latest
YANDEX_DEEPSEEK=deepseek-v32/latest
YANDEX_GPTOOS=gpt-oss-120b/latest
AI4MATH_MODEL=qwen
LEAN_CHECKER_URL=http://localhost:8888
ENV

echo
echo "=== [4] Run setup.sh ==="
./setup.sh 2>&1 | tail -20

echo
echo "=== [5] ai4math doctor ==="
./bin/ai4math doctor

echo
echo "=== [6] ai4math run — Task A (fibonacci) ==="
mkdir -p /tmp/taskA && cd /tmp/taskA
AI4MATH_QUIET=1 /app/bin/ai4math run \
    "Create a file hello.py that prints the first 10 Fibonacci numbers (0 1 1 2 3 5 8 13 21 34), one per line. After creating it, run it to verify it works." 2>&1 | tail -25

echo "---verify artifact---"
if [ ! -f hello.py ]; then
    echo "FAIL: hello.py not created"
    exit 1
fi

EXPECTED="0
1
1
2
3
5
8
13
21
34"
ACTUAL=$(python3 hello.py)
if [ "$ACTUAL" != "$EXPECTED" ]; then
    echo "FAIL: fibonacci output mismatch"
    echo "expected: $EXPECTED"
    echo "actual:   $ACTUAL"
    exit 1
fi
echo "hello.py output correct"

echo
echo "=== Clean room test: PASS ==="
INNER
chmod +x "$TEST_SCRIPT"

echo "Запускаю clean-room test в docker (python:3.12-slim) ..."
docker run --rm \
    --network host \
    -v "$REPO:/git_source:ro" \
    -v "$TEST_SCRIPT:/test.sh:ro" \
    -e YANDEX_AI_API="$YANDEX_AI_API" \
    -e YANDEX_CLOUD_FOLDER="$YANDEX_CLOUD_FOLDER" \
    python:3.12-slim bash /test.sh
