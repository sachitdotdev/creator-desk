# CreatorDesk AI - one-click startup (PowerShell)
#
# Double-click / right-click "Run with PowerShell", or run:
#   pwsh -File .\start.ps1
#
# Creates the Python venv (Python 3.12 / 3.11) and installs backend requirements
# if missing, installs frontend node_modules if missing, then opens two separate
# PowerShell windows: one for the FastAPI backend (port 8000) and one
# for the Vite frontend (port 5173).

$ErrorActionPreference = 'Stop'

# Relaunch with ExecutionPolicy Bypass so this works even under a
# restricted execution policy (the default on Windows).
$policy = [string](Get-ExecutionPolicy -Scope CurrentUser -ErrorAction SilentlyContinue)
if ($policy -in @('Restricted', 'AllSigned')) {
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy", "Bypass", "-NoProfile", "-File", $MyInvocation.MyCommand.Definition -WindowTitle "CreatorDesk Startup"
    exit
}

$Root    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  CreatorDesk AI - Startup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# --- Prerequisites ----------------------------------------------------------
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python was not found on PATH. Install from https://www.python.org"
    exit 1
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error "Node.js was not found on PATH. Install from https://nodejs.org"
    exit 1
}

# --- Select Python 3.12 (or 3.11) via the 'py' launcher ---------------------
# The previous venv was built under Python 3.14, which is incompatible with
# SQLAlchemy (TypingOnly / AssertionError). Force 3.12 (fallback 3.11).
$PyCmd   = 'py'
$PyVer   = $null
foreach ($v in @('3.12', '3.11')) {
    $r = py -$v --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        $PyCmd = "py -$v"
        $PyVer = $v
        break
    }
}
if (-not $PyVer) {
    Write-Error "Python 3.12 or 3.11 was not found via the 'py' launcher.`
Install it first, e.g.:  py install 3.12"
    exit 1
}
Write-Host "[Python] Using Python $PyVer ($PyCmd)" -ForegroundColor Yellow

# --- 1. Create / verify Python venv -----------------------------------------
$VenvPython = Join-Path $Backend "venv\Scripts\python.exe"
$Rebuild    = $false

if (Test-Path $VenvPython) {
    $VenvVer = & $VenvPython --version 2>$null
    if ($VenvVer -match 'Python (3\.12|3\.11)') {
        Write-Host "[1/4] Python virtual environment already exists ($VenvVer)." -ForegroundColor Green
    } else {
        Write-Host "[1/4] Existing venv is $VenvVer (incompatible). Rebuilding with Python $PyVer ..." -ForegroundColor Yellow
        $Rebuild = $true
    }
} else {
    $Rebuild = $true
    Write-Host "[1/4] Creating Python virtual environment (Python $PyVer) at backend\venv ..." -ForegroundColor Yellow
}

if ($Rebuild) {
    if (Test-Path (Join-Path $Backend "venv")) {
        Remove-Item -Recurse -Force (Join-Path $Backend "venv") -ErrorAction SilentlyContinue
    }
    & $PyCmd -m venv (Join-Path $Backend "venv")
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to create the virtual environment."
        exit 1
    }
}

# Refresh path to the venv python after (re)creation
$VenvPython = Join-Path $Backend "venv\Scripts\python.exe"

# --- 2. Install / upgrade backend requirements --------------------------------
Write-Host "[2/4] Installing backend requirements (this may take a minute) ..." -ForegroundColor Yellow
& $VenvPython -m pip install --upgrade -r (Join-Path $Backend "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to install backend requirements."
    exit 1
}

# --- 3. Backend window: FastAPI on port 8000 ---------------------------------
Write-Host "[3/4] Starting FastAPI backend ..." -ForegroundColor Yellow
$backendArgs = @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", "& 'venv\Scripts\Activate.ps1'; uvicorn app.main:app --reload --port 8000")
Start-Process powershell.exe @backendArgs -WorkingDirectory $Backend -WindowTitle "CreatorDesk Backend"

# --- 4. Frontend window: npm install (if needed) + npm run dev ---------------
Write-Host "[4/4] Starting frontend ..." -ForegroundColor Yellow
$frontendArgs = @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", "if (-not (Test-Path 'node_modules')) { npm install }; npm run dev")
Start-Process powershell.exe @frontendArgs -WorkingDirectory $Frontend -WindowTitle "CreatorDesk Frontend"

# --- Done -------------------------------------------------------------------
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  CreatorDesk AI is starting..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Backend API : http://localhost:8000"   -ForegroundColor Green
Write-Host "  Backend docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  Frontend UI : http://localhost:5173"    -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Each service runs in its own PowerShell window. Close those windows to stop the services."
