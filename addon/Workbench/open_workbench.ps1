$ErrorActionPreference='Stop'
$HostProcessId=if($args.Count -ge 2 -and $args[0] -eq '-HostProcessId'){[int]$args[1]}else{0}
$addon=Split-Path $PSScriptRoot -Parent
$launcherRoot=Split-Path (Split-Path $addon -Parent) -Parent
$embedded=Join-Path $launcherRoot 'resources\mod_loader\_internal\venv\Bins\python.exe'
if(Test-Path -LiteralPath $embedded){$python=$embedded}
else {
 $cmd=Get-Command python.exe -ErrorAction SilentlyContinue
 if(-not $cmd){throw '未找到 Python，请安装 Python 3.9 或更新版本。'}
 $python=$cmd.Source
}
$script=Join-Path $PSScriptRoot 'workbench.py'
$logId=(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$logDir=Join-Path ([IO.Path]::GetTempPath()) 'FaustRandomIdentity-Workbench'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$arguments=@(('"'+$script+'"'),'--addon',('"'+$addon+'"'))
if($HostProcessId -gt 0){$arguments+=@('--host-pid',"$HostProcessId")}
Start-Process -FilePath $python -ArgumentList $arguments -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir ('workbench-start-'+$logId+'.log')) -RedirectStandardError (Join-Path $logDir ('workbench-error-'+$logId+'.log'))
