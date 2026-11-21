# Jarvis installer for Windows 10/11.
# Run from the project folder:  powershell -ExecutionPolicy Bypass -File install.ps1
param([string]$Model = "qwen2.5:3b")

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Step "Checking Python"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Python is not installed. Install Python 3.10+ from https://www.python.org/downloads/ (tick 'Add to PATH'), then rerun." -ForegroundColor Red
    exit 1
}
python --version

Step "Creating virtual environment (.venv)"
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }

Step "Installing Python packages"
.\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Step "Checking Ollama (local AI brain)"
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
$ollamaExe = if ($ollama) { $ollama.Source } else { "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }
if (-not (Test-Path $ollamaExe)) {
    $answer = Read-Host "Ollama is not installed. Install it now with winget? (y/n)"
    if ($answer -match '^y') {
        winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
    } else {
        Write-Host "Skipped. Basic commands will work; install Ollama later from https://ollama.com for the AI brain." -ForegroundColor Yellow
    }
}
if (Test-Path $ollamaExe) {
    try { Invoke-RestMethod http://localhost:11434/api/tags -TimeoutSec 3 | Out-Null }
    catch { Start-Process $ollamaExe -ArgumentList serve -WindowStyle Hidden; Start-Sleep 5 }
    $ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
    Write-Host "Downloading AI model $Model (about 2 GB for 3b, 1 GB for 1.5b). Your RAM: $ramGB GB"
    & $ollamaExe pull $Model
}

Step "Creating config file"
if (-not (Test-Path jarvis_config.json)) {
    Copy-Item jarvis_config.example.json jarvis_config.json
    (Get-Content jarvis_config.json) -replace '"qwen2.5:3b"', "`"$Model`"" | Set-Content jarvis_config.json
    Write-Host "Created jarvis_config.json - edit it to change your name, voice or model."
}

Step "Downloading the speech model and running the system check"
.\.venv\Scripts\python.exe -c "from faster_whisper import WhisperModel; import json; cfg=json.load(open('jarvis_config.json')); WhisperModel(cfg.get('WHISPER_MODEL','base.en'), device='cpu', compute_type='int8')"
.\.venv\Scripts\python.exe main.py --check

Write-Host "`nDone. Start Jarvis with:  .\jarvis.bat   (or .\jarvis.bat --text to type)" -ForegroundColor Green
