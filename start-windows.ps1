param([ValidateRange(1024, 65535)][int]$Port = 8080)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Run install-windows.ps1 first.' }
$protectedAuth = Import-Clixml -LiteralPath '.local\google-oauth.xml'
$authCredential = New-Object System.Management.Automation.PSCredential('oauth', $protectedAuth)
$authValues = $authCredential.GetNetworkCredential().Password | ConvertFrom-Json
foreach ($key in @('GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET', 'GOOGLE_OAUTH_REFRESH_TOKEN')) {
    [Environment]::SetEnvironmentVariable($key, $authValues.$key, 'Process')
}
try {
    Write-Host "Starting local API at http://127.0.0.1:$Port . Press Ctrl+C to stop."
    & .\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'API process stopped with an error.' }
} finally {
    foreach ($key in @('GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET', 'GOOGLE_OAUTH_REFRESH_TOKEN')) {
        [Environment]::SetEnvironmentVariable($key, $null, 'Process')
    }
}
