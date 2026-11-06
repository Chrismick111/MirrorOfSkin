$ErrorActionPreference='Stop'
$python=(Get-Command python -ErrorAction Stop).Source
$installedRoot=Split-Path $PSScriptRoot -Parent
$script=Join-Path $PSScriptRoot 'workbench.py'
$addon=$installedRoot
$logId=(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
Start-Process -FilePath $python -ArgumentList @(('"'+$script+'"'),'--addon',('"'+$addon+'"')) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot ('workbench-start-'+$logId+'.log')) -RedirectStandardError (Join-Path $PSScriptRoot ('workbench-error-'+$logId+'.log'))

