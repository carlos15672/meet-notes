@echo off
cd /d "%~dp0"
if not exist ".venv-backend\Scripts\python.exe" (
  echo Falta el entorno .venv-backend. Consulta README.md.
  pause
  exit /b 1
)
".venv-backend\Scripts\python.exe" -u scripts\setup_ai.py
if errorlevel 1 (
  echo La instalacion no termino. Conserva el error mostrado.
  pause
  exit /b 1
)
echo Instalacion completada. Ya puedes iniciar Reunion Notas.
pause
