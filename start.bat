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
set "BOOTSTRAP_OK=%BACKEND%\venv\.bootstrap_ok"
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

rem --- Bootstrap the backend venv using a success marker. python.exe alone
rem --- does not prove pip install finished, so a missing marker re-runs the
rem --- install (fresh clone or an interrupted first run). --------------------
if not exist "%BOOTSTRAP_OK%" (
    echo [bootstrap] Bootstrapping backend venv ...
    if not exist "%BACKEND%\venv\Scripts\python.exe" (
        py -3.12 -m venv "%BACKEND%\venv" 2>NUL
        if errorlevel 1 py -3.11 -m venv "%BACKEND%\venv"
        if errorlevel 1 (
            echo ERROR: could not create backend venv; install Python 3.12/3.11.
            exit /b 1
        )
    )
    "%BACKEND%\venv\Scripts\python.exe" -m pip install -r "%BACKEND%\requirements.txt"
    if errorlevel 1 (
        echo ERROR: could not install backend requirements.
        exit /b 1
    )
    rem Marker only after pip install succeeds; keep the fast path when present.
    > "%BOOTSTRAP_OK%" echo ok
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
>> "%FRONTEND_WRAPPER%" echo if not exist node_modules (
>> "%FRONTEND_WRAPPER%" echo   call npm install
>> "%FRONTEND_WRAPPER%" echo   if errorlevel 1 exit /b 1
>> "%FRONTEND_WRAPPER%" echo )
>> "%FRONTEND_WRAPPER%" echo npm run dev -- --port %FRONTEND_PORT% --strictPort ^> "%FRONTEND_LOG%" 2^>^&1 ^< NUL

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
rem Pass paths through the environment: interpolating them into the PowerShell
rem source broke on paths containing a single quote. RUN_DIR is already an env
rem var; L_NAME and L_WRAPPER are exported by the set commands above.
powershell -NoProfile -Command "$p = Start-Process -FilePath $env:L_WRAPPER -WindowStyle Minimized -PassThru; [IO.File]::WriteAllText((Join-Path $env:RUN_DIR ($env:L_NAME + '.pid')), [string]$p.Id)"
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
rem Wall-clock budget in milliseconds with a 2s guard, so the final bounded
rem curl (max 3s) cannot push total wait past W_TIMEOUT. A healthy check exits
rem immediately, well before the budget is spent.
set /a W_BUDGET_MS=%W_TIMEOUT%*1000-2000
if !W_BUDGET_MS! LSS 1000 set /a W_BUDGET_MS=1000
rem Windows PowerShell 5.1 (powershell.exe) has no [Environment]::TickCount64.
rem Epoch milliseconds from [DateTimeOffset]::UtcNow are 64-bit, so keep them as
rem a string in batch and let PowerShell return only the small elapsed delta;
rem every set /a below then stays within the 32-bit range.
call :clock_ms W_START_MS
if errorlevel 1 goto wait_clock_fail
set /a W_TRY=0
:wait_loop
call :elapsed_ms W_ELAPSED_MS "!W_START_MS!"
if errorlevel 1 goto wait_clock_fail
set /a W_REMAIN_MS=W_BUDGET_MS-!W_ELAPSED_MS!
if !W_REMAIN_MS! LEQ 0 goto wait_fail
set /a W_CURL_S=(!W_REMAIN_MS!+999)/1000
if !W_CURL_S! GTR 3 set /a W_CURL_S=3
set /a W_TRY+=1
curl.exe -fsS -m !W_CURL_S! -o NUL "%W_URL%" >nul 2>&1
if not errorlevel 1 (
    echo   [OK] %W_NAME% healthy after ~!W_TRY! checks.
    exit /b 0
)
rem Sleep only while a full delay still fits inside the remaining budget.
call :elapsed_ms W_ELAPSED_MS "!W_START_MS!"
if errorlevel 1 goto wait_clock_fail
set /a W_REMAIN_MS=W_BUDGET_MS-!W_ELAPSED_MS!
if !W_REMAIN_MS! GEQ 2000 ping -n 2 127.0.0.1 >nul 2>&1
goto wait_loop
:wait_fail
echo.
echo ERROR: %W_NAME% did not become healthy within %W_TIMEOUT%s.
echo   Health URL: %W_URL%
echo   Log file  : %W_LOG%
exit /b 1
:wait_clock_fail
echo.
echo ERROR: %W_NAME% readiness clock unavailable - could not read a numeric
echo   millisecond timestamp from PowerShell. Aborting instead of looping.
echo   Health URL: %W_URL%
exit /b 1

rem ---------------------------------------------------------------------------
:clock_ms
rem %~1 = variable name that receives a 64-bit epoch-ms string.
set "%~1="
for /f "delims=" %%T in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()"') do set "%~1=%%T"
if not defined %~1 exit /b 1
call :is_digits "!%~1!"
if errorlevel 1 exit /b 1
exit /b 0

:elapsed_ms
rem %~1 = variable that receives elapsed ms (small, fits 32-bit).
rem %~2 = the start epoch-ms string recorded by :clock_ms.
set "%~1="
for /f "delims=" %%T in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() - [int64]%~2"') do set "%~1=%%T"
if not defined %~1 exit /b 1
call :is_digits "!%~1!"
if errorlevel 1 exit /b 1
exit /b 0

:is_digits
rem Succeed only for a non-empty string of ASCII digits (any length).
echo(%~1| findstr /R /C:"^[0-9][0-9]*$" >nul 2>&1
exit /b !errorlevel!
