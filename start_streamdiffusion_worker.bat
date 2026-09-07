@echo off
cd /d "%~dp0"
title Morphogenesis StreamDiffusion Worker
set "HF_HOME=%~dp003_diffusion_imagination\models\huggingface"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
"%~dp003_diffusion_imagination\.conda\python.exe" "%~dp003_diffusion_imagination\runtime\worker.py" --host 127.0.0.1 --port 8091
pause
