#!/usr/bin/env bash
# AI4Science setup — Linux / macOS / WSL. Проверяет системные зависимости и передаёт работу setup.py.
#   ./setup.sh                    установка
#   ./setup.sh --with-lean-local  + локальный Lean checker в Docker
#   ./setup.sh --help             все параметры
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

MISSING=()
for cmd in python3 curl git tar; do
    command -v "$cmd" >/dev/null 2>&1 || MISSING+=("$cmd")
done
if [ "$(uname -s)" = "Linux" ]; then
    command -v bzip2 >/dev/null 2>&1 || MISSING+=("bzip2")
    have_libgomp() {
        local d
        for d in /usr/lib/x86_64-linux-gnu /usr/lib/aarch64-linux-gnu /usr/lib64 /usr/lib \
                 /lib/x86_64-linux-gnu /lib/aarch64-linux-gnu /lib64 /lib; do
            [ -e "$d/libgomp.so.1" ] && return 0
        done
        return 1
    }
    have_libgomp || MISSING+=("libgomp1")
    python3 -c "import venv, ensurepip" >/dev/null 2>&1 || MISSING+=("python3-venv")
fi

if [ ${#MISSING[@]} -gt 0 ] && [ "$(uname -s)" = "Linux" ] && command -v apt-get >/dev/null 2>&1; then
    echo "[AI4Science] Ставлю системные зависимости: ${MISSING[*]}"
    if [ "$(id -u)" = "0" ]; then
        apt-get update -qq >/dev/null 2>&1 || true
        apt-get install -y --no-install-recommends "${MISSING[@]}" >/dev/null 2>&1 && MISSING=()
    elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        sudo apt-get update -qq >/dev/null 2>&1 || true
        sudo apt-get install -y --no-install-recommends "${MISSING[@]}" >/dev/null 2>&1 && MISSING=()
    fi
fi
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "[AI4Science] Не хватает: ${MISSING[*]}" >&2
    if command -v apt-get >/dev/null 2>&1; then
        echo "    Debian/Ubuntu: sudo apt-get install -y ${MISSING[*]}" >&2
    elif command -v dnf >/dev/null 2>&1; then
        echo "    Fedora/RHEL: sudo dnf install -y ${MISSING[*]//libgomp1/libgomp}" >&2
    elif [ "$(uname -s)" = "Darwin" ]; then
        echo "    macOS: brew install ${MISSING[*]}" >&2
    fi
    echo "[AI4Science] Установи зависимости и запусти ./setup.sh заново." >&2
    exit 1
fi

exec python3 "$REPO/setup.py" "$@"
