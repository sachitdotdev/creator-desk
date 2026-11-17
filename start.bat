@echo off
chcp 65001 >nul 2>&1
title CreatorDesk AI - Startup
setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

echo.
echo ==========================================
echo   CreatorDesk AI - Startup
echo ==========================================
echo.

:: --- Prerequisites ----------------------------------------------------------
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python was not found on PATH.
    pause
    exit /b 1
)
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Node.js was not found on PATH.
    pause
    exit /b 1
)

:: --- Select Python 3.12 (or 3.11) via the 'py' launcher ---------------------
set "PYVER="
set "PYCMD="
for %%V in (3.12 3.11) do (
    py -%%V --version >nul 2>&1
    if not errorlevel 1 (
        set "PYVER=%%V"
        set "PYCMD=py -%%V"
        goto :py_selected
    )
)
:py_selected
if not defined PYVER (
    echo ERROR: Python 3.12 or 3.11 was not found via the 'py' launcher.
    pause
    exit /b 1
)

:: --- 1. Create / verify Python venv -----------------------------------------
set "VENV_PY=%BACKEND%\venv\Scripts\python.exe"
set "REBUILD=0"

if exist "%VENV_PY%" (
    "%VENV_PY%" --version > "%TEMP%\creatordesk_venv_ver.txt" 2>&1
    findstr /c:"Python 3.12" "%TEMP%\creatordesk_venv_ver.txt" >nul 2>&1
    if not errorlevel 1 (
        :: Try to run pip to see if the venv is actually healthy
        "%BACKEND%\venv\Scripts\pip.exe" --version >nul 2>&1
        if errorlevel 1 (
            set "REBUILD=1"
            echo [1/4] Existing venv is corrupted. Rebuilding with Python %PYVER% ...
            rmdir /s /q "%BACKEND%\venv"
        ) else (
            echo [1/4] Python virtual environment already exists. Version: Python 3.12.
        )
    ) else (
        set "REBUILD=1"
        echo [1/4] Existing venv is incompatible. Rebuilding with Python %PYVER% ...
        rmdir /s /q "%BACKEND%\venv"
    )
) else (
    set "REBUILD=1"
    echo [1/4] Creating Python virtual environment with Python %PYVER% ...
)

if %REBUILD% equ 1 (
    %PYCMD% -m venv "%BACKEND%\venv"
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create the virtual environment.
        pause
        exit /b 1
    )
    :: Upgrade pip to fix the _distutils_hack issue before installing
    echo [2/4] Upgrading pip and setuptools...
    "%BACKEND%\venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
)

:: --- 3. Install / upgrade backend requirements -------------------------------
echo [3/4] Installing backend requirements (this may take a minute) ...
"%BACKEND%\venv\Scripts\pip.exe" install --timeout 300 --retries 5 -r "%BACKEND%\requirements.txt"
if %errorlevel% neq 0 (
    echo ERROR: Failed to install backend requirements.
    pause
    exit /b 1
)

:: --- 4. Start FastAPI backend on port 8080 in its own window ----------------
echo [4/4] Starting FastAPI backend ...
start "CreatorDesk Backend" cmd /k "cd /d "%BACKEND%" && call venv\Scripts\activate.bat && uvicorn app.main:app --reload --port 8080"

:: --- 5. Start frontend (npm install + npm run dev) in another window --------
echo [5/5] Starting frontend ...
start "CreatorDesk Frontend" cmd /k "cd /d "%FRONTEND%" && npm run dev"

:: --- Wait 4 seconds then open browser ---------------------------------------
timeout /t 4 /nobreak >nul
start "CreatorDesk Browser" cmd /k start http://localhost:5173

echo.
echo ==========================================
echo   CreatorDesk AI is starting...
echo ==========================================
echo   Backend API : http://localhost:8080
echo   Backend docs: http://localhost:8080/docs
echo   Frontend UI : http://localhost:5173
echo ==========================================
echo.
pause