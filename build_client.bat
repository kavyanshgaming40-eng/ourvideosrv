@echo off
echo ===================================================
echo   ourvideo Client - Python to EXE Builder
echo ===================================================
echo.
echo [1/2] Installing/updating requirements...
pip install -r requirements.txt

echo.
echo [2/2] Running PyInstaller builder...
python build_client.py

echo.
echo Processing finished.
pause
