@echo off
cd /d "%~dp0"
set "AFC_PYTHON=.venv\Scripts\pythonw.exe"
if not exist "%AFC_PYTHON%" set "AFC_PYTHON=..\.venv\Scripts\pythonw.exe"
if not exist "%AFC_PYTHON%" (
  echo Primero ejecuta python research/bootstrap_training.py
  pause
  exit /b 1
)
start "" "%AFC_PYTHON%" -m afc_lab.corpus_gui
