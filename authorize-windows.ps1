param([switch]$Manual)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'Run install-windows.ps1 first.' }
if (-not (Test-Path -LiteralPath 'credentials.json')) { throw 'Place the Google Desktop OAuth client file here as credentials.json.' }
Write-Host 'Opening Google authorization. Choose the account that can view the supervisor calendars.'
if ($Manual) {
    $authJson = & .\.venv\Scripts\python.exe oauth_setup.py --json --manual
} else {
    $authJson = & .\.venv\Scripts\python.exe oauth_setup.py --json
}
if ($LASTEXITCODE -ne 0) { throw 'Google authorization failed.' }
$authText = $authJson -join "`n"
$authValues = $authText | ConvertFrom-Json
if (-not $authValues.GOOGLE_OAUTH_REFRESH_TOKEN) { throw 'No refresh token was returned.' }
New-Item -ItemType Directory -Path '.local' -Force | Out-Null
# Windows DPAPI: only this Windows user on this machine can decrypt the file.
$protectedAuth = ConvertTo-SecureString -String $authText -AsPlainText -Force
$protectedAuth | Export-Clixml -LiteralPath '.local\google-oauth.xml'
$authJson = $null
$authText = $null
$authValues = $null
Write-Host 'Authorization saved with Windows encryption. Run start-windows.ps1 using this same Windows account.'
