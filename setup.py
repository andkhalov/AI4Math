#!/usr/bin/env python3
"""AI4Science setup — установка на Windows, macOS и Linux.

  1. Проверка Python 3.10+ и системных зависимостей (git, curl; на Linux tar/bzip2/libgomp1)
  2. Создание .venv и pip install -r requirements.txt
  3. Скачивание Goose CLI закреплённой версии в .tools/
  4. Запуск cli/wizard.py (если .env не существует)
  5. Необязательно: локальный Lean checker в Docker (--with-lean-local, Linux/macOS)
  6. Команда ai4science: symlink ~/.local/bin/ai4science (Linux/macOS)
     или папка bin в пользовательском PATH (Windows)
  7. Проверка: bin/ai4science doctor

Использование:
    python setup.py
    python setup.py --skip-goose        без скачивания Goose
    python setup.py --skip-doctor       без проверки в конце
    python setup.py --no-path           Windows: не менять пользовательский PATH
    python setup.py --with-lean-local   + локальный Lean checker (Docker)
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

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

REPO = Path(__file__).resolve().parent
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
# Версия Goose закреплена: проверена с этим репозиторием (Windows/macOS/Linux).
GOOSE_VERSION = "v1.50.0"
GOOSE_RELEASE = os.environ.get(
    "AI4SCIENCE_GOOSE_RELEASE",
    f"https://github.com/aaif-goose/goose/releases/download/{GOOSE_VERSION}",
)

if sys.stdout.isatty() and not os.environ.get("AI4SCIENCE_NOCOLOR"):
    GREEN, YELLOW, RED, RESET = "\033[0;32m", "\033[0;33m", "\033[0;31m", "\033[0m"
else:
    GREEN = YELLOW = RED = RESET = ""


def say(msg: str) -> None:
    print(f"{GREEN}[AI4Science]{RESET} {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"{YELLOW}[AI4Science]{RESET} {msg}", flush=True)


def die(msg: str, code: int = 1) -> "NoReturn":  # noqa: F821
    print(f"{RED}[AI4Science]{RESET} {msg}", file=sys.stderr, flush=True)
    sys.exit(code)


# ---------- pre-flight ----------

def check_python_version() -> None:
    if sys.version_info < (3, 10):
        die(f"Нужен Python 3.10+ (сейчас: {platform.python_version()})")
    say(f"Python: {platform.python_version()} ({sys.executable})")


def check_system_deps() -> None:
    missing = [c for c in ("git", "curl") if shutil.which(c) is None]
    if IS_LINUX:
        missing += [c for c in ("tar", "bzip2") if shutil.which(c) is None]
        found = any(Path(d, "libgomp.so.1").exists() for d in (
            "/usr/lib/x86_64-linux-gnu", "/usr/lib/aarch64-linux-gnu", "/usr/lib64", "/usr/lib",
            "/lib/x86_64-linux-gnu", "/lib/aarch64-linux-gnu", "/lib64", "/lib"))
        if not found:
            missing.append("libgomp1")
    if missing:
        warn(f"Не хватает: {' '.join(missing)}")
        if IS_WINDOWS:
            print("    Windows: git — https://git-scm.com/download/win или winget install -e --id Git.Git;")
            print("             curl входит в Windows 10+")
        elif IS_MACOS:
            print(f"    macOS: brew install {' '.join(missing)}")
        else:
            print(f"    Debian/Ubuntu: sudo apt-get install -y {' '.join(missing)}")
        die("Установи зависимости и запусти setup заново.")


# ---------- venv ----------

def venv_python() -> Path:
    return REPO / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")


def setup_venv() -> Path:
    venv = REPO / ".venv"
    if not venv.exists():
        say("Создаю .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    py = venv_python()
    if not py.exists():
        die(f".venv сломан — нет {py}. Удали папку .venv и запусти setup заново.")
    say("Устанавливаю зависимости из requirements.txt ...")
    subprocess.check_call([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    subprocess.check_call([str(py), "-m", "pip", "install", "--quiet", "-r", str(REPO / "requirements.txt")])
    say("Зависимости установлены.")
    return py


# ---------- goose ----------

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
            die("Windows: Goose доступен только для x86_64. Запасной путь — WSL2 (см. README).")
        return "goose-x86_64-pc-windows-msvc.zip"
    die(f"Неподдерживаемая ОС: {sys.platform}")


def _goose_version(goose_exe: Path) -> str:
    out = subprocess.check_output([str(goose_exe), "--version"], text=True, stderr=subprocess.STDOUT, timeout=20)
    return out.strip().splitlines()[-1].strip()


def install_goose() -> Path:
    tools_dir = REPO / ".tools"
    goose_exe = tools_dir / ("goose.exe" if IS_WINDOWS else "goose")
    wanted = GOOSE_VERSION.lstrip("v")
    if goose_exe.exists():
        try:
            current = _goose_version(goose_exe)
            if current == wanted or os.environ.get("AI4SCIENCE_GOOSE_RELEASE"):
                say(f"Goose уже установлен: {current}")
                return goose_exe
            warn(f"Goose {current} отличается от закреплённой версии {wanted}. Обновляю ...")
        except Exception:
            warn("Goose есть, но не запускается. Переустановка ...")
        goose_exe.unlink()
    tools_dir.mkdir(parents=True, exist_ok=True)
    asset = _goose_asset_name()
    url = f"{GOOSE_RELEASE}/{asset}"
    say(f"Скачиваю Goose: {url}")
    with tempfile.TemporaryDirectory(prefix="ai4science-goose-") as td:
        td_path = Path(td)
        archive = td_path / asset
        try:
            urllib.request.urlretrieve(url, archive)
        except Exception as e:
            die(f"Не удалось скачать Goose: {e}")
        say(f"  скачано: {archive.stat().st_size:,} байт")
        if asset.endswith(".tar.bz2"):
            import tarfile
            with tarfile.open(archive, "r:bz2") as tf:
                tf.extractall(td_path)
            src = next((p for p in td_path.rglob("goose") if p.is_file()), None)
            if src is None:
                die("goose не найден в архиве")
            shutil.move(str(src), str(goose_exe))
            goose_exe.chmod(0o755)
        else:
            import zipfile
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(td_path)
            src = next((p for p in td_path.rglob("*") if p.is_file() and p.name.lower() == "goose.exe"), None)
            if src is None:
                die("goose.exe не найден в архиве")
            shutil.move(str(src), str(goose_exe))
            for dll in src.parent.glob("*.dll"):
                dest = tools_dir / dll.name
                if not dest.exists():
                    shutil.move(str(dll), str(dest))
    try:
        say(f"Goose: {_goose_version(goose_exe)}")
    except Exception as e:
        die(f"Goose установлен, но не запускается: {type(e).__name__}: {e}")
    return goose_exe


# ---------- wizard, lean, command, doctor ----------

def run_wizard(py: Path) -> None:
    env_file = REPO / ".env"
    if env_file.exists():
        warn(".env уже существует — wizard пропущен. Удали .env и перезапусти setup для перенастройки.")
        return
    say("Запускаю cli/wizard.py ...")
    subprocess.check_call([str(py), str(REPO / "cli" / "wizard.py")])


def install_lean_local() -> None:
    if IS_WINDOWS:
        warn("Локальный Lean checker на Windows: через WSL2 или Docker Desktop — bash scripts/install_lean.sh")
        return
    say("Поднимаю локальный Lean checker (Docker) ...")
    rc = subprocess.call(["bash", str(REPO / "scripts" / "install_lean.sh")])
    if rc != 0:
        warn("Локальный Lean checker не поднялся. Агент продолжит работу с удалённым сервисом.")


def create_symlink() -> None:
    target = Path.home() / ".local" / "bin" / "ai4science"
    source = REPO / "bin" / "ai4science"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        if target.resolve() == source.resolve():
            say(f"Команда ai4science: {target} (уже настроена)")
            return
        warn(f"{target} указывал на {target.resolve()} — переключаю на эту установку.")
        target.unlink()
    elif target.exists():
        warn(f"{target} существует и не является symlink — команда не создана. Запуск: {source}")
        return
    try:
        target.symlink_to(source)
        say(f"Команда ai4science: {target} → {source}")
    except OSError as e:
        warn(f"Symlink не создан: {e}. Запуск: {source}")
        return
    if str(target.parent) not in os.environ.get("PATH", "").split(os.pathsep):
        warn(f"{target.parent} нет в PATH. Добавь в ~/.zshrc или ~/.bashrc: export PATH=\"{target.parent}:$PATH\"")


def add_bin_to_user_path() -> None:
    """Windows: добавить <repo>\\bin в пользовательский PATH (без прав администратора)."""
    bin_dir = str(REPO / "bin")
    script = (
        "$d = $env:AI4SCIENCE_BIN; "
        "$p = [Environment]::GetEnvironmentVariable('Path', 'User'); "
        "if (-not $p) { $p = '' }; "
        "$parts = $p -split ';' | Where-Object { $_ -ne '' }; "
        "if ($parts | Where-Object { $_.TrimEnd('\\') -ieq $d.TrimEnd('\\') }) { 'present' } "
        "else { [Environment]::SetEnvironmentVariable('Path', (($parts + $d) -join ';'), 'User'); 'added' }"
    )
    env = os.environ.copy()
    env["AI4SCIENCE_BIN"] = bin_dir
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            text=True, stderr=subprocess.STDOUT, env=env, timeout=60,
        ).strip()
    except Exception as e:
        warn(f"PATH не изменён ({type(e).__name__}). Запуск: {bin_dir}\\ai4science.bat")
        return
    if out.endswith("added"):
        say(f"Папка {bin_dir} добавлена в пользовательский PATH. Открой новый терминал и запускай: ai4science")
    else:
        say(f"Папка {bin_dir} уже есть в пользовательском PATH. Команда: ai4science")


def run_doctor(py: Path) -> None:
    say("Проверка: bin/ai4science doctor ...")
    rc = subprocess.call([str(py), str(REPO / "bin" / "ai4science.py"), "doctor"])
    if rc != 0:
        die("doctor завершился с ошибкой — установка не завершена.", rc)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI4Science setup")
    ap.add_argument("--skip-goose", action="store_true", help="не скачивать Goose")
    ap.add_argument("--skip-doctor", action="store_true", help="не запускать doctor в конце")
    ap.add_argument("--no-path", action="store_true", help="Windows: не менять пользовательский PATH")
    ap.add_argument("--with-lean-local", "--with-lean", dest="with_lean_local", action="store_true",
                    help="поднять локальный Lean checker в Docker (Linux/macOS)")
    args = ap.parse_args()

    say(f"=== AI4Science setup ({sys.platform}, Python {platform.python_version()}, {platform.machine()}) ===")
    say(f"repo: {REPO}")
    say("[1/7] системные зависимости")
    check_system_deps()
    say("[2/7] версия Python")
    check_python_version()
    say("[3/7] venv и зависимости")
    py = setup_venv()
    say(f"[4/7] Goose CLI ({GOOSE_VERSION})")
    if args.skip_goose:
        warn("пропущено (--skip-goose)")
    else:
        install_goose()
    say("[5/7] .env (wizard)")
    run_wizard(py)
    say("[6/7] Lean checker")
    if args.with_lean_local:
        install_lean_local()
    else:
        say("используется удалённый сервис (LEAN_CHECKER_URL в .env)")
    say("[7/7] команда ai4science и проверка")
    if IS_WINDOWS:
        if args.no_path:
            warn(f"PATH не менялся (--no-path). Запуск: {REPO}\\bin\\ai4science.bat")
        else:
            add_bin_to_user_path()
    else:
        create_symlink()
    if not args.skip_doctor:
        run_doctor(py)

    print()
    say("Готово. Запуск:")
    if IS_WINDOWS:
        print("    ai4science                      интерактивная сессия (в новом терминале)")
        print('    ai4science run "промпт"         одна задача')
        print("    ai4science doctor               проверка окружения")
        print(f"    без PATH: {REPO}\\bin\\ai4science.bat")
    else:
        print("    ai4science                      интерактивная сессия")
        print('    ai4science run "промпт"         одна задача')
        print("    ai4science doctor               проверка окружения")
    print("\nДокументация: README.md, docs/ARCHITECTURE.md")
    return 0


if __name__ == "__main__":
    import traceback
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        sys.exit(130)
    except subprocess.CalledProcessError as e:
        print(f"{RED}[AI4Science]{RESET} команда завершилась с ошибкой: {e.cmd} (rc={e.returncode})", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"{RED}[AI4Science]{RESET} ошибка: {type(e).__name__}: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(2)
