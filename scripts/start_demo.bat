@echo off
REM Builds demo repos (idempotent) and starts the RAMAV backend, which also
REM serves the frontend dashboard from the same origin.
cd /d "%~dp0\.."

echo == RAMAV: setting up demo repositories ==
python scripts\setup_demo_repos.py
if errorlevel 1 goto :error

echo == RAMAV: installing backend dependencies ==
pip install -r backend\requirements.txt

echo == RAMAV: starting backend (serves API + dashboard on http://localhost:8000) ==
cd backend
set RAMAV_PORT=8000
python -m app.main
goto :eof

:error
echo Setup failed. See messages above.
exit /b 1
