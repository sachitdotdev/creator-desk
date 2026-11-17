@echo off
chcp 65001 >nul 2>&1
title CreatorDesk AI - Startup
setlocal enabledelayedexpansion

rem ===========================================================================
rem TUNABLES - everything configurable lives in this block.
rem Paths are derived from this script's own location (%~dp0); no personal
rem absolute paths are hardcoded here.
rem ---------------------------------------------------------------------------
rem LLM: the pipeline uses vLLM (OpenAI-compatible) on 127.0.0.1:8002, model
rem "meissa-7b-awq". The self-contained vLLM build and the exact start command
rem (model path, --max-model-len 4096, --gpu-memory-utilization 0.60,
rem --max-num-seqs 4, --enforce-eager) are owned by the services script below.
rem We call that script with the right working directory instead of duplicating
rem its logic. Override LLM_SCRIPT here if the services layout changes.
set "LLM_SCRIPT=%~dp0services\vllm\start_vllm.bat"
set "LLM_PORT=8002"
set "LLM_HEALTH=http://127.0.0.1:%LLM_PORT%/health"
set "LLM_TIMEOUT=300"

set "BACKEND_PORT=8080"
set "BACKEND_HEALTH=http://127.0.0.1:%BACKEND_PORT%/api/status"
set "BACKEND_TIMEOUT=120"

set "FRONTEND_PORT=5173"
set "FRONTEND_HEALTH=http://127.0.0.1:%FRONTEND_PORT%/"
set "FRONTEND_TIMEOUT=120"
rem ===========================================================================

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "LOG_DIR=%ROOT%logs"
set "RUN_DIR=%ROOT%.run"
set "LLM_LOG=%LOG_DIR%\llm.log"
set "BACKEND_LOG=%LOG_DIR%\backend.log"
set "FRONTEND_LOG=%LOG_DIR%\frontend.log"
set "LLM_WRAPPER=%RUN_DIR%\start_llm.cmd"
set "BACKEND_WRAPPER=%RUN_DIR%\start_backend.cmd"
set "FRONTEND_WRAPPER=%RUN_DIR%\start_frontend.cmd"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"
rem NOTE: PID files are cleared only for services we actually (re)start, so a
rem second run that skips an already-healthy service keeps its tracking intact.

rem --- Bootstrap the backend venv only when it is missing (fresh clone). -----
if not exist "%BACKEND%\venv\Scripts\python.exe" (
    echo [bootstrap] Creating backend venv ...
    py -3.12 -m venv "%BACKEND%\venv" 2>NUL
    if errorlevel 1 py -3.11 -m venv "%BACKEND%\venv"
    if errorlevel 1 (
        echo ERROR: could not create backend venv; install Python 3.12/3.11.
        exit /b 1
    )
    "%BACKEND%\venv\Scripts\python.exe" -m pip install -r "%BACKEND%\requirements.txt"
    if errorlevel 1 (
        echo ERROR: could not install backend requirements.
        exit /b 1
    )
)

rem --- Build tiny per-service wrappers: redirect output to logs\ and feed NUL
rem --- to stdin so a trailing "pause" in any child script cannot block us.
> "%LLM_WRAPPER%" echo @echo off
>> "%LLM_WRAPPER%" echo call "%LLM_SCRIPT%" ^> "%LLM_LOG%" 2^>^&1 ^< NUL
> "%BACKEND_WRAPPER%" echo @echo off
>> "%BACKEND_WRAPPER%" echo cd /d "%BACKEND%"
>> "%BACKEND_WRAPPER%" echo call venv\Scripts\activate.bat
>> "%BACKEND_WRAPPER%" echo python -m uvicorn app.main:app --reload --port %BACKEND_PORT% ^> "%BACKEND_LOG%" 2^>^&1 ^< NUL
> "%FRONTEND_WRAPPER%" echo @echo off
>> "%FRONTEND_WRAPPER%" echo cd /d "%FRONTEND%"
>> "%FRONTEND_WRAPPER%" echo if not exist node_modules npm install
>> "%FRONTEND_WRAPPER%" echo npm run dev ^> "%FRONTEND_LOG%" 2^>^&1 ^< NUL

echo.
echo ==========================================
echo   CreatorDesk AI - Startup
echo ==========================================
for /f %%T in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do set "START_TS=%%T"

rem --- 1. LLM server ---------------------------------------------------------
call :health "%LLM_HEALTH%"
if "!SVC_UP!"=="1" goto llm_skip
echo [1/3] Starting vLLM on port %LLM_PORT% ...
del "%RUN_DIR%\llm.pid" >nul 2>&1
call :launch llm "%LLM_WRAPPER%"
if errorlevel 1 exit /b 1
call :wait_for vLLM "%LLM_HEALTH%" "%LLM_TIMEOUT%" "%LLM_LOG%"
if errorlevel 1 exit /b 1
goto llm_done
:llm_skip
echo [1/3] vLLM already healthy on port %LLM_PORT% - skipped.
:llm_done

rem --- 2. Backend ------------------------------------------------------------
call :health "%BACKEND_HEALTH%"
if "!SVC_UP!"=="1" goto backend_skip
echo [2/3] Starting backend on port %BACKEND_PORT% ...
del "%RUN_DIR%\backend.pid" >nul 2>&1
call :launch backend "%BACKEND_WRAPPER%"
if errorlevel 1 exit /b 1
call :wait_for Backend "%BACKEND_HEALTH%" "%BACKEND_TIMEOUT%" "%BACKEND_LOG%"
if errorlevel 1 exit /b 1
goto backend_done
:backend_skip
echo [2/3] Backend already healthy on port %BACKEND_PORT% - skipped.
:backend_done

rem --- 3. Frontend -----------------------------------------------------------
call :health "%FRONTEND_HEALTH%"
if "!SVC_UP!"=="1" goto frontend_skip
echo [3/3] Starting frontend on port %FRONTEND_PORT% ...
del "%RUN_DIR%\frontend.pid" >nul 2>&1
call :launch frontend "%FRONTEND_WRAPPER%"
if errorlevel 1 exit /b 1
call :wait_for Frontend "%FRONTEND_HEALTH%" "%FRONTEND_TIMEOUT%" "%FRONTEND_LOG%"
if errorlevel 1 exit /b 1
goto frontend_done
:frontend_skip
echo [3/3] Frontend already healthy on port %FRONTEND_PORT% - skipped.
:frontend_done

start "" http://localhost:%FRONTEND_PORT%
for /f %%T in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeSeconds()"') do set "END_TS=%%T"
set /a ELAPSED=END_TS-START_TS

echo.
echo ==========================================
echo   CreatorDesk AI is up in !ELAPSED!s.
echo   vLLM    : http://localhost:%LLM_PORT%/v1
echo   Backend : http://localhost:%BACKEND_PORT%
echo   Docs    : http://localhost:%BACKEND_PORT%/docs
echo   Frontend: http://localhost:%FRONTEND_PORT%
echo   Logs    : %LOG_DIR%
echo   Stop    : stop.bat
echo ==========================================
echo.
exit /b 0

rem ---------------------------------------------------------------------------
:health
curl.exe -fsS -m 3 -o NUL "%~1" >nul 2>&1
if errorlevel 1 (set "SVC_UP=0") else (set "SVC_UP=1")
exit /b 0

:launch
set "L_NAME=%~1"
set "L_WRAPPER=%~2"
powershell -NoProfile -Command "$p = Start-Process -FilePath '%L_WRAPPER%' -WindowStyle Minimized -PassThru; [IO.File]::WriteAllText('%RUN_DIR%\%L_NAME%.pid', [string]$p.Id)"
if errorlevel 1 (
    echo ERROR: could not launch %L_NAME%.
    exit /b 1
)
echo   Launched %L_NAME%, PID recorded in .run\%L_NAME%.pid
exit /b 0

:wait_for
set "W_NAME=%~1"
set "W_URL=%~2"
set "W_TIMEOUT=%~3"
set "W_LOG=%~4"
set /a W_MAX=W_TIMEOUT/3+1
set /a W_TRY=0
:wait_loop
set /a W_TRY+=1
curl.exe -fsS -m 3 -o NUL "%W_URL%" >nul 2>&1
if not errorlevel 1 (
    echo   [OK] %W_NAME% healthy after ~!W_TRY! checks.
    exit /b 0
)
if !W_TRY! GEQ !W_MAX! (
    echo.
    echo ERROR: %W_NAME% did not become healthy within %W_TIMEOUT%s.
    echo   Health URL: %W_URL%
    echo   Log file  : %W_LOG%
    exit /b 1
)
ping -n 4 127.0.0.1 >nul 2>&1
goto wait_loop
