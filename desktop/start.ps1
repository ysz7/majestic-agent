# Majestic Desktop - single launcher (dev mode)
# Usage: .\start.ps1  (from desktop/ directory)

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$env:MAJESTIC_ROOT = $ProjectRoot
Write-Host "Project root: $ProjectRoot" -ForegroundColor Cyan

# Setup MSVC environment (Windows)
$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
if (Test-Path $vcvars) {
    $envLines = cmd /c "`"$vcvars`" x64 >nul 2>&1 && set"
    foreach ($line in $envLines) {
        if ($line -match '^([^=]+)=(.+)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
        }
    }
    Write-Host "MSVC environment loaded." -ForegroundColor DarkGray
}

# Add Rust to PATH
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"

# Ensure default profile exists
$profileDir = "$ProjectRoot\profiles\default"
if (-not (Test-Path $profileDir)) {
    Write-Host "Creating default profile..." -ForegroundColor Yellow
    Push-Location $ProjectRoot
    python -m majestic new default 2>&1 | Out-Null
    Pop-Location
}

# Start agent if not already running
$agentRunning = $false
$registry = "$ProjectRoot\data\registry.json"
if (Test-Path $registry) {
    try {
        $reg = Get-Content $registry -Raw | ConvertFrom-Json
        $entry = $reg.default
        if ($entry -and $entry.pid) {
            try {
                Get-Process -Id $entry.pid -ErrorAction Stop | Out-Null
                $agentRunning = $true
                Write-Host "Agent already running (PID $($entry.pid))." -ForegroundColor Green
            } catch {}
        }
    } catch {}
}

if (-not $agentRunning) {
    Write-Host "Starting default agent..." -ForegroundColor Yellow
    $venvPython = "$ProjectRoot\.venv\Scripts\python.exe"
    $pythonExe = if (Test-Path $venvPython) { $venvPython } else { "python" }
    Start-Process $pythonExe `
        -ArgumentList "-m majestic.__background__ default" `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden

    $port = 17000
    $personaFile = "$profileDir\persona.yaml"
    if (Test-Path $personaFile) {
        $m = Select-String -Path $personaFile -Pattern "^port:\s*(\d+)"
        if ($m) { $port = [int]$m.Matches[0].Groups[1].Value }
    }
    Write-Host "Waiting for agent on port $port..." -ForegroundColor Yellow
    $ready = $false
    for ($i = 1; $i -le 20; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$port/status" `
                -UseBasicParsing -TimeoutSec 1 -ErrorAction Stop
            if ($r.StatusCode -lt 500) { $ready = $true; break }
        } catch {}
        Write-Host "  [$i/20] not ready yet..." -ForegroundColor DarkGray
        Start-Sleep -Seconds 2
    }
    if ($ready) {
        Write-Host "Agent ready on port $port." -ForegroundColor Green
    } else {
        Write-Host "Agent may still be starting, launching app anyway." -ForegroundColor Yellow
    }
}

Write-Host "Launching desktop app..." -ForegroundColor Cyan
npm run tauri:dev
