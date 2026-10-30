@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3 -c "import sys; sys.exit(sys.version_info < (3,11))" || (echo Python 3.11 or newer is required. & pause & exit /b 1)
  py -3 -m venv .venv || (pause & exit /b 1)
)
.venv\Scripts\python.exe -c "import yaml, dotenv, filelock, pycapcut" 2>nul || (
  .venv\Scripts\python.exe -m pip install -r requirements-capcut.txt || (pause & exit /b 1)
)
if "%~1"=="" (
  .venv\Scripts\python.exe main.py --help
  pause
) else (
  .venv\Scripts\python.exe main.py %*
)
endlocal
