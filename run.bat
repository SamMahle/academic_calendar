@echo off
setlocal

echo CadetCal Launcher
echo -----------------

REM Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install Python 3.11+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM Create venv on first run
if not exist ".venv" (
    echo Setting up for first use - this takes about a minute...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
    echo Setup complete.
) else (
    call .venv\Scripts\activate.bat
)

echo Starting CadetCal...
start "" http://localhost:8501
streamlit run app.py --server.headless true --server.port 8501

endlocal
