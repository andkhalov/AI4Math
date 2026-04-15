@echo off
REM Unified AI4Math MCP stdio server — Windows shim (mirrors bin/ai4math-mcp).
REM Goose spawns this from .goose/sessions; bin/ai4math.py also probes it
REM during pre-flight via probe_mcp().
setlocal
set "REPO=%~dp0.."
set "PY=%REPO%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "%REPO%\src\ai4math_mcp.py" %*
endlocal
