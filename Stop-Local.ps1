param([string]$Distro='Ubuntu-22.04')
$ErrorActionPreference='Stop'
$envFile=Join-Path $PSScriptRoot '.env'
if(Test-Path -LiteralPath $envFile){foreach($line in Get-Content -LiteralPath $envFile){if($line -match '^WSL_DISTRO=(.+)$'){$Distro=$Matches[1].Trim()}}}
$linuxPath=(& wsl.exe -d $Distro -- wslpath -a -u $PSScriptRoot).Trim()
if($LASTEXITCODE -ne 0){throw 'WSL path conversion failed'}
& wsl.exe -d $Distro -- bash "$linuxPath/stop.sh"
if($LASTEXITCODE -ne 0){throw 'Stop failed; read output'}
