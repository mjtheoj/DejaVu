# Start LostLink with ONE terminal, ONE Uvicorn process, and ONE browser origin.
# Switch student/office roles through the in-app demo role switcher; all actions use one database.
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$envFile = Join-Path $root ".env"
$dbDir = Join-Path $root "data"
$dbPath = Join-Path $dbDir "lostlink.db"
$uploads = Join-Path $dbDir "uploads"

if (-not (Test-Path $python)) {
    throw "Missing .venv Python. Create .venv and install requirements.txt first."
}
if (-not (Test-Path $envFile)) {
    throw "Missing .env. Copy .env.example to .env and replace SESSION_SECRET with a unique random value."
}

$secretLine = Get-Content $envFile | Where-Object { $_ -match '^\s*SESSION_SECRET\s*=' } | Select-Object -Last 1
$secretValue = if ($secretLine) { ($secretLine -split '=', 2)[1].Trim().Trim('"').Trim("'") } else { "" }
if ([string]::IsNullOrWhiteSpace($secretValue) -or
    $secretValue -eq "replace-with-a-long-random-secret-before-running" -or
    $secretValue -eq "local-development-only-change-this") {
    throw "SESSION_SECRET is a placeholder. Generate one with: python -c ""import secrets; print(secrets.token_urlsafe(48))"""
}

Set-Location $root
New-Item -ItemType Directory -Force -Path $dbDir, $uploads | Out-Null
$env:DEMO_MODE = "true"
$env:SESSION_HTTPS_ONLY = "false"
$env:DATABASE_PATH = $dbPath
$env:UPLOAD_DIR = $uploads

& $python -c "import fastapi, uvicorn; import app.main; print('LostLink demo preflight passed')"
if ($LASTEXITCODE -ne 0) {
    throw "LostLink preflight failed. Fix the error above before starting the demo."
}

Write-Host ""
Write-Host "LostLink single-terminal local demo" -ForegroundColor Cyan
Write-Host "URL: http://127.0.0.1:8000"
Write-Host "Database: $dbPath"
Write-Host "Use the in-app Switch to office / Switch to student button to change roles."
Write-Host "All roles use this one server and database. Do not start a second server."
Write-Host "Student: student@lostlink.local / student123"
Write-Host "Office:   office@lostlink.local / office123"
Write-Host "Local demo only; do not expose this server to the public internet."
Write-Host "Stop with Ctrl+C."
Write-Host ""

Start-Process "http://127.0.0.1:8000"
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
