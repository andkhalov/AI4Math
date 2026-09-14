@echo off
chcp 65001 >nul
REM AI4Science setup - Windows 10/11 (native). Checks Python 3.10+ and git, then runs setup.py.
REM If native installation fails, prints the fallback path (WSL2).
REM   setup.bat                 install
REM   setup.bat --no-path       do not modify user PATH
REM   setup.bat --help          all options
setlocal EnableExtensions
set "REPO=%~dp0"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYCMD="

REM 1) python from PATH (skip the Microsoft Store stub, which fails on -c)
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYCMD=python"
)
REM 2) py launcher
if not defined PYCMD (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYCMD=py -3"
    )
)
if not defined PYCMD goto :nopython

where git >nul 2>&1
if errorlevel 1 goto :nogit

echo [AI4Science] Python: %PYCMD%
%PYCMD% "%REPO%setup.py" %*
if errorlevel 1 goto :fallback
endlocal
exit /b 0

:nopython
echo [AI4Science] Не найден Python 3.10 или новее.
echo     Установите Python: https://www.python.org/downloads/windows/
echo     при установке отметьте "Add python.exe to PATH"
echo     или выполните: winget install -e --id Python.Python.3.12
echo     затем откройте новый терминал и запустите setup.bat заново.
goto :fallback

:nogit
echo [AI4Science] Не найден git.
echo     Установите git: https://git-scm.com/download/win
echo     или выполните: winget install -e --id Git.Git
echo     затем откройте новый терминал и запустите setup.bat заново.
goto :fallback

:fallback
echo.
echo [AI4Science] Установка в Windows не завершена.
echo     Запасной путь: WSL2 с Ubuntu.
echo       1. PowerShell от администратора: wsl --install -d Ubuntu
echo       2. В терминале Ubuntu:
echo          git clone https://github.com/andkhalov/AI4Science.git
echo          cd AI4Science
echo          ./setup.sh
endlocal
exit /b 1
