@echo off
rem Starts the Hello FPGA Kit test GUI with the repository .venv (created if missing).
setlocal
set ROOT=%~dp0..\..
if not exist "%ROOT%\.venv\Scripts\python.exe" (
    py -3 -m venv "%ROOT%\.venv" || python -m venv "%ROOT%\.venv"
    "%ROOT%\.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
)
cd /d "%~dp0"
"%ROOT%\.venv\Scripts\python.exe" hk_gui.py %*
