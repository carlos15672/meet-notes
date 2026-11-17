@echo off
cd /d "%~dp0"
if not exist ".venv-backend\Scripts\python.exe" (
  echo Falta el entorno de Python. Consulta README.md.
  pause
  exit /b 1
)
".venv-backend\Scripts\python.exe" -u scripts\restart.py
if errorlevel 1 pause
