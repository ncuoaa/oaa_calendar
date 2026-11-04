$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Install Python 3.12 or newer with the Windows Python launcher, then run this script again.'
}
& py -3 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python virtual environment.' }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Installed. Place credentials.json here, then run authorize-windows.ps1.'
