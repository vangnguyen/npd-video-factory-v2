@echo off
cd /d "%~dp0.."
echo Video Factory: http://127.0.0.1:8026
echo Open that address in your browser. Keep this window open; Ctrl+C stops Studio.
"C:\NPD-Video-Factory\runtime\venv\Scripts\python.exe" -m services.windows_native.server --port 8026
if errorlevel 1 pause
