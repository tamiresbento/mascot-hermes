@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 (
    echo Instale Python 3.11 ou superior e abra novamente.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -c "import mascot_studio, PySide6, PIL" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -e .
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
start "Mascot Studio" ".venv\Scripts\pythonw.exe" -m mascot_studio gui
endlocal
