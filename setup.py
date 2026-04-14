#!/usr/bin/env python3
"""AI4Math cross-platform setup.

Python-эквивалент `setup.sh` — работает на Linux, macOS и Windows.
Делает то же самое:

  1. Pre-flight check системных зависимостей (python3.10+, curl, git,
     tar/bzip2 для Linux, libgomp1 для Linux slim-образов)
  2. Создание .venv и pip install -r requirements.txt
  3. Скачивание Goose CLI в .tools/ (Linux/macOS/Windows)
  4. Запуск cli/wizard.py (если .env не существует)
  5. Опционально: scripts/install_lean.sh для Docker lean-checker
  6. Для Linux/macOS: symlink ~/.local/bin/ai4math → bin/ai4math

Использование:
    python3 setup.py                # установка без Lean
    python3 setup.py --with-lean    # + lean-checker Docker
    python3 setup.py --help
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Colors (ANSI, works on Linux/macOS and Win10+; old cmd without ANSI — just garbage)
if sys.stdout.isatty() and not os.environ.get("AI4MATH_NOCOLOR"):
    GREEN = "\033[0;32m"
    YELLOW = "\033[0;33m"
    RED = "\033[0;31m"
    RESET = "\033[0m"
else:
    GREEN = YELLOW = RED = RESET = ""


def say(msg: str) -> None:
    print(f"{GREEN}[AI4Math]{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[AI4Math]{RESET} {msg}")


def die(msg: str, code: int = 1) -> "NoReturn":  # noqa: F821
    print(f"{RED}[AI4Math]{RESET} {msg}", file=sys.stderr)
    sys.exit(code)


# ---------- pre-flight ----------

def check_python_version() -> None:
    v = sys.version_info
    if (v.major, v.minor) < (3, 10):
        die(f"Нужен Python 3.10+ (сейчас: {platform.python_version()})")
    say(f"Python: {platform.python_version()}")


def check_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def check_system_deps() -> None:
    """Checks OS-specific deps and prints install hints if missing."""
    missing = []
    for cmd in ("git", "curl"):
        if not check_command(cmd):
            missing.append(cmd)
    if IS_LINUX:
        # tar/bzip2 for Goose archive extraction
        for cmd in ("tar", "bzip2"):
            if not check_command(cmd):
                missing.append(cmd)
        # libgomp1 for Goose Rust binary
        try:
            ldconfig = subprocess.run(
                ["ldconfig", "-p"], capture_output=True, text=True, timeout=5
            )
            if "libgomp.so.1" not in ldconfig.stdout:
                missing.append("libgomp1")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # ldconfig not found — can't verify; warn but don't fail
            warn("Не удалось проверить libgomp1 (ldconfig отсутствует). На Debian/Ubuntu: sudo apt-get install libgomp1")
    if missing:
        warn(f"Не хватает системных зависимостей: {' '.join(missing)}")
        if IS_LINUX:
            if check_command("apt-get"):
                print(f"    Debian/Ubuntu: sudo apt-get install -y {' '.join(missing)}")
            elif check_command("dnf"):
                print(f"    Fedora/RHEL: sudo dnf install -y {' '.join(missing)}")
            elif check_command("pacman"):
                print(f"    Arch: sudo pacman -S {' '.join(missing)}")
        elif IS_MACOS:
            print(f"    macOS: brew install {' '.join(missing)}")
        elif IS_WINDOWS:
            print(f"    Windows: установи git и curl (https://git-scm.com / https://curl.se/windows)")
        die("Доставь зависимости и запусти setup заново.")


# ---------- venv + pip ----------

def setup_venv() -> Path:
    venv = REPO / ".venv"
    if not venv.exists():
        say("Создаю .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    # python inside venv
    if IS_WINDOWS:
        py = venv / "Scripts" / "python.exe"
        pip = venv / "Scripts" / "pip.exe"
    else:
        py = venv / "bin" / "python"
        pip = venv / "bin" / "pip"
    if not py.exists():
        die(f".venv сломан — python не найден по пути {py}")
    say("Устанавливаю зависимости из requirements.txt ...")
    subprocess.check_call([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    subprocess.check_call([str(pip), "install", "--quiet", "-r", str(REPO / "requirements.txt")])
    say("Зависимости установлены.")
    return py


# ---------- Goose install ----------

def _goose_asset_name() -> str:
    arch_raw = platform.machine().lower()
    if arch_raw in ("x86_64", "amd64"):
        arch = "x86_64"
    elif arch_raw in ("aarch64", "arm64"):
        arch = "aarch64"
    else:
        die(f"Неподдерживаемая архитектура: {arch_raw}")
    if IS_LINUX:
        return f"goose-{arch}-unknown-linux-gnu.tar.bz2"
    if IS_MACOS:
        return f"goose-{arch}-apple-darwin.tar.bz2"
    if IS_WINDOWS:
        if arch != "x86_64":
            die("Windows: Goose поставляется только для x86_64")
        return "goose-x86_64-pc-windows-msvc.zip"
    die(f"Неподдерживаемая ОС: {sys.platform}")


def install_goose() -> Path:
    tools_dir = REPO / ".tools"
    goose_exe = tools_dir / ("goose.exe" if IS_WINDOWS else "goose")
    if goose_exe.exists():
        try:
            out = subprocess.check_output([str(goose_exe), "--version"], text=True, stderr=subprocess.STDOUT)
            say(f"Goose уже установлен: {out.strip()}")
            return goose_exe
        except Exception:
            warn("Goose бинарь есть, но не запускается. Переустановка ...")
            goose_exe.unlink()

    tools_dir.mkdir(parents=True, exist_ok=True)
    asset = _goose_asset_name()
    url = f"https://github.com/aaif-goose/goose/releases/download/stable/{asset}"
    say(f"Скачиваю Goose: {asset} ...")

    with tempfile.TemporaryDirectory(prefix="ai4math-goose-") as td:
        td_path = Path(td)
        archive = td_path / asset
        try:
            urllib.request.urlretrieve(url, archive)
        except Exception as e:
            die(f"Не удалось скачать Goose: {e}")

        say("Распаковываю ...")
        if asset.endswith(".tar.bz2"):
            import tarfile
            with tarfile.open(archive, "r:bz2") as tf:
                tf.extractall(td_path)
            src = td_path / "goose"
            if not src.exists():
                # Some releases put binary in a subdirectory
                for p in td_path.rglob("goose"):
                    if p.is_file():
                        src = p
                        break
            shutil.move(str(src), str(goose_exe))
            goose_exe.chmod(0o755)
        elif asset.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(td_path)
            # Windows: might be nested in goose-package/
            src = td_path / "goose.exe"
            if not src.exists():
                for p in td_path.rglob("goose.exe"):
                    src = p
                    break
            if not src.exists():
                die(f"Не нашёл goose.exe в распакованном архиве")
            shutil.move(str(src), str(goose_exe))
            # Copy any bundled DLLs next to the exe
            for dll in (src.parent).glob("*.dll"):
                shutil.move(str(dll), str(tools_dir / dll.name))

    # Verify
    try:
        out = subprocess.check_output([str(goose_exe), "--version"], text=True, stderr=subprocess.STDOUT)
        say(f"Goose: {out.strip()}")
    except Exception as e:
        die(f"Goose установлен, но не запускается: {e}")
    return goose_exe


# ---------- wizard + lean + symlink ----------

def run_wizard(venv_py: Path) -> None:
    env_file = REPO / ".env"
    if env_file.exists():
        warn(".env уже существует — пропускаю wizard. Удали .env и перезапусти setup чтобы переконфигурировать.")
        return
    say("Запускаю cli/wizard.py ...")
    subprocess.check_call([str(venv_py), str(REPO / "cli" / "wizard.py")])


def install_lean() -> None:
    script = REPO / "scripts" / "install_lean.sh"
    if IS_WINDOWS:
        warn("Lean installer на Windows: запусти вручную через WSL2 или Docker Desktop + bash scripts/install_lean.sh")
        return
    say("Поднимаю lean-checker (Docker) ...")
    try:
        subprocess.check_call(["bash", str(script)])
    except subprocess.CalledProcessError:
        warn("lean-checker не поднялся. Детали выше.")


def create_symlink() -> None:
    if IS_WINDOWS:
        # Windows: пользователи запускают `python bin\ai4math.py` или `bin\ai4math.bat`
        # Symlinks требуют привилегий, не делаем.
        warn("Windows: для глобальной команды добавь %REPO%\\bin в PATH или используй bin\\ai4math.bat")
        return
    target = Path.home() / ".local" / "bin" / "ai4math"
    src = REPO / "bin" / "ai4math"
    if target.exists() or target.is_symlink():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(src)
        say(f"Создан symlink: {target} → {src}")
        if str(target.parent) not in os.environ.get("PATH", "").split(os.pathsep):
            warn(f"{target.parent} отсутствует в PATH. Добавь в ~/.bashrc или ~/.zshrc:")
            print(f'    export PATH="{target.parent}:$PATH"')
    except OSError as e:
        warn(f"Не удалось создать symlink: {e}")


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="AI4Math cross-platform setup", add_help=True)
    ap.add_argument("--with-lean", action="store_true", help="Также поднять lean-checker Docker контейнер")
    args = ap.parse_args()

    say(f"=== AI4Math setup ({sys.platform}) ===")
    check_system_deps()
    check_python_version()
    venv_py = setup_venv()
    install_goose()
    run_wizard(venv_py)
    if args.with_lean:
        install_lean()
    else:
        warn("Lean не устанавливался. Чтобы добавить позже: ./scripts/install_lean.sh (Linux/macOS/WSL)")
    create_symlink()

    print()
    say("Готово. Запуск:")
    if IS_WINDOWS:
        print("    bin\\ai4math.bat                 интерактивная сессия")
        print('    bin\\ai4math.bat run "промпт"    одна задача')
        print("    bin\\ai4math.bat doctor          проверка окружения")
    else:
        print("    ai4math                         интерактивная сессия")
        print("    ai4math -m deepseek             выбор модели")
        print('    ai4math run "промпт"            одна задача')
        print("    ai4math doctor                  проверка окружения")
    print()
    print("Документация: README.md, docs/ARCHITECTURE.md, report/EXPERIMENT_REPORT.md")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
    except subprocess.CalledProcessError as e:
        die(f"Команда упала: {e}")
