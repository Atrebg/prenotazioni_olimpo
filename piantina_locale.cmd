@echo off
"%~dp0.venv\Scripts\python.exe" "%~dp0piantina_locale.py" %*
if errorlevel 1 pause
