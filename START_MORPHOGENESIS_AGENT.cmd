@echo off
title Morphogenesis System Agent
cd /d "%~dp0"

echo Starting Morphogenesis System Agent...
echo Keep this window open while the installation is running.
echo Press Ctrl+C to stop the Agent safely.
echo.

"C:\Users\xiaoh\anaconda3\envs\crystal\python.exe" "08_system_agent\agent.py" --host 0.0.0.0 --open

echo.
echo Morphogenesis System Agent has stopped.
pause
