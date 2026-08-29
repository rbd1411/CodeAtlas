$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$BackendPath = Join-Path $ProjectRoot 'backend'
if (-not (Test-Path $PythonPath)) {
    throw 'The virtual environment is missing. Run .\scripts\setup.ps1 first.'
}

$QuotedBackendPath = '"{0}"' -f $BackendPath
$ApiArguments = @('-m', 'uvicorn', 'codeatlas.app:app', '--app-dir', $QuotedBackendPath, '--host', '127.0.0.1', '--port', '8000', '--reload')
$ApiProcess = Start-Process -FilePath $PythonPath -ArgumentList $ApiArguments -WorkingDirectory $BackendPath -WindowStyle Hidden -PassThru

try {
    Push-Location $ProjectRoot
    npm run dev
} finally {
    Pop-Location
    if (-not $ApiProcess.HasExited) { Stop-Process -Id $ApiProcess.Id }
}
