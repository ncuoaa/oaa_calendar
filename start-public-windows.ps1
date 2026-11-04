$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$tunnelCommand = Get-Command cloudflared -ErrorAction Stop
New-Item -ItemType Directory -Path '.local' -Force | Out-Null
$outLog = Join-Path $PSScriptRoot '.local\tunnel-output.log'
$errorLog = Join-Path $PSScriptRoot '.local\tunnel-errors.log'
$tunnelProcess = Start-Process -FilePath $tunnelCommand.Source -ArgumentList @('tunnel', '--url', 'http://127.0.0.1:8080', '--no-autoupdate', '--protocol', 'http2') -WindowStyle Hidden -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errorLog
$previousOrigins = $env:ALLOWED_ORIGINS
try {
    $deadline = (Get-Date).AddSeconds(45)
    $publicOrigin = $null
    while ((Get-Date) -lt $deadline -and -not $tunnelProcess.HasExited) {
        $logText = Get-Content -LiteralPath $errorLog -Raw -ErrorAction SilentlyContinue
        if ($logText -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $publicOrigin = $Matches[0]; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $publicOrigin) { throw 'No public URL was created. Check .local\tunnel-errors.log.' }
    $env:ALLOWED_ORIGINS = 'https://december-2026-availability.oaaailab-6179.chatgpt.site,' + $publicOrigin
    Set-Content -LiteralPath '.local\public-url.txt' -Value ($publicOrigin + '/availability') -Encoding utf8
    Write-Host ('Temporary public page: ' + $publicOrigin + '/availability')
    Write-Host 'Keep this computer awake and this process running. Restarting creates a different public URL.'
    & .\start-windows.ps1
} finally {
    $env:ALLOWED_ORIGINS = $previousOrigins
    if (-not $tunnelProcess.HasExited) { Stop-Process -Id $tunnelProcess.Id }
}
