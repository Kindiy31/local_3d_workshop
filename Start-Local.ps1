param([string]$Distro='Ubuntu-22.04',[int]$Port=7861)
$ErrorActionPreference='Stop'
$repo=$PSScriptRoot
if(Test-Path -LiteralPath (Join-Path $repo '.env')){
 foreach($line in Get-Content -LiteralPath (Join-Path $repo '.env')){
  if($line -match '^WSL_DISTRO=(.+)$'){$Distro=$Matches[1].Trim()}
  if($line -match '^WORKSHOP_PORT=(\d+)$'){$Port=[int]$Matches[1]}
 }
}
try { $null=Invoke-RestMethod "http://localhost:$Port/api/health" -TimeoutSec 2; Write-Host "Already active: http://localhost:$Port"; exit 0 } catch {}
$linuxPath=(& wsl.exe -d $Distro -- wslpath -a -u $repo).Trim()
if($LASTEXITCODE -ne 0){throw 'WSL path conversion failed'}
if($linuxPath -match '[\r\n"]'){throw 'Unsupported path characters'}
$logs=Join-Path $repo 'runtime';New-Item -ItemType Directory -Path $logs -Force | Out-Null
Start-Process -FilePath 'wsl.exe' -ArgumentList "-d $Distro -- bash `"$linuxPath/run.sh`" $Port" -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'service.log') -RedirectStandardError (Join-Path $logs 'service-error.log') | Out-Null
Write-Host "Starting: http://localhost:$Port (first startup may take 30 seconds)"
