@echo off
chcp 65001 >nul 2>&1
title CreatorDesk AI - Stop
setlocal enabledelayedexpansion

rem Stops only the processes that start.bat recorded in .run\*.pid.
rem Services that were already running (and therefore skipped by start.bat)
rem have no PID file and are left untouched. Unrelated python/node processes
rem are never targeted.
set "ROOT=%~dp0"
set "RUN_DIR=%ROOT%.run"

echo.
echo Stopping CreatorDesk services ...
call :stop_one llm 8002
call :stop_one backend 8080
call :stop_one frontend 5173

echo Waiting for ports to free ...
ping -n 4 127.0.0.1 >nul 2>&1
set /a STILL=0
for %%P in (8002 8080 5173) do (
    netstat -ano | findstr /R /C:":%%P .*LISTENING" >nul 2>&1
    if not errorlevel 1 (
        echo   WARNING: port %%P is still listening - check for an unrelated owner.
        set /a STILL+=1
    )
)
if !STILL! EQU 0 echo All CreatorDesk ports are free.
echo.
exit /b 0

:stop_one
set "S_NAME=%~1"
set "S_PORT=%~2"
set "S_PID_FILE=%RUN_DIR%\%S_NAME%.pid"
if not exist "%S_PID_FILE%" (
    echo   [%S_NAME%] not tracked by this launcher - skipped.
    exit /b 0
)
set "S_PID="
set /p S_PID= < "%S_PID_FILE%"
if not defined S_PID (
    del "%S_PID_FILE%" >nul 2>&1
    echo   [%S_NAME%] no PID recorded - skipped.
    exit /b 0
)
tasklist /FI "PID eq %S_PID%" 2>NUL | findstr /I /C:"%S_PID%" >nul 2>&1
if errorlevel 1 (
    rem Already gone: the stale PID file is safe to remove.
    del "%S_PID_FILE%" >nul 2>&1
    echo   [%S_NAME%] PID %S_PID% is no longer running.
    exit /b 0
)
taskkill /PID %S_PID% /T /F >nul 2>&1
if errorlevel 1 (
    rem Keep the PID file so the operator can retry stopping this process.
    echo   [%S_NAME%] could not stop PID %S_PID% - PID file kept for retry: %S_PID_FILE%
    exit /b 1
)
del "%S_PID_FILE%" >nul 2>&1
echo   [%S_NAME%] stopped PID %S_PID% and its children on port %S_PORT%.
exit /b 0
