@echo off
echo Starting OpenHands Docker Environment...

:: 1. Check if Docker Desktop is running
tasklist /FI "IMAGENAME eq Docker Desktop.exe" 2>NUL | find /I /N "Docker Desktop.exe">NUL
if "%ERRORLEVEL%"=="1" (
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    echo Waiting for Docker to wake up...
    timeout /t 35 /nobreak >nul
)

:: 2. Start the Linux Backend silently via WSL
echo Starting Ubuntu backend...
:: UPDATED PATH to the new location
wsl -d Ubuntu -e bash -c "cd '/mnt/c/Projects Openhands/Active/Creator Desk' && docker compose up -d"

:: 3. Wait 5 seconds for the web server to initialize
timeout /t 5 /nobreak >nul

:: 4. Open the Web Browser (Chrome/Edge)
start http://localhost:8001/canvas
exit