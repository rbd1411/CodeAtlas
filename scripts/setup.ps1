$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPath = Join-Path $ProjectRoot '.venv'

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m venv $VenvPath
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python -m venv $VenvPath
} else {
    throw 'Python 3.11 or newer is required. Install Python, then run this script again.'
}

$PythonPath = Join-Path $VenvPath 'Scripts\python.exe'
& $PythonPath -m pip install --upgrade pip
& $PythonPath -m pip install -e "$ProjectRoot\backend[dev]"
Push-Location $ProjectRoot
try {
    npm install
    if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
} finally {
    Pop-Location
}
Write-Host 'CodeAtlas setup is complete. Run .\scripts\dev.ps1 next.' -ForegroundColor Green

