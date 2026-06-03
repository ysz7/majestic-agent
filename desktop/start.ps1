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

# Ensure data dir exists
$dataDir = "$ProjectRoot\data"
if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Force $dataDir | Out-Null }

# Ensure default profile exists
$profileDir = "$ProjectRoot\profiles\default"
if (-not (Test-Path $profileDir)) {
    Write-Host "Creating default profile..." -ForegroundColor Yellow
    Push-Location $ProjectRoot
    python -m majestic new default 2>&1 | Out-Null
    Pop-Location
}

# Read port from persona.yaml
$port = 17000
$personaFile = "$profileDir\persona.yaml"
if (Test-Path $personaFile) {
    $m = Select-String -Path $personaFile -Pattern "^port:\s*(\d+)"
    if ($m) { $port = [int]$m.Matches[0].Groups[1].Value }
}

# Check if agent is already responding on port
$agentRunning = $false
try {
    $r = Invoke-WebRequest -Uri "http://localhost:$port/status" `
        -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($r.StatusCode -lt 500) {
        $agentRunning = $true
        Write-Host "Agent already running on port $port." -ForegroundColor Green
    }
} catch {}

if (-not $agentRunning) {
    Write-Host "Starting default agent..." -ForegroundColor Yellow
    # Use 'majestic run' so the agent is properly registered in registry.json
    Start-Process "majestic" `
        -ArgumentList @("run", "default") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden

    Write-Host "Waiting for agent on port $port (up to 3 min on first run)..." -ForegroundColor Yellow
    $ready = $false
    for ($i = 1; $i -le 90; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$port/status" `
                -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            if ($r.StatusCode -lt 500) { $ready = $true; break }
        } catch {}
        if ($i % 5 -eq 0) {
            $elapsed = $i * 2
            Write-Host "  [${elapsed}s] still starting..." -ForegroundColor DarkGray
        }
        Start-Sleep -Seconds 2
    }
    if ($ready) {
        Write-Host "Agent ready on port $port." -ForegroundColor Green
    } else {
        Write-Host "Agent did not start. Check logs:" -ForegroundColor Red
        Write-Host "  $agentErr" -ForegroundColor DarkGray
        if (Test-Path $agentErr) {
            $errContent = Get-Content $agentErr -Tail 8 -ErrorAction SilentlyContinue
            if ($errContent) {
                Write-Host "--- last lines of agent.err ---" -ForegroundColor DarkGray
                $errContent | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
            }
        }
        Write-Host "Launching app anyway (will retry connection from UI)." -ForegroundColor Yellow
    }
}

Write-Host "Launching desktop app..." -ForegroundColor Cyan
$env:VITE_AGENT_PORT = "$port"
& "$PSScriptRoot\node_modules\.bin\tauri.cmd" dev
