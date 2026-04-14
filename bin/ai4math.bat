@echo off
REM AI4Math entrypoint — Windows wrapper. Forwards to bin\ai4math.py.
setlocal
set "REPO=%~dp0.."
set "PY=%REPO%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%REPO%\bin\ai4math.py" %*
endlocal
