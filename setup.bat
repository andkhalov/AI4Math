@echo off
REM AI4Math setup — Windows wrapper. Delegates to setup.py.
setlocal
set "REPO=%~dp0"
python "%REPO%setup.py" %*
endlocal
