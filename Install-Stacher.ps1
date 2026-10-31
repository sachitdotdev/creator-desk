# Stacher Installation Automation Script
# Installs Stacher.Stacher via winget with silent flags & accepted agreements
# Verifies FFmpeg dependency and confirms install path / executable readiness

$ErrorActionPreference = "Continue"
$global:installSucceeded = $false

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Stacher Installation Automation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# Step 1: Check if winget is available
# ---------------------------------------------------------------------------
Write-Host "`n[1/3] Checking winget availability..." -ForegroundColor Yellow
$wingetCmd = Get-Command winget -ErrorAction SilentlyContinue
if (-not $wingetCmd) {
    Write-Host "winget is NOT available on this machine." -ForegroundColor Red
    Write-Host "Please install the App Installer (winget) from Microsoft Store or GitHub, then re-run." -ForegroundColor Red
    exit 1
}
Write-Host "winget found at: $($wingetCmd.Source)" -ForegroundColor Green

# ---------------------------------------------------------------------------
# Step 2: Install Stacher (Stacher.Stacher) with silent flags & agreements
# ---------------------------------------------------------------------------
Write-Host "`n[2/3] Installing Stacher (Stacher.Stacher)..." -ForegroundColor Yellow
$installArgs = @("-e", "--id", "Stacher.Stacher", "--silent", "--accept-package-agreements", "--accept-source-agreements")
& winget install @installArgs
$wingetExit = $LASTEXITCODE

if ($wingetExit -eq 0) {
    Write-Host "Stacher install completed successfully (exit code 0)." -ForegroundColor Green
    $global:installSucceeded = $true
} elseif ($wingetExit -eq 1) {
    # Exit code 1 often means "already installed" or "nothing to install"
    Write-Host "winget exited with code 1 (Stacher may already be installed / up to date). Continuing to verify." -ForegroundColor Yellow
    $global:installSucceeded = $true
} else {
    Write-Host "winget install exited with code $wingetExit. Installation may have failed." -ForegroundColor Red
}

# ---------------------------------------------------------------------------
# Step 3: Verify FFmpeg (secondary dependency for local media rendering)
# ---------------------------------------------------------------------------
Write-Host "`n[3/3] Checking FFmpeg dependency..." -ForegroundColor Yellow
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpegCmd) {
    Write-Host "FFmpeg not found in PATH. Installing Gyan.FFmpeg via winget..." -ForegroundColor Yellow
    & winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
    $ffmpegExit = $LASTEXITCODE
    $ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
    if (-not $ffmpegCmd) {
        Write-Host "FFmpeg was not located after install attempt. You may need to install it manually." -ForegroundColor Red
    } else {
        Write-Host "FFmpeg installed at: $($ffmpegCmd.Source)" -ForegroundColor Green
    }
} else {
    Write-Host "FFmpeg already installed at: $($ffmpegCmd.Source)" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# Step 4: Confirm Stacher installation path & executable readiness
# ---------------------------------------------------------------------------
Write-Host "`n[Final] Locating Stacher executable..." -ForegroundColor Yellow

$stacherPath = $null

# Try PATH first
$stacherCmd = Get-Command Stacher -ErrorAction SilentlyContinue
if ($stacherCmd) {
    $stacherPath = $stacherCmd.Source
}

# Fallback: common winget / user install locations
if (-not $stacherPath) {
    $commonPaths = @(
        "$env:LOCALAPPDATA\Programs\Stacher\Stacher.exe",
        "$env:LOCALAPPDATA\Stacher\Stacher.exe",
        "$env:ProgramFiles\Stacher\Stacher.exe",
        "$env:ProgramFiles(x86)\Stacher\Stacher.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\Stacher.exe"
    )
    foreach ($p in $commonPaths) {
        if (Test-Path -Path $p -PathType Leaf) {
            $stacherPath = $p
            break
        }
    }
}

# Last resort: query winget list for the package
if (-not $stacherPath) {
    $listOut = winget list --id Stacher.Stacher 2>$null
    if ($listOut -match "Stacher.Stacher") {
        Write-Host "Stacher package is registered in winget (exact exe path not auto-detected)." -ForegroundColor Yellow
    }
}

if ($stacherPath -and (Test-Path -Path $stacherPath -PathType Leaf)) {
    Write-Host "Stacher executable found: $stacherPath" -ForegroundColor Green
    Write-Host "Stacher is ready to launch." -ForegroundColor Green
} else {
    Write-Host "Stacher executable was not auto-detected in PATH or common locations." -ForegroundColor Red
    Write-Host "Launch via Start Menu or run: winget list --id Stacher.Stacher" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Installation Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "winget available : $($null -ne $wingetCmd)"
Write-Host "Stacher install  : $global:installSucceeded"
Write-Host "FFmpeg present   : $($null -ne $ffmpegCmd)"
Write-Host "Stacher exe      : $stacherPath"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Done." -ForegroundColor Cyan
