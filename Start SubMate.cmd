@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo SubMate's Python environment is missing. Follow the README setup instructions.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m scripts.local_bot start
pause
