$ErrorActionPreference='Stop'
$HostProcessId=0
$ServerOnly=$args -contains '-ServerOnly'
for($i=0;$i -lt $args.Count-1;$i++){if($args[$i] -eq '-HostProcessId'){$HostProcessId=[int]$args[$i+1]}}
$addon=Split-Path $PSScriptRoot -Parent
$launcherRoot=Split-Path (Split-Path $addon -Parent) -Parent
$embedded=Join-Path $launcherRoot 'resources\mod_loader\_internal\venv\Bins\python.exe'
if(Test-Path -LiteralPath $embedded){$python=$embedded}
else {
 $cmd=Get-Command python.exe -ErrorAction SilentlyContinue
 if(-not $cmd){throw '未找到 Python，请安装 Python 3.9 或更新版本。'}
 $python=$cmd.Source
}
function Show-WorkbenchWindow([string]$url){
 $lib=Join-Path $launcherRoot '_internal\webview\lib'
 $core=Join-Path $lib 'Microsoft.Web.WebView2.Core.dll'
 $winForms=Join-Path $lib 'Microsoft.Web.WebView2.WinForms.dll'
 if(-not (Test-Path -LiteralPath $core) -or -not (Test-Path -LiteralPath $winForms)){
  Start-Process $url;return
 }
 $lock=Join-Path $addon 'Workbench\webview-window.json'
 if(Test-Path -LiteralPath $lock){
  try{
   $info=Get-Content -LiteralPath $lock -Raw|ConvertFrom-Json
   $proc=Get-Process -Id ([int]$info.pid) -ErrorAction SilentlyContinue
   if($proc){
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
     $info=Get-Content -LiteralPath $lock -Raw|ConvertFrom-Json
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
     $web.CoreWebView2.Navigate($url)
    }catch{Start-Process $url;$form.Close()}
   }else{Start-Process $url;$form.Close()}
  })
  $web.add_NewWindowRequested({param($sender,$e)
   $e.Handled=$true
   Start-Process $e.Uri
  })
  $form.Add_Shown({try{$web.EnsureCoreWebView2Async($null)|Out-Null}catch{Start-Process $url;$form.Close()}})
  $form.Add_FormClosed({& $cleanup})
  @{pid=$PID;url=$url}|ConvertTo-Json|Set-Content -LiteralPath $lock -Encoding UTF8
  [System.Windows.Forms.Application]::Run($form)
 }catch{
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
function Start-Pywebview([string]$url){
 $py=Find-PywebviewPython
 if(-not $py){return $false}
 $script=Join-Path $PSScriptRoot 'launch_webview.py'
 if(-not (Test-Path -LiteralPath $script)){return $false}
 try{
  Start-Process -FilePath $py -ArgumentList @($script,'--url',$url,'--addon',$addon) -WindowStyle Hidden
  return $true
 }catch{return $false}
}
$localVersion=$null
try{$localVersion=(Get-Content -LiteralPath (Join-Path $addon 'addon_info.json') -Raw|ConvertFrom-Json).version}catch{}
$state=Join-Path $addon 'workbench-instance.json'
if(Test-Path -LiteralPath $state){
 try{
  $url=(Get-Content -LiteralPath $state -Raw|ConvertFrom-Json).url
  if($url -match '^http://127\.0\.0\.1:\d{1,5}/[A-Za-z0-9_-]+/$'){
   $ping=Invoke-RestMethod -Uri ($url+'api/instance-ping') -TimeoutSec 1
   if($ping.workbench){
    $buildVersion=$null
    try{$buildVersion=(Get-Content -LiteralPath (Join-Path $addon 'Workbench/server_build.json') -Raw|ConvertFrom-Json).version}catch{}
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
     if($ServerOnly){Write-Output $url;exit 0}
     if(Start-Pywebview $url){exit 0}
     Show-WorkbenchWindow $url;exit 0
    }
   }
  }
 }catch{}
}
$script=Join-Path $PSScriptRoot 'workbench.py'
$logId=(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'-'+[Guid]::NewGuid().ToString('N').Substring(0,8)
$logDir=Join-Path ([IO.Path]::GetTempPath()) 'FaustRandomIdentity-Workbench'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$arguments=@(('"'+$script+'"'),'--addon',('"'+$addon+'"'),'--no-browser')
if($HostProcessId -gt 0){$arguments+=@('--host-pid',"$HostProcessId")}
Start-Process -FilePath $python -ArgumentList $arguments -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir ('workbench-start-'+$logId+'.log')) -RedirectStandardError (Join-Path $logDir ('workbench-error-'+$logId+'.log'))
$url=$null
for($i=0;$i -lt 100;$i++){
 Start-Sleep -Milliseconds 200
 if(-not (Test-Path -LiteralPath $state)){continue}
 try{
  $candidate=(Get-Content -LiteralPath $state -Raw|ConvertFrom-Json).url
  if($candidate -match '^http://127\.0\.0\.1:\d{1,5}/[A-Za-z0-9_-]+/$'){
   $ping=Invoke-RestMethod -Uri ($candidate+'api/instance-ping') -TimeoutSec 1
   if($ping.workbench){$url=$candidate;break}
  }
 }catch{}
}
if($url){
 if($ServerOnly){Write-Output $url}
 elseif(Start-Pywebview $url){exit 0}
 else{Show-WorkbenchWindow $url}
}
