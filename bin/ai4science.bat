@echo off
REM AI4Science entrypoint — Windows wrapper. Forwards to bin\ai4science.py.
setlocal
set "REPO=%~dp0.."
set "PY=%REPO%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%REPO%\bin\ai4science.py" %*
endlocal
