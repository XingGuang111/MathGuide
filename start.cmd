@echo off
setlocal
chcp 65001 >nul
title MathGuide
pushd "%~dp0"
if errorlevel 1 goto failed

if exist ".venv\Scripts\python.exe" goto check_python
echo [1/3] Creating Python environment...
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
    if errorlevel 1 goto no_python
    python -m venv .venv
)
if errorlevel 1 goto failed

:check_python
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 10))"
if errorlevel 1 goto no_python
if not exist ".venv\mathguide-requirements.txt" goto install
fc /b requirements.txt ".venv\mathguide-requirements.txt" >nul 2>&1
if errorlevel 1 goto install
".venv\Scripts\python.exe" -m pip check >nul 2>&1
if not errorlevel 1 goto launch

:install
echo [2/3] Installing dependencies. The first run may take several minutes...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
copy /y requirements.txt ".venv\mathguide-requirements.txt" >nul
if errorlevel 1 goto failed

:launch
echo [3/3] Starting MathGuide: http://127.0.0.1:8000
echo Keep this window open. Press Ctrl+C to stop.
".venv\Scripts\python.exe" tools\start_web.py
if errorlevel 1 goto failed
popd
exit /b 0

:no_python
echo Please install Python 3.10 or newer and enable Add Python to PATH.
echo If .venv is from another computer, rename it and run this script again.
goto failed

:failed
echo.
echo MathGuide could not start. See the error above.
echo For download issues, see the dependency mirror instructions in README.md.
pause
popd
exit /b 1
