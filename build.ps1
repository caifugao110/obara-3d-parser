<#
.SYNOPSIS
Builds obara-3d-parser as a standalone Windows executable.

.DESCRIPTION
This script automates the complete build process:
1. Validates environment (Python, PyInstaller)
2. Cleans previous build artifacts
3. Runs PyInstaller with the spec file
4. Verifies the output

Run with: .\build.ps1
#>

$ErrorActionPreference = "Stop"

$scriptPath = $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptPath
$specFile = Join-Path $projectRoot "obara-3d-parser.spec"
$iconFile = Join-Path (Join-Path $projectRoot "assets") "app_icon.ico"
$distDir = Join-Path $projectRoot "dist"
$buildDir = Join-Path $projectRoot "build"
$exePath = Join-Path (Join-Path $distDir "obara-3d-parser") "obara-3d-parser.exe"
$venvDir = Join-Path $projectRoot ".venv"

Write-Host "`n=== obara-3d-parser Build Script ===" -ForegroundColor Cyan

Write-Host "`n[1/6] Validating environment..." -ForegroundColor Yellow

$pythonExe = $null
$pyinstallerExe = $null

if (Test-Path $venvDir) {
    $venvPython = Join-Path (Join-Path $venvDir "Scripts") "python.exe"
    $venvPyinstaller = Join-Path (Join-Path $venvDir "Scripts") "pyinstaller.exe"
    
    if (Test-Path $venvPython) {
        $pythonExe = $venvPython
        Write-Host "  Found virtual environment: $venvDir" -ForegroundColor Green
    }
    if (Test-Path $venvPyinstaller) {
        $pyinstallerExe = $venvPyinstaller
    }
}

if (-not $pythonExe) {
    $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $pythonExe) {
        Write-Error "Python not found. Please install Python 3.13+ or create a virtual environment."
    }
    Write-Host "  Using system Python: $pythonExe" -ForegroundColor Yellow
}

if (-not $pyinstallerExe) {
    $pyinstallerExe = (Get-Command pyinstaller -ErrorAction SilentlyContinue).Source
    if (-not $pyinstallerExe) {
        Write-Error "PyInstaller not found. Run: $pythonExe -m pip install pyinstaller"
    }
    Write-Host "  Using system PyInstaller: $pyinstallerExe" -ForegroundColor Yellow
} else {
    Write-Host "  Using venv PyInstaller: $pyinstallerExe" -ForegroundColor Green
}

try {
    $pythonVersion = & $pythonExe --version 2>&1
    Write-Host "  Python: $pythonVersion"
} catch {
    Write-Error "Failed to get Python version."
}

if (-not (Test-Path $specFile)) {
    Write-Error "Spec file not found: $specFile"
}

if (-not (Test-Path $iconFile)) {
    Write-Error "Icon file not found: $iconFile"
}

Write-Host "`n[2/6] Cleaning previous build artifacts..." -ForegroundColor Yellow

if (Test-Path $distDir) {
    Remove-Item -Recurse -Force $distDir
    Write-Host "  Removed dist directory"
}

if (Test-Path $buildDir) {
    Remove-Item -Recurse -Force $buildDir
    Write-Host "  Removed build directory"
}

if (Test-Path $venvDir) {
    Write-Host "  Skipping .venv directory (preserving virtual environment)" -ForegroundColor Green
}

Write-Host "`n[3/6] Running PyInstaller..." -ForegroundColor Yellow

Push-Location $projectRoot
try {
    $args = @(
        "--noconfirm",
        "--distpath", "dist",
        "--workpath", "build",
        "obara-3d-parser.spec"
    )
    
    Write-Host "  Command: pyinstaller $($args -join ' ')"
    
    $process = Start-Process -FilePath $pyinstallerExe -ArgumentList $args -NoNewWindow -Wait -PassThru -RedirectStandardOutput "build_log.txt" -RedirectStandardError "build_err.txt"
    
    if ($process.ExitCode -ne 0) {
        Write-Host "`n=== BUILD FAILED ===" -ForegroundColor Red
        Write-Host "`nBuild errors:" -ForegroundColor Red
        Get-Content "build_err.txt" | Write-Host
        Write-Host "`nBuild output (last 50 lines):" -ForegroundColor Red
        Get-Content "build_log.txt" | Select-Object -Last 50 | Write-Host
        Remove-Item "build_log.txt", "build_err.txt" -ErrorAction SilentlyContinue
        exit 1
    }
    
    Remove-Item "build_log.txt", "build_err.txt" -ErrorAction SilentlyContinue
    
} finally {
    Pop-Location
}

Write-Host "`n[4/6] Verifying output..." -ForegroundColor Yellow

if (Test-Path $exePath) {
    $fileInfo = Get-Item $exePath
    $sizeMB = [math]::Round($fileInfo.Length / 1MB, 1)
    Write-Host "  EXE created: $exePath" -ForegroundColor Green
    Write-Host "  Size: $sizeMB MB" -ForegroundColor Green
    
    Write-Host "`n  Testing startup..." -ForegroundColor Yellow
    $proc = Start-Process -FilePath $exePath -NoNewWindow -PassThru
    Start-Sleep -Seconds 3
    
    if ($proc.HasExited) {
        Write-Host "  WARNING: Process exited with code $($proc.ExitCode)" -ForegroundColor Yellow
        if ($proc.ExitCode -ne 0) {
            Write-Host "  Build may have issues. Check if all dependencies are bundled correctly." -ForegroundColor Yellow
        }
    } else {
        $proc.Kill()
        Write-Host "  OK: Application started successfully" -ForegroundColor Green
    }
    
} else {
    Write-Error "EXE not found at: $exePath"
}

Write-Host "`n[5/6] Cleaning intermediate build artifacts..." -ForegroundColor Yellow

if (Test-Path $buildDir) {
    Remove-Item -Recurse -Force $buildDir
    Write-Host "  Removed intermediate build directory" -ForegroundColor Green
}

if (Test-Path $venvDir) {
    Write-Host "  Skipping .venv directory (preserving virtual environment)" -ForegroundColor Green
}

Write-Host "`n[6/6] Build complete!" -ForegroundColor Green
Write-Host "`nDistribution: $distDir"
Write-Host "Executable: $exePath"
