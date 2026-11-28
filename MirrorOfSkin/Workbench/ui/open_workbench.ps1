$ErrorActionPreference='Stop'
$HostProcessId=0
$GameProcessId=0
$ExistingUrl=$null
$ServerOnly=$args -contains '-ServerOnly'
for($i=0;$i -lt $args.Count-1;$i++){if($args[$i] -eq '-HostProcessId'){$HostProcessId=[int]$args[$i+1]}
 if($args[$i] -eq '-ExistingUrl'){$ExistingUrl=$args[$i+1]}
 if($args[$i] -eq '-GameProcessId'){$GameProcessId=[int]$args[$i+1]}}
$addon=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$launcherRoot=Split-Path (Split-Path $addon -Parent) -Parent
$embedded=Join-Path $launcherRoot 'resources\mod_loader\_internal\venv\Bins\python.exe'
if(Test-Path -LiteralPath $embedded){$python=$embedded}
else {
 $cmd=Get-Command python.exe -ErrorAction SilentlyContinue
 if(-not $cmd){throw '未找到 Python，请安装 Python 3.9 或更新版本。'}
 $python=$cmd.Source
}
$dataRoot=if($env:FAUST_MOS_DATA_ROOT){$env:FAUST_MOS_DATA_ROOT}else{Join-Path $env:APPDATA 'FaustLauncher/MOS_data'}
function Attach-Workbench([string]$url){
 $token=$url.TrimEnd('/').Split('/')[-1]
 $body=@{host_pid=$null;game_pid=$null;startup_pid=$PID}
 if($HostProcessId -gt 0){$body.host_pid=$HostProcessId}
 if($GameProcessId -gt 0){$body.game_pid=$GameProcessId}
 $answer=Invoke-RestMethod -Method Post -Uri ($url+'api/instance-attach') -Headers @{'X-Workbench'=$token} -ContentType 'application/json' -Body ($body|ConvertTo-Json -Compress) -TimeoutSec 2
 return $answer.attached
}
function Write-WebviewLog([string]$message){
 try{
  $dir=Join-Path $dataRoot 'Workbench'
  New-Item -ItemType Directory -Force -Path $dir|Out-Null
  Add-Content -LiteralPath (Join-Path $dir 'webview.log') -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+' '+$message) -Encoding UTF8
 }catch{}
}
function Show-WorkbenchWindow([string]$url,[int]$serverId){
 $serverProcess=Get-Process -Id $serverId -ErrorAction SilentlyContinue
 if(-not $serverProcess){return}
 $null=$serverProcess.Handle
 $lib=Join-Path $launcherRoot '_internal\webview\lib'
 $core=Join-Path $lib 'Microsoft.Web.WebView2.Core.dll'
 $winForms=Join-Path $lib 'Microsoft.Web.WebView2.WinForms.dll'
 if(-not (Test-Path -LiteralPath $core) -or -not (Test-Path -LiteralPath $winForms)){
  Write-WebviewLog ('webview2 dll missing: '+$lib)
  Start-Process $url;return
 }
 $lock=Join-Path $dataRoot 'Workbench\webview-window.json'
 if(Test-Path -LiteralPath $lock){
  try{
   $info=Get-Content -LiteralPath $lock -Raw -Encoding UTF8|ConvertFrom-Json
   $proc=Get-Process -Id ([int]$info.pid) -ErrorAction SilentlyContinue
   if($proc -and $info.server_pid -eq $serverId){
    $shell=New-Object -ComObject WScript.Shell
    $shell.AppActivate($proc.Id)|Out-Null
    return
   }
  }catch{}
  Remove-Item -LiteralPath $lock -Force -ErrorAction SilentlyContinue
 }
 try{
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing
  Add-Type -Path $core
  Add-Type -Path $winForms
  $native=Join-Path $lib 'runtimes\win-x64\native'
  $env:PATH=$native+';'+$env:PATH
  # WebView2 defaults its user data folder next to the host executable
  # (powershell.exe under System32), which is not writable and fails with
  # E_ACCESSDENIED. Always point it at a writable per-user folder.
  $webData=Join-Path $dataRoot 'Workbench\webview2'
  New-Item -ItemType Directory -Force -Path $webData|Out-Null
  $form=New-Object System.Windows.Forms.Form
  $form.Text='镜像幻化'
  $area=[System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
  $form.Width=[Math]::Max(1100,[Math]::Min(1400,[int]($area.Width*0.82)))
  $form.Height=[Math]::Max(760,[Math]::Min(1200,$area.Height-40))
  $form.MinimumSize=New-Object System.Drawing.Size(1000,650)
  $form.StartPosition='CenterScreen'
  $icon=Join-Path $launcherRoot 'assets\images\icon\icon.ico'
  if(Test-Path -LiteralPath $icon){try{$form.Icon=New-Object System.Drawing.Icon($icon)}catch{}}
  $web=New-Object Microsoft.Web.WebView2.WinForms.WebView2
  $web.Dock=[System.Windows.Forms.DockStyle]::Fill
  $form.Controls.Add($web)
  $cleanup={
   try{
    if(Test-Path -LiteralPath $lock){
     $info=Get-Content -LiteralPath $lock -Raw -Encoding UTF8|ConvertFrom-Json
     if([int]$info.pid -eq $PID){Remove-Item -LiteralPath $lock -Force -ErrorAction SilentlyContinue}
    }
   }catch{}
  }
  $web.add_CoreWebView2InitializationCompleted({param($sender,$e)
   if($e.IsSuccess){
    try{
     $settings=$web.CoreWebView2.Settings
     $settings.AreDefaultContextMenusEnabled=$false
     $settings.AreDevToolsEnabled=$false
     $settings.IsStatusBarEnabled=$false
     $web.CoreWebView2.add_NewWindowRequested({param($sender,$e)
      $e.Handled=$true
      Start-Process $e.Uri
     })
     $web.CoreWebView2.Navigate($url)
    }catch{
     Write-WebviewLog ('webview2 settings/navigate failed: '+$_.Exception.ToString())
     Start-Process $url;$form.Close()
    }
   }else{
    try{Write-WebviewLog ('webview2 init failed: '+$e.InitializationException.ToString())}
    catch{Write-WebviewLog 'webview2 init failed: unknown exception'}
    Start-Process $url;$form.Close()
   }
  })
  $form.Add_Shown({try{
    $wvEnv=[Microsoft.Web.WebView2.Core.CoreWebView2Environment]::CreateAsync($null,$webData,$null).GetAwaiter().GetResult()
    $web.EnsureCoreWebView2Async($wvEnv)|Out-Null
   }catch{
    Write-WebviewLog ('webview2 environment failed: '+$_.Exception.ToString())
    Start-Process $url;$form.Close()
   }})
  $timer=New-Object System.Windows.Forms.Timer
  $timer.Interval=250
  $timer.add_Tick({if($serverProcess.HasExited){$form.Close()}})
  $timer.Start()
  $form.Add_FormClosed({$timer.Stop();$timer.Dispose();$web.Dispose();& $cleanup})
  @{pid=$PID;url=$url;server_pid=$serverId}|ConvertTo-Json|Set-Content -LiteralPath $lock -Encoding UTF8
  [System.Windows.Forms.Application]::Run($form)
 }catch{
  Write-WebviewLog ('webview2 window failed: '+$_.Exception.ToString())
  & $cleanup
  Start-Process $url
 }
}
function Find-PywebviewPython {
 $candidates=New-Object System.Collections.Generic.List[string]
 if($env:MOS_WEBVIEW_PYTHON){$candidates.Add($env:MOS_WEBVIEW_PYTHON)}
 $candidates.Add((Join-Path $launcherRoot 'venv\Scripts\pythonw.exe'))
 $candidates.Add((Join-Path $launcherRoot 'venv\Scripts\python.exe'))
 foreach($root in @('D:\projects\python','C:\projects\python',(Join-Path $env:USERPROFILE 'projects\python'))){
  if(-not (Test-Path -LiteralPath $root)){continue}
  try{
   Get-ChildItem -LiteralPath $root -Directory -Filter 'FaustLauncher' -Recurse -Depth 3 -ErrorAction SilentlyContinue | ForEach-Object {
    $candidates.Add((Join-Path $_.FullName 'venv\Scripts\pythonw.exe'))
    $candidates.Add((Join-Path $_.FullName 'venv\Scripts\python.exe'))
   }
  }catch{}
 }
 foreach($candidate in $candidates){
  if(-not $candidate -or -not (Test-Path -LiteralPath $candidate)){continue}
  try{
   & $candidate -c "import webview" 2>$null
   if($LASTEXITCODE -eq 0){return $candidate}
  }catch{}
 }
 return $null
}
function Start-Pywebview([string]$url,[int]$serverId){
 $py=Find-PywebviewPython
 if(-not $py){return $false}
 $script=Join-Path $PSScriptRoot 'launch_webview.py'
 if(-not (Test-Path -LiteralPath $script)){return $false}
 try{
  Start-Process -FilePath $py -ArgumentList @(('"'+$script+'"'),'--url',$url,'--addon',('"'+$addon+'"'),'--server-pid',$serverId,'--data-root',('"'+$dataRoot+'"')) -WindowStyle Hidden
  return $true
 }catch{return $false}
}
$localVersion=$null
try{$localVersion=(Get-Content -LiteralPath (Join-Path $addon 'addon_info.json') -Raw -Encoding UTF8|ConvertFrom-Json).version}catch{}
$state=Join-Path $dataRoot 'workbench-instance.json'
if($ExistingUrl){
 if($ExistingUrl -notmatch '^http://127\.0\.0\.1:\d{1,5}/[A-Za-z0-9_-]+/$'){exit 1}
 $published=Get-Content -LiteralPath $state -Raw -Encoding UTF8|ConvertFrom-Json
 if($published.url -cne $ExistingUrl){exit 1}
 $ping=Invoke-RestMethod -Uri ($ExistingUrl+'api/instance-ping') -TimeoutSec 1
 if(-not $ping.workbench -or -not $ping.pid -or $ping.pid -ne $published.pid){exit 1}
 if($ServerOnly){Write-Output $ExistingUrl;exit 0}
 if(Start-Pywebview $ExistingUrl $ping.pid){exit 0}
 Show-WorkbenchWindow $ExistingUrl $ping.pid
 exit 0
}
$sessionProcesses=@(foreach($ownerId in @($HostProcessId,$GameProcessId)){
 if($ownerId -gt 0){
  $owner=Get-Process -Id $ownerId
  $null=$owner.Handle
  $owner
 }
})
if(Test-Path -LiteralPath $state){
 try{
  $url=(Get-Content -LiteralPath $state -Raw -Encoding UTF8|ConvertFrom-Json).url
  if($url -match '^http://127\.0\.0\.1:\d{1,5}/[A-Za-z0-9_-]+/$'){
   $ping=Invoke-RestMethod -Uri ($url+'api/instance-ping') -TimeoutSec 1
   if($ping.workbench){
    $buildVersion=$null
    try{$buildVersion=(Get-Content -LiteralPath (Join-Path $dataRoot 'Workbench/server_build.json') -Raw -Encoding UTF8|ConvertFrom-Json).version}catch{}
    if((-not $ping.version) -or ($ping.version -ne $localVersion) -or (-not $buildVersion) -or ($buildVersion -ne $localVersion)){
     $token=$url.TrimEnd('/').Split('/')[-1]
     try{
      $shutdown=Invoke-WebRequest -Method Post -Uri ($url+'api/instance-shutdown') -Headers @{'X-Workbench'=$token;'Content-Type'='application/json'} -Body '{"host_pid":0}' -TimeoutSec 3
     }catch{}
     for($i=0;$i -lt 20;$i++){
      Start-Sleep -Milliseconds 150
      try{ Invoke-RestMethod -Uri ($url+'api/instance-ping') -TimeoutSec 1|Out-Null }
      catch{ break }
     }
    }else{
     if(-not (Attach-Workbench $url)){throw '无法绑定工作台会话'}
     if($ServerOnly){Write-Output $url;exit 0}
     if(Start-Pywebview $url $ping.pid){exit 0}
     Show-WorkbenchWindow $url $ping.pid;exit 0
    }
   }
  }
 }catch{}
}
$script=Join-Path (Split-Path $PSScriptRoot -Parent) 'workbench.py'
$logId=(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$logDir=Join-Path ([IO.Path]::GetTempPath()) 'FaustRandomIdentity-Workbench'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$arguments=@(('"'+$script+'"'),'--addon',('"'+$addon+'"'),'--no-browser','--startup-pid',"$PID")
if($HostProcessId -gt 0){$arguments+=@('--host-pid',"$HostProcessId")}
if($GameProcessId -gt 0){$arguments+=@('--game-pid',"$GameProcessId")}
$startedServer=Start-Process -PassThru -FilePath $python -ArgumentList $arguments -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir ('workbench-start-'+$logId+'.log')) -RedirectStandardError (Join-Path $logDir ('workbench-error-'+$logId+'.log'))
$url=$null
for($i=0;$i -lt 100;$i++){
 if($startedServer.HasExited -and $startedServer.ExitCode -ne 0){throw "工作台启动失败，详见 $logDir"}
 foreach($owner in $sessionProcesses){if($owner.HasExited){exit 1}}
 Start-Sleep -Milliseconds 200
 if(-not (Test-Path -LiteralPath $state)){continue}
 try{
  $candidate=(Get-Content -LiteralPath $state -Raw -Encoding UTF8|ConvertFrom-Json).url
  if($candidate -match '^http://127\.0\.0\.1:\d{1,5}/[A-Za-z0-9_-]+/$'){
   $ping=Invoke-RestMethod -Uri ($candidate+'api/instance-ping') -TimeoutSec 1
   if($ping.workbench -and $ping.version -eq $localVersion -and $ping.pid -and (Attach-Workbench $candidate)){$url=$candidate;break}
  }
 }catch{$lastStartError=$_.Exception.Message}
}
if(-not $url){throw "工作台未启动或会话已结束。$lastStartError"}
if($url){
 if($ServerOnly){Write-Output $url;exit 0}
 elseif(Start-Pywebview $url $ping.pid){exit 0}
 else{Show-WorkbenchWindow $url $ping.pid}
}
