# Start student and office LostLink portals side by side for a local jury demo.
# Uses distinct hostnames so the browser keeps each portal's session cookie separate.
$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv Python. Create .venv and install requirements.txt before running this script."
}

$dbDir = Join-Path $root "data"
$uploads = Join-Path $dbDir "uploads"
$dbPath = Join-Path $dbDir "lostlink.db"
New-Item -ItemType Directory -Force -Path $uploads | Out-Null

$rootQ = $root.Replace("'", "''")
$pythonQ = $python.Replace("'", "''")
$dbPathQ = $dbPath.Replace("'", "''")
$uploadsQ = $uploads.Replace("'", "''")

$studentCommand = "Set-Location '$rootQ'; Set-Item Env:DEMO_MODE 'true'; Set-Item Env:DATABASE_PATH '$dbPathQ'; Set-Item Env:UPLOAD_DIR '$uploadsQ'; & '$pythonQ' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
$officeCommand = "Set-Location '$rootQ'; Set-Item Env:DEMO_MODE 'true'; Set-Item Env:DATABASE_PATH '$dbPathQ'; Set-Item Env:UPLOAD_DIR '$uploadsQ'; & '$pythonQ' -m uvicorn app.main:app --host 127.0.0.1 --port 8001"

Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $studentCommand)
Start-Sleep -Seconds 3
Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $officeCommand)
Start-Sleep -Seconds 3

# Different hostnames are deliberate: localhost and 127.0.0.1 have separate cookies.
Start-Process "http://localhost:8000"
Start-Process "http://127.0.0.1:8001"

Write-Host ""
Write-Host "LostLink jury portals are starting:" -ForegroundColor Green
Write-Host "Student portal: http://localhost:8000"
Write-Host "Office portal:  http://127.0.0.1:8001"
Write-Host "Both share the local demo database: $dbPath"
Write-Host "Demo-only server. Do not expose either port to the public internet."
Write-Host ""
Write-Host "Student 1: student@lostlink.local / student123"
Write-Host "Student 2: student2@lostlink.local / student2123"
Write-Host "Student 3: student3@lostlink.local / student3123"
Write-Host "Student 4: student4@lostlink.local / student4123"
Write-Host "Office:    office@lostlink.local / office123"
