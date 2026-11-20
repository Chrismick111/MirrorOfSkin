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
$state=Join-Path $addon 'workbench-instance.json'
if(Test-Path -LiteralPath $state){
 try{
  $url=(Get-Content -LiteralPath $state -Raw|ConvertFrom-Json).url
  if($url -match '^http://127\.0\.0\.1:\d{1,5}/[A-Za-z0-9_-]+/$'){
   $ping=Invoke-RestMethod -Uri ($url+'api/instance-ping') -TimeoutSec 1
   if($ping.workbench){Start-Process $url;exit 0}
  }
 }catch{}
}
$script=Join-Path $PSScriptRoot 'workbench.py'
$logId=(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$logDir=Join-Path ([IO.Path]::GetTempPath()) 'FaustRandomIdentity-Workbench'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$arguments=@(('"'+$script+'"'),'--addon',('"'+$addon+'"'))
if($HostProcessId -gt 0){$arguments+=@('--host-pid',"$HostProcessId")}
Start-Process -FilePath $python -ArgumentList $arguments -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir ('workbench-start-'+$logId+'.log')) -RedirectStandardError (Join-Path $logDir ('workbench-error-'+$logId+'.log'))
