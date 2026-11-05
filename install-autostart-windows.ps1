param([string]$CredentialUsername = '', [string]$Repository = 'ncuoaa/oaa_calendar')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtimePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$runtimePythonw = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $runtimePythonw)) { throw 'Install the Python environment first.' }
foreach ($filename in @('google-oauth.xml','web-access.xml')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot ('.local\' + $filename)))) { throw 'Complete Google and website account setup first.' }
}
$shellPath = (Get-Process -Id $PID).Path
$basePython = & $runtimePython -c "import sys; print(sys._base_executable)"
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve Python installation.' }
$config = @{
    python=$runtimePython; base_python=$basePython.Trim(); site_packages=(Join-Path $PSScriptRoot '.venv\Lib\site-packages'); powershell=$shellPath; git=(Get-Command git -ErrorAction Stop).Source;
    cloudflared=(Get-Command cloudflared -ErrorAction Stop).Source;
    ngrok=(Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\ngrok.exe');
    repository=$Repository; credential_username=$CredentialUsername; pages_origin='https://ncuoaa.github.io'
}
if (Get-Command ngrok -ErrorAction SilentlyContinue) { $config.ngrok=(Get-Command ngrok).Source }
$config | ConvertTo-Json | Set-Content -LiteralPath '.local\service-config.json' -Encoding utf8
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $runtimePythonw -Argument ('"' + (Join-Path $PSScriptRoot 'service_supervisor.py') + '"') -WorkingDirectory $PSScriptRoot
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$retryTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'OAA Calendar Service' -Action $action -Trigger @($logonTrigger,$retryTrigger) -Settings $settings -Principal $principal -Description 'Start calendar API at Windows sign-in; monitor and recover API and tunnel failures.' -Force | Out-Null
Write-Output 'Installed OAA Calendar Service task. It starts at Windows sign-in, monitors health, and retries failures.'
