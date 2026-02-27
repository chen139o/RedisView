@echo off
cd /d "%~dp0"

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Starting Redis Viewer...
venv\Scripts\python redis_viewer.py

echo Press any key to exit...
pause > nul
